import importlib.util

import torch
from torchvision import transforms
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

from auto_captioning.auto_captioning_model import AutoCaptioningModel
from auto_captioning.models.cogvlm import patch_cogvlm_source_code
from utils.enums import CaptionDevice
from utils.image import Image

LANGUAGE_TOKEN_TYPE_ID = 0
VISION_TOKEN_TYPE_ID = 1


class Cogvlm2(AutoCaptioningModel):
    transformers_model_class = AutoModelForCausalLM

    def get_additional_error_message(self) -> str | None:
        if not importlib.util.find_spec('triton'):
            return ('This model cannot be run because it requires the '
                    '`triton` package, which is not available for your '
                    'system.')
        is_4_bit_model = 'int4' in self.model_id
        if is_4_bit_model:
            if self.device_setting == CaptionDevice.CPU:
                return (
                    'This version of the model can only be loaded on a GPU. '
                    'Select THUDM/cogvlm2-llama3-chat-19B if you want to load '
                    'the model on the CPU.')
            if not self.load_in_4_bit:
                return (
                    'This version of the model can only be loaded in 4-bit. '
                    'Select THUDM/cogvlm2-llama3-chat-19B if you do not want '
                    'to load the model in 4-bit.')
        elif self.load_in_4_bit:
            return (
                'This version of the model cannot be loaded in 4-bit. Select '
                'THUDM/cogvlm2-llama3-chat-19B-int4 if you want to load the '
                'model in 4-bit.')
        return None

    def get_processor(self):
        return AutoTokenizer.from_pretrained(self.model_id,
                                             trust_remote_code=True)

    def get_model_load_arguments(self) -> dict:
        arguments = super().get_model_load_arguments()
        if self.load_in_4_bit:
            config = AutoConfig.from_pretrained(self.model_id,
                                                trust_remote_code=True)
            config.quantization_config = arguments['quantization_config']
            arguments['config'] = config
            del arguments['quantization_config']
        return arguments

    def patch_source_code(self) -> bool:
        return patch_cogvlm_source_code()

    @staticmethod
    def get_default_prompt() -> str:
        return 'Describe the image in one sentence.'

    @staticmethod
    def format_prompt(prompt: str) -> str:
        return f'Question: {prompt} Answer:'

    def get_model_inputs(self, image_prompt: str, image: Image, crop: bool) -> dict:
        text = self.get_input_text(image_prompt)
        pil_image = self.load_image(image, crop)
        image_size = self.model.config.vision_config['image_size']
        patch_size = self.model.config.vision_config['patch_size']
        vision_tokens_count = ((image_size // patch_size // 2)
                               * (image_size // patch_size // 2) + 2)
        input_ids = [self.processor.bos_token_id]
        token_type_ids = [LANGUAGE_TOKEN_TYPE_ID]
        self.processor.pad_token_id = 128002
        input_ids += [self.processor.pad_token_id] * vision_tokens_count
        token_type_ids += [VISION_TOKEN_TYPE_ID] * vision_tokens_count
        text_ids = self.processor.encode(text, add_special_tokens=False)
        input_ids += text_ids
        token_type_ids += [LANGUAGE_TOKEN_TYPE_ID] * len(text_ids)
        attention_mask = [1] * len(input_ids)
        transform = transforms.Compose([
            transforms.Resize(
                (image_size, image_size),
                interpolation=transforms.InterpolationMode.BICUBIC
            ),
            transforms.ToTensor(),
            transforms.Normalize((0.48145466, 0.4578275, 0.40821073),
                                 (0.26862954, 0.26130258, 0.27577711))
        ])
        image = transform(pil_image)
        inputs = {
            'input_ids': torch.tensor(input_ids).unsqueeze(0).to(self.device),
            'token_type_ids': torch.tensor(token_type_ids).unsqueeze(0).to(
                self.device),
            'attention_mask': torch.tensor(attention_mask).unsqueeze(0).to(
                self.device),
            'images': [[image.to(self.device, **self.dtype_argument)]
                       for _ in range(self.beam_count)]
        }
        return inputs

    def get_tokenizer(self):
        return self.processor

    @staticmethod
    def get_additional_generation_parameters() -> dict:
        return {'pad_token_id': 128002}
