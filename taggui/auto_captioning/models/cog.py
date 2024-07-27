import sys
from abc import ABC, abstractmethod
from contextlib import redirect_stdout
from inspect import getsource

from transformers import AutoModelForCausalLM, LlamaTokenizer

from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.image import Image


class Cog(AutoCaptioningModel, ABC):
    transformers_model_class = AutoModelForCausalLM

    @property
    @abstractmethod
    def template_version(self):
        ...

    def get_processor(self):
        return LlamaTokenizer.from_pretrained('lmsys/vicuna-7b-v1.5')

    @staticmethod
    def get_default_prompt() -> str:
        return 'Describe the image in twenty words or less.'

    def get_input_text(self, image_prompt: str) -> str:
        # `caption_start` is added later.
        return image_prompt

    def get_model_inputs(self, image_prompt: str, image: Image) -> dict:
        text = self.get_input_text(image_prompt)
        pil_image = self.load_image(image)
        model_inputs = self.model.build_conversation_input_ids(
            self.processor, query=text, images=[pil_image],
            template_version=self.template_version)
        # Only CogAgent uses `cross_images`.
        cross_images = model_inputs.get('cross_images')
        model_inputs = {
            'input_ids': (model_inputs['input_ids'].unsqueeze(0)
                          .to(self.device)),
            'token_type_ids': (model_inputs['token_type_ids'].unsqueeze(0)
                               .to(self.device)),
            'attention_mask': (model_inputs['attention_mask'].unsqueeze(0)
                               .to(self.device)),
            'images': [
                [model_inputs['images'][0].to(self.device,
                                              **self.dtype_argument)]
                for _ in range(self.beam_count)
            ]
        }
        if cross_images:
            model_inputs['cross_images'] = [
                [cross_images[0].to(self.device, **self.dtype_argument)]
                for _ in range(self.beam_count)
            ]
        return model_inputs

    def get_tokenizer(self):
        return self.processor


class Cogvlm(Cog):
    template_version = None

    def monkey_patch_after_loading(self):
        """
        Monkey patch CogVLM to support `caption_start`. This has to be done
        every time after loading because `caption_start` might have changed.
        """
        cogvlm_module = next(
            module for module_name, module in sys.modules.items()
            if 'modeling_cogvlm' in module_name)

        def format_cogvlm_prompt(prompt: str, caption_start_: str) -> str:
            prompt = f'Question: {prompt} Answer:'
            if caption_start_.strip():
                prompt += f' {caption_start_}'
            return prompt

        cogvlm_module._history_to_prompt = (
            lambda _, __, prompt_: format_cogvlm_prompt(prompt_,
                                                        self.caption_start))

    @staticmethod
    def postprocess_image_prompt(image_prompt: str) -> str:
        return f'Question: {image_prompt} Answer:'


class Cogagent(Cog):
    model_load_context_manager = redirect_stdout(None)
    template_version = 'chat_old'

    def monkey_patch_after_loading(self):
        """Monkey patch CogAgent to support beam search and `caption_start`."""
        cogagent_module = next(module
                               for module_name, module in sys.modules.items()
                               if 'modeling_cogagent' in module_name)
        cogagent_module_source = getsource(cogagent_module)
        # Modify the source code to make beam search work (line 613 of
        # `modeling_cogagent.py`).
        cogagent_module_source = cogagent_module_source.replace(
            '(batch_size, 1)',
            '(1, 1)')
        # Replace the method in the class with the updated version.
        exec(cogagent_module_source, cogagent_module.__dict__)
        self.model.model.__class__.llm_forward = (cogagent_module.CogAgentModel
                                                  .llm_forward)

        def format_cogagent_prompt(prompt: str, caption_start_: str) -> str:
            prompt = f'<EOI>Question: {prompt} Answer:'
            if caption_start_.strip():
                prompt += f' {caption_start_}'
            return prompt

        cogagent_module._history_to_prompt = {
            'chat_old': lambda _, prompt_: format_cogagent_prompt(
                prompt_, self.caption_start)
        }

    @staticmethod
    def postprocess_image_prompt(image_prompt: str) -> str:
        return f'<EOI>Question: {image_prompt} Answer:'
