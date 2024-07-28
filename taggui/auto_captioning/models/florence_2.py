from transformers import AutoModelForCausalLM

from auto_captioning.auto_captioning_model import AutoCaptioningModel
from utils.utils import list_with_and

TASK_PROMPTS = [
    '<CAPTION>',
    '<DETAILED_CAPTION>',
    '<MORE_DETAILED_CAPTION>',
    '<OCR>'
]

DEFAULT_PROMPT = TASK_PROMPTS[2]


class Florence2(AutoCaptioningModel):
    transformers_model_class = AutoModelForCausalLM

    def get_additional_error_message(self) -> str | None:
        if self.prompt and self.prompt not in TASK_PROMPTS:
            quoted_task_prompts = [f'"{task_prompt}"'
                                   for task_prompt in TASK_PROMPTS]
            return (f'This model only supports the following prompts: '
                    f'{list_with_and(quoted_task_prompts)}. The default '
                    f'prompt is "{DEFAULT_PROMPT}".')
        if self.caption_start:
            return 'This model does not support `Start caption with`.'
        return None

    @staticmethod
    def get_default_prompt() -> str:
        return DEFAULT_PROMPT
