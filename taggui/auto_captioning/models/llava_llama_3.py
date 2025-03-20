from transformers import AutoConfig, AutoProcessor

from auto_captioning.auto_captioning_model import AutoCaptioningModel


class LlavaLlama3(AutoCaptioningModel):
    def get_processor(self):
        config = AutoConfig.from_pretrained(self.model_id)
        patch_size = config.vision_config.patch_size
        return AutoProcessor.from_pretrained(
            self.model_id, trust_remote_code=True, patch_size=patch_size)

    @staticmethod
    def get_default_prompt() -> str:
        return 'Describe the image in one sentence.'

    @staticmethod
    def format_prompt(prompt: str) -> str:
        return (f'<|start_header_id|>user<|end_header_id|>\n\n<image>\n'
                f'{prompt}<|eot_id|><|start_header_id|>assistant'
                f'<|end_header_id|>\n\n')

    def get_input_text(self, image_prompt: str) -> str:
        return image_prompt + self.caption_start

    def get_additional_generation_parameters(self) -> dict:
        eos_token_id = (self.tokenizer('<|eot_id|>', add_special_tokens=False)
                        .input_ids)[0]
        return {'eos_token_id': eos_token_id}

    @staticmethod
    def postprocess_image_prompt(image_prompt: str) -> str:
        image_prompt = image_prompt.replace('<|start_header_id|>', '')
        image_prompt = image_prompt.replace('<|end_header_id|>', '')
        image_prompt = image_prompt.replace('<image>', '')
        image_prompt = image_prompt.replace('<|eot_id|>', '')
        return image_prompt
