import re

from utils.enums import CaptionModelType


def get_default_prompt(model_type: CaptionModelType) -> str:
    if model_type in (CaptionModelType.COGAGENT, CaptionModelType.COGVLM,
                      CaptionModelType.LLAVA_1_5, CaptionModelType.MOONDREAM1,
                      CaptionModelType.MOONDREAM2):
        return 'Describe the image in twenty words or less.'
    if model_type in (CaptionModelType.COGVLM2, CaptionModelType.LLAVA_LLAMA_3,
                      CaptionModelType.LLAVA_NEXT_34B,
                      CaptionModelType.LLAVA_NEXT_MISTRAL,
                      CaptionModelType.LLAVA_NEXT_VICUNA):
        return 'Describe the image in one sentence.'
    if model_type == CaptionModelType.XCOMPOSER2:
        return 'Concisely describe the image.'
    return ''


def format_prompt(prompt: str, model_type: CaptionModelType) -> str:
    if model_type == CaptionModelType.COGVLM2:
        return f'Question: {prompt} Answer:'
    if model_type == CaptionModelType.KOSMOS:
        return f'<grounding>{prompt}'
    if model_type == CaptionModelType.LLAVA_1_5:
        return f'USER: <image>\n{prompt}\nASSISTANT:'
    if model_type == CaptionModelType.LLAVA_LLAMA_3:
        return (f'<|start_header_id|>user<|end_header_id|>\n\n<image>\n'
                f'{prompt}<|eot_id|><|start_header_id|>assistant'
                f'<|end_header_id|>\n\n')
    if model_type == CaptionModelType.LLAVA_NEXT_34B:
        return (f'<|im_start|>system\nAnswer the questions.<|im_end|>'
                f'<|im_start|>user\n<image>\n{prompt}<|im_end|>'
                f'<|im_start|>assistant\n')
    if model_type == CaptionModelType.LLAVA_NEXT_MISTRAL:
        return f'[INST] <image>\n{prompt} [/INST]'
    if model_type == CaptionModelType.LLAVA_NEXT_VICUNA:
        return (f"A chat between a curious human and an artificial "
                f"intelligence assistant. The assistant gives helpful, "
                f"detailed, and polite answers to the human's questions. "
                f"USER: <image>\n{prompt} ASSISTANT:")
    if model_type in (CaptionModelType.MOONDREAM1,
                      CaptionModelType.MOONDREAM2):
        return f'<image>\n\nQuestion: {prompt}\n\nAnswer:'
    if model_type == CaptionModelType.XCOMPOSER2:
        return (f'[UNUSED_TOKEN_146]user\n<ImageHere>{prompt}'
                f'[UNUSED_TOKEN_145]\n[UNUSED_TOKEN_146]assistant\n')
    return prompt


def postprocess_prompt_and_generated_text(model_type: CaptionModelType,
                                          processor, prompt: str,
                                          generated_text: str) -> tuple:
    if model_type == CaptionModelType.COGAGENT:
        prompt = f'<EOI>Question: {prompt} Answer:'
    elif model_type == CaptionModelType.COGVLM:
        prompt = f'Question: {prompt} Answer:'
    elif model_type == CaptionModelType.KOSMOS:
        generated_text, _ = processor.post_process_generation(
            generated_text)
        prompt = prompt.replace('<grounding>', '')
    elif model_type in (CaptionModelType.LLAVA_1_5,
                        CaptionModelType.LLAVA_NEXT_MISTRAL):
        prompt = prompt.replace('<image>', ' ')
    elif model_type == CaptionModelType.LLAVA_NEXT_VICUNA:
        prompt = prompt.replace('<image>', '')
    elif model_type == CaptionModelType.LLAVA_LLAMA_3:
        prompt = prompt.replace('<|start_header_id|>', '')
        prompt = prompt.replace('<|end_header_id|>', '')
        prompt = prompt.replace('<image>', '')
        prompt = prompt.replace('<|eot_id|>', '')
    elif model_type == CaptionModelType.LLAVA_NEXT_34B:
        prompt = prompt.replace('<|im_start|>', '<|im_start|> ')
        prompt = prompt.replace('<|im_end|>', '')
        prompt = prompt.replace('<image>', ' ')
    elif model_type in (CaptionModelType.MOONDREAM1,
                        CaptionModelType.MOONDREAM2):
        generated_text = re.sub('END$', '', generated_text)
        generated_text = re.sub('<$', '', generated_text)
    elif model_type == CaptionModelType.XCOMPOSER2:
        generated_text = generated_text.split('[UNUSED_TOKEN_145]')[0]
    return prompt, generated_text
