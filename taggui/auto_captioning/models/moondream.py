import re
import sys
from pathlib import Path

import torch
from transformers import (AutoModelForCausalLM, AutoTokenizer,
                          CodeGenTokenizerFast)

from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.image import Image

MOONDREAM2_REVISION = '2024-08-26'


class Moondream(AutoCaptioningModel):
    transformers_model_class = AutoModelForCausalLM

    @staticmethod
    def get_default_prompt() -> str:
        return 'Describe the image in twenty words or less.'

    @staticmethod
    def format_prompt(prompt: str) -> str:
        return f'<image>\n\nQuestion: {prompt}\n\nAnswer:'

    def get_generation_model(self):
        return self.model.text_model

    def get_tokenizer(self):
        return self.processor


class Moondream1(Moondream):
    def get_additional_error_message(self) -> str | None:
        if self.load_in_4_bit:
            return 'This model cannot be loaded in 4-bit.'
        if self.beam_count > 1:
            return 'This model only supports `Number of beams` set to 1.'
        return None

    def get_processor(self):
        return CodeGenTokenizerFast.from_pretrained(self.model_id,
                                                    trust_remote_code=True)

    def patch_source_code(self) -> bool:
        """Patch the source code to be compatible with Transformers v4.38."""
        # There are multiple modules with a name containing 'modeling_phi'.
        phi_module = next(module for module_name, module in sys.modules.items()
                          if 'moondream1' in module_name
                          and 'modeling_phi' in module_name)
        phi_module_source_path = phi_module.__file__
        phi_module_source = Path(phi_module_source_path).read_text()
        # Modify the source code at line 318 of `modeling_phi.py`.
        insert_string = 'key_padding_mask = key_padding_mask[:, :seqlen_k]\n'
        insert_index = phi_module_source.find(' ' * 12
                                              + 'padding_mask.masked_fill_')
        if insert_string in phi_module_source or insert_index == -1:
            return False
        phi_module_source = (phi_module_source[:insert_index] + ' ' * 12
                             + insert_string
                             + phi_module_source[insert_index:])
        Path(phi_module_source_path).write_text(phi_module_source)
        del sys.modules[phi_module.__name__]
        return True

    def get_model_inputs(self, image_prompt: str, image: Image, crop: bool) -> dict:
        text = self.get_input_text(image_prompt)
        pil_image = self.load_image(image, crop)
        encoded_image = self.model.encode_image(pil_image)
        eos_tokens_ids = self.processor('<END>').input_ids
        inputs_embeds = self.model.input_embeds(text, encoded_image,
                                                self.processor)
        model_inputs = {
            'inputs_embeds': inputs_embeds,
            'attention_mask': (torch.ones(1, inputs_embeds.shape[1]).bool()
                               .to(self.device, **self.dtype_argument)),
            'bos_token_id': self.processor.bos_token_id,
            'eos_token_id': eos_tokens_ids,
            'pad_token_id': eos_tokens_ids[0]
        }
        return model_inputs

    @staticmethod
    def postprocess_generated_text(generated_text: str) -> str:
        generated_text = re.sub('END$', '', generated_text)
        generated_text = re.sub('<$', '', generated_text)
        return generated_text


class Moondream2(Moondream):
    def get_additional_error_message(self) -> str | None:
        if self.load_in_4_bit:
            return 'This model cannot be loaded in 4-bit.'
        return None

    def get_processor(self):
        return AutoTokenizer.from_pretrained(self.model_id,
                                             trust_remote_code=True)

    def get_model_load_arguments(self) -> dict:
        arguments = super().get_model_load_arguments()
        arguments['revision'] = MOONDREAM2_REVISION
        return arguments

    def get_model_inputs(self, image_prompt: str, image: Image, crop: bool) -> dict:
        text = self.get_input_text(image_prompt)
        pil_image = self.load_image(image, crop)
        encoded_image = self.model.encode_image(pil_image)
        inputs_embeds = self.model.input_embeds(text, encoded_image,
                                                self.processor)
        model_inputs = {
            'inputs_embeds': inputs_embeds,
            'attention_mask': (torch.ones(1, inputs_embeds.shape[1]).bool()
                               .to(self.device, **self.dtype_argument)),
            'bos_token_id': self.processor.bos_token_id,
            'eos_token_id': self.processor.eos_token_id,
            'pad_token_id': self.processor.bos_token_id
        }
        return model_inputs
