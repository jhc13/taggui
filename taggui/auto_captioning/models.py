from auto_captioning.enums import ModelType

MODELS = [
    'internlm/internlm-xcomposer2-vl-7b-4bit',
    'internlm/internlm-xcomposer2-vl-7b',
    'THUDM/cogagent-vqa-hf',
    'THUDM/cogvlm-chat-hf',
    'llava-hf/llava-v1.6-mistral-7b-hf',
    'llava-hf/llava-v1.6-vicuna-7b-hf',
    'llava-hf/llava-v1.6-vicuna-13b-hf',
    'llava-hf/llava-v1.6-34b-hf',
    'vikhyatk/moondream2',
    'vikhyatk/moondream1',
    'SmilingWolf/wd-swinv2-tagger-v3',
    'SmilingWolf/wd-convnext-tagger-v3',
    'SmilingWolf/wd-vit-tagger-v3',
    'SmilingWolf/wd-v1-4-moat-tagger-v2',
    'SmilingWolf/wd-v1-4-swinv2-tagger-v2',
    'SmilingWolf/wd-v1-4-convnext-tagger-v2',
    'SmilingWolf/wd-v1-4-convnextv2-tagger-v2',
    'SmilingWolf/wd-v1-4-vit-tagger-v2',
    'llava-hf/llava-1.5-7b-hf',
    'llava-hf/llava-1.5-13b-hf',
    'llava-hf/bakLlava-v1-hf',
    'Salesforce/instructblip-vicuna-7b',
    'Salesforce/instructblip-vicuna-13b',
    'Salesforce/instructblip-flan-t5-xl',
    'Salesforce/instructblip-flan-t5-xxl',
    'Salesforce/blip2-opt-2.7b',
    'Salesforce/blip2-opt-6.7b',
    'Salesforce/blip2-opt-6.7b-coco',
    'Salesforce/blip2-flan-t5-xl',
    'Salesforce/blip2-flan-t5-xxl',
    'microsoft/kosmos-2-patch14-224',
]


def get_model_type(model_id: str) -> ModelType:
    lowercase_model_id = model_id.lower()
    if 'cogagent' in lowercase_model_id:
        return ModelType.COGAGENT
    if 'cogvlm' in lowercase_model_id:
        return ModelType.COGVLM
    if 'kosmos' in lowercase_model_id:
        return ModelType.KOSMOS
    if 'llava' in lowercase_model_id and '1.6' not in lowercase_model_id:
        return ModelType.LLAVA_1_5
    if 'llava-v1.6-34b' in lowercase_model_id:
        return ModelType.LLAVA_NEXT_34B
    if 'llava-v1.6-mistral' in lowercase_model_id:
        return ModelType.LLAVA_NEXT_MISTRAL
    if 'llava-v1.6-vicuna' in lowercase_model_id:
        return ModelType.LLAVA_NEXT_VICUNA
    if 'moondream' in lowercase_model_id:
        return ModelType.MOONDREAM
    if 'wd' in lowercase_model_id and 'tagger' in lowercase_model_id:
        return ModelType.WD_TAGGER
    if 'xcomposer2' in lowercase_model_id:
        return ModelType.XCOMPOSER2
    return ModelType.OTHER
