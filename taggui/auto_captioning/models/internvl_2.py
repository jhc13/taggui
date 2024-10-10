from auto_captioning.auto_captioning_model import AutoCaptioningModel
import auto_captioning.captioning_thread as captioning_thread

from utils.image import Image
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
from torchvision import transforms

class InternVL2(AutoCaptioningModel):
    transformers_model_class = AutoModelForCausalLM

    def __init__(self,
                 captioning_thread_: 'captioning_thread.CaptioningThread',
                 caption_settings: dict):
        super().__init__(captioning_thread_, caption_settings)

        if self.device.type == 'cuda':
            self.dtype = torch.float16
            self.dtype_argument = ({'dtype': torch.float16})
        else:
            self.dtype = None
            self.dtype_argument = ({})

    def get_additional_error_message(self) -> str | None:
        if self.beam_count > 1:
            return 'This model only supports `Number of beams` set to 1.'
        return None

    def get_processor(self):
        processor = AutoTokenizer.from_pretrained(self.model_id,
                                                  trust_remote_code=True,
                                                  use_fast=False)
        return processor

    def get_tokenizer(self):
        return self.processor

    @staticmethod
    def get_default_prompt() -> str:
        return 'Please describe the image shortly.'

    @staticmethod
    def format_prompt(prompt: str) -> str:
        return (f'<image>\n{prompt}')

    # Returns only the Image Pixels for generation
    def get_model_inputs(self,
                         image_prompt: str,
                         image: Image) -> dict:
        pil_image = self.load_image(image)
        image_size = self.model.config.vision_config.image_size
        transform = transforms.Compose([
            transforms.Resize(
                (image_size, image_size),
                interpolation=transforms.InterpolationMode.BICUBIC
            ),
            transforms.ToTensor(),
            transforms.Normalize((0.48145466, 0.4578275, 0.40821073),
                                 (0.26862954, 0.26130258, 0.27577711))
        ])
        image = transform(pil_image)
        inputs = torch.stack([image.to(self.device, self.dtype)])
        return inputs

    # Generates a caption from the model via chat
    def generate_caption(self,
                         model_inputs: dict,
                         image_prompt: str) -> tuple[str, str]:
        self.tokenizer = self.get_tokenizer()

        generation_model = self.get_generation_model()
        bad_words_ids = self.get_bad_words_ids()
        forced_words_ids = self.get_forced_words_ids()
        additional_generation_parameters = (self.get_additional_generation_parameters())

        generation_config = dict(
            bad_words_ids=bad_words_ids,
            force_words_ids=forced_words_ids,
            **self.generation_parameters,
            **additional_generation_parameters)

        with torch.inference_mode():
            response = generation_model.chat(tokenizer=self.tokenizer,
                                             pixel_values=model_inputs,
                                             question=image_prompt,
                                             generation_config=generation_config,
                                             history=None,
                                             return_history=False)

        console_output_caption = response
        return response, console_output_caption
