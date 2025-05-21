import numpy as np
from transformers import AutoModelForCausalLM, BatchFeature

from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.image import Image
from utils.utils import list_with_and


class Florence2(AutoCaptioningModel):
    use_safetensors = None
    transformers_model_class = AutoModelForCausalLM
    task_prompts = [
        '<CAPTION>',
        '<DETAILED_CAPTION>',
        '<MORE_DETAILED_CAPTION>',
        '<OCR>'
    ]
    default_prompt = task_prompts[2]

    def get_additional_error_message(self) -> str | None:
        if self.prompt and self.prompt not in self.task_prompts:
            quoted_task_prompts = [f'"{task_prompt}"'
                                   for task_prompt in self.task_prompts]
            return (f'This model only supports the following prompts: '
                    f'{list_with_and(quoted_task_prompts)}. The default '
                    f'prompt is "{self.default_prompt}".')
        if self.caption_start:
            return 'This model does not support `Start caption with`.'
        return None

    def get_default_prompt(self) -> str:
        return self.default_prompt


class Florence2Promptgen(Florence2):
    use_safetensors = True
    task_prompts = [
        '<GENERATE_TAGS>',
        '<CAPTION>',
        '<DETAILED_CAPTION>',
        '<MORE_DETAILED_CAPTION>',
        '<ANALYZE>',
        '<MIXED_CAPTION>',
        '<MIXED_CAPTION_PLUS>',
    ]
    default_prompt = task_prompts[1]

    def get_model_inputs(self, image_prompt: str,
                         image: Image) -> BatchFeature | dict | np.ndarray:
        model_inputs = super().get_model_inputs(image_prompt, image)
        model_inputs = {
            'input_ids': model_inputs['input_ids'],
            'pixel_values': model_inputs['pixel_values'],
        }
        return model_inputs
