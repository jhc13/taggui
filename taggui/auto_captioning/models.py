from utils.enums import CaptionModelType

MODELS = [
    'internlm/internlm-xcomposer2-vl-7b-4bit',
    'internlm/internlm-xcomposer2-vl-7b',
    'THUDM/cogvlm2-llama3-chat-19B-int4',
    'THUDM/cogvlm-chat-hf',
    'THUDM/cogagent-vqa-hf',
    'llava-hf/llava-v1.6-mistral-7b-hf',
    'llava-hf/llava-v1.6-vicuna-7b-hf',
    'llava-hf/llava-v1.6-vicuna-13b-hf',
    'llava-hf/llava-v1.6-34b-hf',
    'xtuner/llava-llama-3-8b-v1_1-transformers',
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
    'microsoft/kosmos-2-patch14-224'
]


def get_model_type(model_id: str) -> CaptionModelType:
    lowercase_model_id = model_id.lower()
    if 'cogagent' in lowercase_model_id:
        return CaptionModelType.COGAGENT
    if 'cogvlm2' in lowercase_model_id:
        return CaptionModelType.COGVLM2
    if 'cogvlm' in lowercase_model_id:
        return CaptionModelType.COGVLM
    if 'kosmos' in lowercase_model_id:
        return CaptionModelType.KOSMOS
    if 'llava-v1.6-34b' in lowercase_model_id:
        return CaptionModelType.LLAVA_NEXT_34B
    if 'llava-v1.6-mistral' in lowercase_model_id:
        return CaptionModelType.LLAVA_NEXT_MISTRAL
    if 'llava-v1.6-vicuna' in lowercase_model_id:
        return CaptionModelType.LLAVA_NEXT_VICUNA
    if 'llava-llama-3' in lowercase_model_id:
        return CaptionModelType.LLAVA_LLAMA_3
    if 'llava' in lowercase_model_id:
        return CaptionModelType.LLAVA_1_5
    if 'moondream1' in lowercase_model_id:
        return CaptionModelType.MOONDREAM1
    if 'moondream2' in lowercase_model_id:
        return CaptionModelType.MOONDREAM2
    if 'wd' in lowercase_model_id and 'tagger' in lowercase_model_id:
        return CaptionModelType.WD_TAGGER
    if 'xcomposer2' in lowercase_model_id:
        return CaptionModelType.XCOMPOSER2
    return CaptionModelType.OTHER
