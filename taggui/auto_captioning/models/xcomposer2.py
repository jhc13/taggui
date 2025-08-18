import sys
from contextlib import redirect_stdout

import numpy as np
import torch
from PIL import Image as PilImage
try:
    from gptqmodel.models import BaseGPTQModel
    gptq = True
except:
    gptq = False
from torchvision.transforms import functional
from transformers import AutoModelForCausalLM, AutoTokenizer

from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.enums import CaptionDevice
from utils.image import Image

if gptq:
    class InternLMXComposer2GPTQ(BaseGPTQModel):
        base_modules = ['vit', 'vision_proj', 'model.tok_embeddings', 'model.norm',
                        'output']
        layers_node = 'model.layers'
        layer_modules = [
            ['attention.wqkv.linear'],
            ['attention.wo.linear'],
            ['feed_forward.w1.linear', 'feed_forward.w3.linear'],
            ['feed_forward.w2.linear'],
        ]



class Xcomposer2(AutoCaptioningModel):
    model_load_context_manager = redirect_stdout(None)
    transformers_model_class = AutoModelForCausalLM

    def get_additional_error_message(self) -> str | None:
        is_4_bit_model = '4bit' in self.model_id
        if is_4_bit_model:
            if self.device_setting == CaptionDevice.CPU:
                return 'This model can only be loaded on a GPU.'
            if not self.load_in_4_bit:
                return 'This model can only be loaded in 4-bit.'
        elif self.load_in_4_bit:
            return 'This model cannot be loaded in 4-bit.'
        return None

    def get_processor(self):
        return AutoTokenizer.from_pretrained(self.model_id,
                                             trust_remote_code=True)

    def load_model(self, model_load_arguments: dict):
        if self.load_in_4_bit:
            with self.model_load_context_manager:
                model = InternLMXComposer2GPTQ.from_quantized(
                    self.model_id, trust_remote_code=True,
                    device=str(self.device))
            model.eval()
        else:
            model = super().load_model(model_load_arguments)
        return model

    def monkey_patch_after_loading(self):
        """
        Monkey patch the model to be compatible with Transformers v4.46.
        Patching the source code does not work for this model because the
        remote code is re-downloaded each time the model is loaded.
        """

        def patched_forward(self_, images):
            """
            Identical to the original `forward` method, except for the
            additional `interpolate_pos_encoding=True` arguments.
            """
            if not self_.is_loaded:
                self_.load_model()
            if type(images) is list:
                image_features = []
                for image in images:
                    image_forward_out = self_.vision_tower(
                        image.to(device=self_.device,
                                 dtype=self_.dtype).unsqueeze(0),
                        output_hidden_states=True,
                        interpolate_pos_encoding=True)
                    image_feature = self_.feature_select(image_forward_out).to(
                        image.dtype)
                    image_features.append(image_feature)
            else:
                image_forward_outs = self_.vision_tower(
                    images.to(device=self_.device, dtype=self_.dtype),
                    output_hidden_states=True, interpolate_pos_encoding=True)
                image_features = self_.feature_select(image_forward_outs).to(
                    images.dtype)
            return image_features

        # There may be multiple modules with the same name, each corresponding
        # to a different version of the model that was loaded.
        clip_modules = [module for module_name, module in sys.modules.items()
                        if 'build_mlp' in module_name]
        for clip_module in clip_modules:
            clip_module.CLIPVisionTower.forward = patched_forward

    @staticmethod
    def get_default_prompt() -> str:
        return 'Concisely describe the image.'

    @staticmethod
    def format_prompt(prompt: str) -> str:
        return (f'[UNUSED_TOKEN_146]user\n<ImageHere>{prompt}'
                f'[UNUSED_TOKEN_145]\n[UNUSED_TOKEN_146]assistant\n')

    def get_input_text(self, image_prompt: str) -> str:
        return image_prompt + self.caption_start

    def get_model_inputs(self, image_prompt: str, image: Image, crop: bool) -> dict:
        text = self.get_input_text(image_prompt)
        pil_image = self.load_image(image, crop)
        input_embeddings_parts = []
        image_mask_parts = []
        processed_image = self.model.vis_processor(pil_image).unsqueeze(0).to(
            self.device, **self.dtype_argument)
        image_embeddings, *_ = self.model.img2emb(processed_image)
        for text_part in text.split('<ImageHere>'):
            part_token_ids = self.processor(
                text_part, return_tensors='pt').input_ids.to(self.device)
            if self.load_in_4_bit:
                part_embeddings = self.model.model.model.tok_embeddings(
                    part_token_ids)
            else:
                part_embeddings = self.model.model.tok_embeddings(
                    part_token_ids)
            input_embeddings_parts.append(part_embeddings)
            image_mask_parts.append(torch.zeros(part_embeddings.shape[:2]))
        input_embeddings_parts.insert(1, image_embeddings[0].unsqueeze(0))
        image_mask_parts.insert(
            1, torch.ones(1, image_embeddings[0].shape[0]))
        input_embeddings = torch.cat(
            input_embeddings_parts, dim=1).to(self.device)
        image_mask = torch.cat(image_mask_parts, dim=1).bool().to(self.device)
        eos_token_id = [
            self.processor.eos_token_id,
            self.processor.convert_tokens_to_ids(['[UNUSED_TOKEN_145]'])[0]
        ]
        model_inputs = {
            'inputs_embeds': input_embeddings,
            'im_mask': image_mask,
            'eos_token_id': eos_token_id
        }
        return model_inputs

    def get_tokenizer(self):
        return self.processor

    @staticmethod
    def postprocess_generated_text(generated_text: str) -> str:
        return generated_text.split('[UNUSED_TOKEN_145]')[0]


def pad_image(pil_image: PilImage) -> PilImage:
    width, height = pil_image.size
    target_height = int(np.ceil(height / 336) * 336)
    top_padding = int((target_height - height) / 2)
    bottom_padding = target_height - height - top_padding
    left_padding = 0
    right_padding = 0
    pil_image = functional.pad(pil_image, [left_padding, top_padding,
                                           right_padding, bottom_padding],
                               fill=(255, 255, 255))
    return pil_image


def hd_transform(pil_image: PilImage, hd_number: int = 25) -> PilImage:
    width, height = pil_image.size
    transposed = False
    if width < height:
        pil_image = pil_image.transpose(PilImage.Transpose.TRANSPOSE)
        transposed = True
        width, height = pil_image.size
    aspect_ratio = width / height
    scale = 1
    while scale * np.ceil(scale / aspect_ratio) <= hd_number:
        scale += 1
    scale -= 1
    new_width = int(scale * 336)
    new_height = int(new_width / aspect_ratio)
    pil_image = functional.resize(pil_image, [new_height, new_width])
    pil_image = pad_image(pil_image)
    if transposed:
        pil_image = pil_image.transpose(PilImage.Transpose.TRANSPOSE)
    return pil_image


class Xcomposer2_4khd(Xcomposer2):
    def monkey_patch_after_loading(self):
        return

    def load_image(self, image: Image, crop: bool) -> PilImage:
        pil_image = super().load_image(image, crop)
        pil_image = hd_transform(pil_image)
        return pil_image
