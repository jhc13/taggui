import torch
from transformers import AutoModelForCausalLM, BatchFeature

import auto_captioning.captioning_thread as captioning_thread
from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.image import Image


class Phi3Vision(AutoCaptioningModel):
    transformers_model_class = AutoModelForCausalLM

    def __init__(self,
                 captioning_thread_: 'captioning_thread.CaptioningThread',
                 caption_settings: dict):
        super().__init__(captioning_thread_, caption_settings)
        self.input_length = None

    @staticmethod
    def get_default_prompt() -> str:
        return 'Describe the image in one sentence.'

    @staticmethod
    def format_prompt(prompt: str) -> str:
        return f'<|user|>\n<|image_1|>\n{prompt}<|end|>\n<|assistant|>\n'

    def get_input_text(self, image_prompt: str) -> str:
        return image_prompt + self.caption_start

    def get_model_inputs(self, image_prompt: str,
                         image: Image, crop: bool) -> BatchFeature:
        model_inputs = super().get_model_inputs(image_prompt, image, crop)
        self.input_length = model_inputs['input_ids'].shape[1]
        return model_inputs

    def get_additional_generation_parameters(self) -> dict:
        return {'eos_token_id': self.tokenizer.eos_token_id}

    def get_caption_from_generated_tokens(
            self, generated_token_ids: torch.Tensor, image_prompt: str) -> str:
        generated_token_ids = generated_token_ids[:, self.input_length:]
        return super().get_caption_from_generated_tokens(
            generated_token_ids, image_prompt)
