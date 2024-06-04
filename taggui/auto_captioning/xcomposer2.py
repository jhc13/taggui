import importlib.util

import numpy as np
import torch
from PIL import Image as PilImage
from torchvision.transforms import functional

from utils.enums import CaptionDevice, CaptionModelType


def get_xcomposer2_error_message(model_id: str, device: CaptionDevice,
                                 load_in_4_bit: bool) -> str | None:
    is_4_bit_model = '4bit' in model_id
    if is_4_bit_model:
        if not importlib.util.find_spec('auto_gptq'):
            return ('This model requires the `auto-gptq` package, which is '
                    'only available on Linux and Windows.')
        if device == CaptionDevice.CPU:
            return 'This model can only be loaded on a GPU.'
        if not load_in_4_bit:
            return 'This model can only be loaded in 4-bit.'
    elif load_in_4_bit:
        return 'This model cannot be loaded in 4-bit.'
    return None


try:
    from auto_gptq.modeling import BaseGPTQForCausalLM
except ImportError:
    BaseGPTQForCausalLM = object


class InternLMXComposer2QuantizedForCausalLM(BaseGPTQForCausalLM):
    layers_block_name = 'model.layers'
    outside_layer_modules = ['vit', 'vision_proj', 'model.tok_embeddings',
                             'model.norm', 'output']
    inside_layer_modules = [
        ['attention.wqkv.linear'],
        ['attention.wo.linear'],
        ['feed_forward.w1.linear', 'feed_forward.w3.linear'],
        ['feed_forward.w2.linear'],
    ]


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


def get_xcomposer2_inputs(model_type: CaptionModelType, model, processor,
                          load_in_4_bit: bool, text: str, pil_image: PilImage,
                          device: torch.device, dtype_argument: dict) -> dict:
    input_embeddings_parts = []
    image_mask_parts = []
    if model_type == CaptionModelType.XCOMPOSER2_4KHD:
        pil_image = hd_transform(pil_image)
    processed_image = model.vis_processor(pil_image).unsqueeze(0).to(
        device, **dtype_argument)
    image_embeddings, *_ = model.img2emb(processed_image)
    for text_part in text.split('<ImageHere>'):
        part_token_ids = processor(
            text_part, return_tensors='pt').input_ids.to(device)
        if load_in_4_bit:
            part_embeddings = model.model.model.tok_embeddings(
                part_token_ids)
        else:
            part_embeddings = model.model.tok_embeddings(
                part_token_ids)
        input_embeddings_parts.append(part_embeddings)
        image_mask_parts.append(torch.zeros(part_embeddings.shape[:2]))
    input_embeddings_parts.insert(1, image_embeddings[0].unsqueeze(0))
    image_mask_parts.insert(
        1, torch.ones(1, image_embeddings[0].shape[0]))
    input_embeddings = torch.cat(
        input_embeddings_parts, dim=1).to(device)
    image_mask = torch.cat(image_mask_parts, dim=1).bool().to(device)
    eos_token_id = [
        processor.eos_token_id,
        processor.convert_tokens_to_ids(['[UNUSED_TOKEN_145]'])[0]
    ]
    model_inputs = {
        'inputs_embeds': input_embeddings,
        'im_mask': image_mask,
        'eos_token_id': eos_token_id
    }
    return model_inputs
