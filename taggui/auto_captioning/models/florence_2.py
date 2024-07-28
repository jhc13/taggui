from transformers import AutoModelForCausalLM

from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.utils import list_with_and


class Florence2(AutoCaptioningModel):
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
    task_prompts = [
        '<GENERATE_PROMPT>',
        '<CAPTION>',
        '<DETAILED_CAPTION>',
        '<MORE_DETAILED_CAPTION>'
    ]
    default_prompt = task_prompts[0]
