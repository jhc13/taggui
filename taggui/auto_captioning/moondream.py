import sys
from inspect import getsource

import torch
from PIL import Image as PilImage
from transformers import AutoModelForCausalLM


def get_moondream_error_message(load_in_4_bit: bool,
                                beam_count: int) -> str | None:
    if load_in_4_bit:
        return 'This model cannot be loaded in 4-bit.'
    if beam_count > 1:
        return 'This model only supports `Number of beams` set to 1.'
    return None


def monkey_patch_moondream1(device: torch.device, model_id: str):
    """Monkey patch moondream1 for Transformers v4.38."""
    # There are multiple modules with a name containing 'modeling_phi'.
    phi_module = next(module for module_name, module in sys.modules.items()
                      if 'moondream1' in module_name
                      and 'modeling_phi' in module_name)
    phi_module_source = getsource(phi_module)
    # Modify the source code at line 318 of `modeling_phi.py`.
    insert_index = phi_module_source.find(' ' * 12
                                          + 'padding_mask.masked_fill_')
    phi_module_source = (
            phi_module_source[:insert_index]
            + ' ' * 12 + 'key_padding_mask = key_padding_mask[:, :seqlen_k]\n'
            + phi_module_source[insert_index:]
    )
    # Reload the model using the updated source code.
    exec(phi_module_source, phi_module.__dict__)
    dtype_argument = ({'torch_dtype': torch.float16}
                      if device.type == 'cuda' else {})
    model = AutoModelForCausalLM.from_pretrained(model_id, device_map=device,
                                                 trust_remote_code=True,
                                                 **dtype_argument)
    return model


def get_moondream_inputs(model, processor, text: str, pil_image: PilImage,
                         device: torch.device, dtype_argument: dict) -> dict:
    encoded_image = model.encode_image(pil_image)
    eos_tokens_ids = processor('<END>').input_ids
    inputs_embeds = model.input_embeds(text, encoded_image, processor)
    model_inputs = {
        'inputs_embeds': inputs_embeds,
        'attention_mask': (torch.ones(1, inputs_embeds.shape[1]).bool()
                           .to(device, **dtype_argument)),
        'bos_token_id': processor.bos_token_id,
        'eos_token_id': eos_tokens_ids,
        'pad_token_id': eos_tokens_ids[0]
    }
    return model_inputs
