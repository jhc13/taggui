from auto_captioning.auto_captioning_model import AutoCaptioningModel
from auto_captioning.models.florence_2 import Florence2, Florence2Promptgen
from auto_captioning.models.joycaption import Joycaption
from auto_captioning.models.kosmos_2 import Kosmos2
from auto_captioning.models.llava_1_point_5 import Llava1Point5
from auto_captioning.models.llava_llama_3 import LlavaLlama3
from auto_captioning.models.local_server import (LM_STUDIO_MODEL_ID,
                                                 OLLAMA_MODEL_ID,
                                                 LmStudioModel, OllamaModel)
from auto_captioning.models.llava_next import (LlavaNext34b, LlavaNextMistral,
                                               LlavaNextVicuna)
from auto_captioning.models.moondream import Moondream1, Moondream2
from auto_captioning.models.phi_3_vision import Phi3Vision
from auto_captioning.models.wd_tagger import WdTagger

MODELS = [
    LM_STUDIO_MODEL_ID,
    OLLAMA_MODEL_ID,
    'fancyfeast/llama-joycaption-beta-one-hf-llava',
    'microsoft/Florence-2-large-ft',
    'microsoft/Florence-2-large',
    'microsoft/Florence-2-base-ft',
    'microsoft/Florence-2-base',
    'MiaoshouAI/Florence-2-large-PromptGen-v2.0',
    'MiaoshouAI/Florence-2-base-PromptGen-v2.0',
    'microsoft/Phi-3-vision-128k-instruct',
    'llava-hf/llava-v1.6-mistral-7b-hf',
    'llava-hf/llava-v1.6-vicuna-7b-hf',
    'llava-hf/llava-v1.6-vicuna-13b-hf',
    'llava-hf/llava-v1.6-34b-hf',
    'xtuner/llava-llama-3-8b-v1_1-transformers',
    'vikhyatk/moondream2',
    'vikhyatk/moondream1',
    'SmilingWolf/wd-eva02-large-tagger-v3',
    'SmilingWolf/wd-vit-large-tagger-v3',
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


def get_model_class(model_id: str) -> type[AutoCaptioningModel]:
    if model_id == LM_STUDIO_MODEL_ID:
        return LmStudioModel
    if model_id == OLLAMA_MODEL_ID:
        return OllamaModel
    lowercase_model_id = model_id.lower()
    if 'florence' in lowercase_model_id:
        if 'promptgen' in lowercase_model_id:
            return Florence2Promptgen
        return Florence2
    if 'joycaption' in lowercase_model_id:
        return Joycaption
    if 'kosmos' in lowercase_model_id:
        return Kosmos2
    if 'llava-v1.6-34b' in lowercase_model_id:
        return LlavaNext34b
    if 'llava-v1.6-mistral' in lowercase_model_id:
        return LlavaNextMistral
    if 'llava-v1.6-vicuna' in lowercase_model_id:
        return LlavaNextVicuna
    if 'llava-llama-3' in lowercase_model_id:
        return LlavaLlama3
    if 'llava' in lowercase_model_id:
        return Llava1Point5
    if 'moondream1' in lowercase_model_id:
        return Moondream1
    if 'moondream2' in lowercase_model_id:
        return Moondream2
    if 'phi-3' in lowercase_model_id:
        return Phi3Vision
    if 'wd' in lowercase_model_id and 'tagger' in lowercase_model_id:
        return WdTagger
    return AutoCaptioningModel
