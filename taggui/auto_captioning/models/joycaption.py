import numpy as np
import torch
from transformers import LlavaForConditionalGeneration, BatchFeature

from auto_captioning import captioning_thread
from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.image import Image


class JoycaptionLlavaLlama3(AutoCaptioningModel):
    transformers_model_class = LlavaForConditionalGeneration

    def __init__(self,
                 captioning_thread_: 'captioning_thread.CaptioningThread',
                 caption_settings: dict):
        super().__init__(captioning_thread_, caption_settings)

        self.input_length = None
        self.dtype = torch.bfloat16
        self.dtype_argument = ({'dtype': self.dtype}
                               if self.device.type == 'cuda' else {})

    def get_error_message(self) -> str | None:
        if self.load_in_4_bit:
            # The official model does not currently work when loaded
            # in 4-bit mode.
            return 'Joycaption cannot currently be loaded in 4-bit.'
        return super().get_error_message()

    @staticmethod
    def get_default_prompt() -> str:
        return 'Write a stable diffusion prompt for this image.'

    def format_prompt(self, prompt: str) -> str:
        conversation = [
                {
                    "role": "system", 
                    "content": "You are a helpful image captioner.",
                },
                {
                    "role": "user",
                    "content": prompt.strip(),
                },
        ]
        templated_prompt = self.processor.apply_chat_template(
            conversation, tokenize=False, add_generation_prompt=True)

        self.caption_start = self.caption_start.strip()
        if self.caption_start:
            templated_prompt = templated_prompt + self.caption_start

        return templated_prompt

    def get_additional_generation_parameters(self) -> dict:
        additional_parameters = super().get_additional_generation_parameters()
        additional_parameters['use_cache'] = True

        tokenizer = self.get_tokenizer()
        eos_token_id = (tokenizer('<|eot_id|>', add_special_tokens=False)
                        .input_ids)[0]
        additional_parameters['eos_token_id'] = eos_token_id

        return additional_parameters

    def get_input_text(self, image_prompt: str) -> str:
    	# Do not add caption_start here, we add it in format_prompt().
        return image_prompt

    def get_model_inputs(self, image_prompt: str,
                         image: Image) -> BatchFeature | dict | np.ndarray:
        model_inputs = super().get_model_inputs(image_prompt, image)
        # Cache our input token length so we can remove that many from the
        # model's response.
        self.input_length = model_inputs['input_ids'].shape[1]
        return model_inputs

    def get_caption_from_generated_tokens(
            self, generated_token_ids: torch.Tensor, image_prompt: str) -> str:
        # Remove our prompt from the generated result
        generated_token_ids = generated_token_ids[:, self.input_length:]
        return super().get_caption_from_generated_tokens(
            generated_token_ids, image_prompt)
