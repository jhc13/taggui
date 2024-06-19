from utils.utils import list_with_and

TASK_PROMPTS = [
    '<CAPTION>',
    '<DETAILED_CAPTION>',
    '<MORE_DETAILED_CAPTION>',
    '<OCR>'
]

FLORENCE_2_DEFAULT_PROMPT = TASK_PROMPTS[2]


def get_florence_2_error_message(prompt: str,
                                 caption_start: str) -> str | None:
    if prompt and prompt not in TASK_PROMPTS:
        quoted_task_prompts = [f'"{task_prompt}"'
                               for task_prompt in TASK_PROMPTS]
        return (f'This model only supports the following prompts: '
                f'{list_with_and(quoted_task_prompts)}. The default prompt is '
                f'"{FLORENCE_2_DEFAULT_PROMPT}".')
    if caption_start:
        return 'This model does not support `Start caption with`.'
    return None
