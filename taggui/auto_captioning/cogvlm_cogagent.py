import sys
from inspect import getsource

import torch
from PIL import Image as PilImage

from utils.enums import CaptionModelType


def monkey_patch_cogvlm(caption_start: str):
    """Monkey patch CogVLM to support `caption_start`."""
    cogvlm_module = next(module for module_name, module in sys.modules.items()
                         if 'modeling_cogvlm' in module_name)

    def format_cogvlm_prompt(prompt: str, caption_start_: str) -> str:
        prompt = f'Question: {prompt} Answer:'
        if caption_start_.strip():
            prompt += f' {caption_start_}'
        return prompt

    cogvlm_module._history_to_prompt = (
        lambda _, __, prompt_: format_cogvlm_prompt(prompt_, caption_start))


def monkey_patch_cogagent(model, caption_start: str):
    """Monkey patch CogAgent to support beam search and `caption_start`."""
    cogagent_module = next(module
                           for module_name, module in sys.modules.items()
                           if 'modeling_cogagent' in module_name)
    cogagent_module_source = getsource(cogagent_module)
    # Modify the source code to make beam search work (line 613 of
    # `modeling_cogagent.py`).
    cogagent_module_source = cogagent_module_source.replace('(batch_size, 1)',
                                                            '(1, 1)')
    # Replace the method in the class with the updated version.
    exec(cogagent_module_source, cogagent_module.__dict__)
    model.model.__class__.llm_forward = (cogagent_module.CogAgentModel
                                         .llm_forward)

    def format_cogagent_prompt(prompt: str, caption_start_: str) -> str:
        prompt = f'<EOI>Question: {prompt} Answer:'
        if caption_start_.strip():
            prompt += f' {caption_start_}'
        return prompt

    cogagent_module._history_to_prompt = {
        'chat_old': lambda _, prompt_: format_cogagent_prompt(prompt_,
                                                              caption_start)
    }


def get_cogvlm_cogagent_inputs(model_type: CaptionModelType, model, processor,
                               text: str, pil_image: PilImage, beam_count: int,
                               device: torch.device,
                               dtype_argument: dict) -> dict:
    template_version = ('chat_old' if model_type == CaptionModelType.COGAGENT
                        else None)
    model_inputs = model.build_conversation_input_ids(
        processor, query=text, images=[pil_image],
        template_version=template_version)
    cross_images = model_inputs.get('cross_images')
    model_inputs = {
        'input_ids': model_inputs['input_ids'].unsqueeze(0).to(device),
        'token_type_ids': (model_inputs['token_type_ids'].unsqueeze(0)
                           .to(device)),
        'attention_mask': (model_inputs['attention_mask'].unsqueeze(0)
                           .to(device)),
        'images': [
            [model_inputs['images'][0].to(device, **dtype_argument)]
            for _ in range(beam_count)
        ]
    }
    if model_type == CaptionModelType.COGAGENT:
        model_inputs['cross_images'] = [
            [cross_images[0].to(device, **dtype_argument)]
            for _ in range(beam_count)
        ]
    return model_inputs
