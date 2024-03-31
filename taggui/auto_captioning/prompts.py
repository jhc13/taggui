import re

from auto_captioning.enums import ModelType


def get_default_prompt(model_type: ModelType) -> str:
    if model_type in (ModelType.COGAGENT, ModelType.COGVLM,
                      ModelType.LLAVA_1_5, ModelType.MOONDREAM):
        return 'Describe the image in twenty words or less.'
    if model_type in (ModelType.LLAVA_NEXT_34B, ModelType.LLAVA_NEXT_MISTRAL,
                      ModelType.LLAVA_NEXT_VICUNA):
        return 'Describe the image in one sentence.'
    if model_type == ModelType.XCOMPOSER2:
        return 'Concisely describe the image.'
    return ''


def format_prompt(prompt: str, model_type: ModelType) -> str:
    if model_type == ModelType.KOSMOS:
        return f'<grounding>{prompt}'
    if model_type == ModelType.LLAVA_1_5:
        return f'USER: <image>\n{prompt}\nASSISTANT:'
    if model_type == ModelType.LLAVA_NEXT_34B:
        return (f'<|im_start|>system\nAnswer the questions.<|im_end|>'
                f'<|im_start|>user\n<image>\n{prompt}<|im_end|>'
                f'<|im_start|>assistant\n')
    if model_type == ModelType.LLAVA_NEXT_MISTRAL:
        return f'[INST] <image>\n{prompt} [/INST]'
    if model_type == ModelType.LLAVA_NEXT_VICUNA:
        return (f"A chat between a curious human and an artificial "
                f"intelligence assistant. The assistant gives helpful, "
                f"detailed, and polite answers to the human's questions. "
                f"USER: <image>\n{prompt} ASSISTANT:")
    if model_type == ModelType.MOONDREAM:
        return f'<image>\n\nQuestion: {prompt}\n\nAnswer:'
    if model_type == ModelType.XCOMPOSER2:
        return (f'[UNUSED_TOKEN_146]user\n<ImageHere>{prompt}'
                f'[UNUSED_TOKEN_145]\n[UNUSED_TOKEN_146]assistant\n')
    return prompt


def postprocess_prompt_and_generated_text(model_type: ModelType, processor,
                                          prompt: str,
                                          generated_text: str) -> tuple:
    if model_type == ModelType.COGAGENT:
        prompt = f'<EOI>Question: {prompt} Answer:'
    elif model_type == ModelType.COGVLM:
        prompt = f'Question: {prompt} Answer:'
    elif model_type == ModelType.KOSMOS:
        generated_text, _ = processor.post_process_generation(
            generated_text)
        prompt = prompt.replace('<grounding>', '')
    elif model_type in (ModelType.LLAVA_1_5, ModelType.LLAVA_NEXT_MISTRAL,
                        ModelType.LLAVA_NEXT_VICUNA):
        prompt = prompt.replace('<image>', ' ')
    elif model_type == ModelType.LLAVA_NEXT_34B:
        prompt = prompt.replace('<|im_start|>', '<|im_start|> ')
        prompt = prompt.replace('<|im_end|>', '')
        prompt = prompt.replace('<image>', ' ')
    elif model_type == ModelType.MOONDREAM:
        generated_text = re.sub('END$', '', generated_text)
        generated_text = re.sub('<$', '', generated_text)
    elif model_type == ModelType.XCOMPOSER2:
        generated_text = generated_text.split('[UNUSED_TOKEN_145]')[0]
    return prompt, generated_text
