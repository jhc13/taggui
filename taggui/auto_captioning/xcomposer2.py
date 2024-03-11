import torch
from PIL import Image as PilImage
from auto_gptq.modeling import BaseGPTQForCausalLM

from auto_captioning.enums import Device


def get_xcomposer2_error_message(model_id: str, device: Device,
                                 load_in_4_bit: bool) -> str | None:
    is_4_bit_model = '4bit' in model_id
    if is_4_bit_model:
        if device == Device.CPU:
            return ('This version of the model can only be loaded on a GPU. '
                    'Select internlm/internlm-xcomposer2-vl-7b if you want to '
                    'load the model on the CPU.')
        if not load_in_4_bit:
            return ('This version of the model can only be loaded in 4-bit. '
                    'Select internlm/internlm-xcomposer2-vl-7b if you do not '
                    'want to load the model in 4-bit.')
    elif load_in_4_bit:
        return ('This version of the model cannot be loaded in 4-bit. Select '
                'internlm/internlm-xcomposer2-vl-7b-4bit if you want to load '
                'the model in 4-bit.')
    return None


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


def get_xcomposer2_inputs(model, processor, load_in_4_bit: bool, text: str,
                          pil_image: PilImage, device: torch.device,
                          dtype_argument: dict) -> dict:
    input_embeddings_parts = []
    image_mask_parts = []
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
