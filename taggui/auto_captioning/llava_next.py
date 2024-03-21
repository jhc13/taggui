from auto_captioning.enums import ModelType


def get_llava_next_formatted_prompt(model_type: ModelType, prompt: str) -> str:
    if model_type == ModelType.LLAVA_NEXT_34B:
        return (f'<|im_start|>system\nAnswer the questions.<|im_end|>'
                f'<|im_start|>user\n<image>\n{prompt}<|im_end|><|im_start|>'
                f'assistant\n')
    if model_type == ModelType.LLAVA_NEXT_MISTRAL:
        return f'[INST] <image>\n{prompt} [/INST]'
    if model_type == ModelType.LLAVA_NEXT_VICUNA:
        return (f"A chat between a curious human and an artificial "
                f"intelligence assistant. The assistant gives helpful, "
                f"detailed, and polite answers to the human's questions. "
                f"USER: <image>\n{prompt} ASSISTANT:")
    return prompt
