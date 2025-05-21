import bitsandbytes
import torch
from transformers import LlavaForConditionalGeneration

from auto_captioning.auto_captioning_model import AutoCaptioningModel


class Joycaption(AutoCaptioningModel):
    dtype = torch.bfloat16
    transformers_model_class = LlavaForConditionalGeneration

    def monkey_patch_after_loading(self) -> None:
        if self.load_in_4_bit:
            attention = self.model.vision_tower.vision_model.head.attention
            # JoyCaption's out-projection layer is not dynamically quantizable,
            # so if it was converted into `nn.Linear4bit`, replace it with the
            # original `nn.Linear`.
            if isinstance(attention.out_proj, bitsandbytes.nn.Linear4bit):
                attention.out_proj = torch.nn.Linear(
                    in_features=attention.embed_dim,
                    out_features=attention.embed_dim,
                    device=self.device,
                    dtype=self.dtype)

    @staticmethod
    def get_default_prompt() -> str:
        return 'Briefly describe the image.'

    def format_prompt(self, prompt: str) -> str:
        conversation = [
            {
                'role': 'system',
                'content': 'You are a helpful image captioner.'
            },
            {
                'role': 'user',
                'content': prompt
            }
        ]
        templated_prompt = self.processor.apply_chat_template(
            conversation, tokenize=False, add_generation_prompt=True)
        return templated_prompt

    def get_input_text(self, image_prompt: str) -> str:
        return image_prompt + self.caption_start

    @staticmethod
    def postprocess_image_prompt(image_prompt: str) -> str:
        special_tokens = ['<|start_header_id|>', '<|end_header_id|>',
                          '<|eot_id|>', '<|reserved_special_token_70|>',
                          '<|reserved_special_token_69|>',
                          '<|reserved_special_token_71|>']
        for special_token in special_tokens:
            image_prompt = image_prompt.replace(special_token, '')
        return image_prompt
