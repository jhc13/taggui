from auto_captioning.auto_captioning_model import AutoCaptioningModel


class Llava1Point5(AutoCaptioningModel):
    @staticmethod
    def get_default_prompt() -> str:
        return 'Describe the image in twenty words or less.'

    @staticmethod
    def format_prompt(prompt: str) -> str:
        return f'USER: <image>\n{prompt}\nASSISTANT:'

    @staticmethod
    def postprocess_image_prompt(image_prompt: str) -> str:
        return image_prompt.replace('<image>', ' ')
