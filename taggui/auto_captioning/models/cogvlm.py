import sys
from pathlib import Path

from transformers import AutoModelForCausalLM, LlamaTokenizer

from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.image import Image


def patch_cogvlm_source_code() -> bool:
    """Patch the source code to be compatible with Transformers v4.42."""
    cog_module = next(module for module_name, module in sys.modules.items()
                      if 'modeling_cog' in module_name)
    cog_module_source_path = cog_module.__file__
    cog_module_source = Path(cog_module_source_path).read_text()
    original_code = """
        model_kwargs["past_key_values"] = self._extract_past_from_model_output(
            outputs, standardize_cache_format=standardize_cache_format
        )"""
    patched_code = """
        cache_name, cache = self._extract_past_from_model_output(outputs)
        model_kwargs[cache_name] = cache"""
    if original_code not in cog_module_source:
        return False
    cog_module_source = cog_module_source.replace(original_code,
                                                  patched_code)
    Path(cog_module_source_path).write_text(cog_module_source)
    del sys.modules[cog_module.__name__]
    return True


class Cogvlm(AutoCaptioningModel):
    transformers_model_class = AutoModelForCausalLM

    def get_processor(self):
        return LlamaTokenizer.from_pretrained('lmsys/vicuna-7b-v1.5')

    def patch_source_code(self) -> bool:
        return patch_cogvlm_source_code()

    def monkey_patch_after_loading(self):
        """
        Monkey patch the model to support `caption_start`. This has to be done
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
    def get_default_prompt() -> str:
        return 'Describe the image in twenty words or less.'

    def get_input_text(self, image_prompt: str) -> str:
        # `caption_start` is added later.
        return image_prompt

    def get_model_inputs(self, image_prompt: str, image: Image, crop: bool) -> dict:
        text = self.get_input_text(image_prompt)
        pil_image = self.load_image(image, crop)
        model_inputs = self.model.build_conversation_input_ids(
            self.processor, query=text, images=[pil_image],
            template_version=None)
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

    @staticmethod
    def postprocess_image_prompt(image_prompt: str) -> str:
        return f'Question: {image_prompt} Answer:'
