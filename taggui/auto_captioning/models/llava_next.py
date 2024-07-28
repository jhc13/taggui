from auto_captioning.auto_captioning_model import AutoCaptioningModel


class LlavaNext(AutoCaptioningModel):
    def get_processor(self):
        processor = super().get_processor()
        processor.tokenizer.padding_side = 'left'
        return processor

    @staticmethod
    def get_default_prompt() -> str:
        return 'Describe the image in one sentence.'


class LlavaNext34b(LlavaNext):
    @staticmethod
    def format_prompt(prompt: str) -> str:
        return (f'<|im_start|>system\nAnswer the questions.<|im_end|>'
                f'<|im_start|>user\n<image>\n{prompt}<|im_end|>'
                f'<|im_start|>assistant\n')

    def get_input_text(self, image_prompt: str) -> str:
        return image_prompt + self.caption_start

    @staticmethod
    def postprocess_image_prompt(image_prompt: str) -> str:
        image_prompt = image_prompt.replace('<|im_start|>', '<|im_start|> ')
        image_prompt = image_prompt.replace('<|im_end|>', '')
        image_prompt = image_prompt.replace('<image>', ' ')
        return image_prompt


class LlavaNextMistral(LlavaNext):
    @staticmethod
    def format_prompt(prompt: str) -> str:
        return f'[INST] <image>\n{prompt} [/INST]'

    @staticmethod
    def postprocess_image_prompt(image_prompt: str) -> str:
        return image_prompt.replace('<image>', ' ')


class LlavaNextVicuna(LlavaNext):
    @staticmethod
    def format_prompt(prompt: str) -> str:
        return (f"A chat between a curious human and an artificial "
                f"intelligence assistant. The assistant gives helpful, "
                f"detailed, and polite answers to the human's questions. "
                f"USER: <image>\n{prompt} ASSISTANT:")

    @staticmethod
    def postprocess_image_prompt(image_prompt: str) -> str:
        return image_prompt.replace('<image>', '')
