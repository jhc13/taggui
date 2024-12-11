from auto_captioning.auto_captioning_model import AutoCaptioningModel
import auto_captioning.captioning_thread as captioning_thread

from utils.image import Image
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
from torchvision import transforms

def find_closest_aspect_ratio(aspect_ratio, target_ratios, width, height, image_size):
    best_ratio_diff = float('inf')
    best_ratio = (1, 1)
    area = width * height
    for ratio in target_ratios:
        target_aspect_ratio = ratio[0] / ratio[1]
        ratio_diff = abs(aspect_ratio - target_aspect_ratio)
        if ratio_diff < best_ratio_diff:
            best_ratio_diff = ratio_diff
            best_ratio = ratio
        elif ratio_diff == best_ratio_diff:
            if area > 0.5 * image_size * image_size * ratio[0] * ratio[1]:
                best_ratio = ratio
    return best_ratio

def dynamic_preprocess(image, max_num, image_size, use_thumbnail=False):
    orig_width, orig_height = image.size
    aspect_ratio = orig_width / orig_height

    # calculate the existing image aspect ratio
    target_ratios = set(
        (i, j) for n in range(1, max_num + 1) for i in range(1, n + 1) for j in range(1, n + 1) if
        i * j <= max_num and i * j >= 1)
    target_ratios = sorted(target_ratios, key=lambda x: x[0] * x[1])

    # find the closest aspect ratio to the target
    target_aspect_ratio = find_closest_aspect_ratio(
        aspect_ratio, target_ratios, orig_width, orig_height, image_size)

    # calculate the target width and height
    target_width = image_size * target_aspect_ratio[0]
    target_height = image_size * target_aspect_ratio[1]
    blocks = target_aspect_ratio[0] * target_aspect_ratio[1]

    # resize the image
    resized_img = image.resize((target_width, target_height))
    processed_images = []
    for i in range(blocks):
        box = (
            (i % (target_width // image_size)) * image_size,
            (i // (target_width // image_size)) * image_size,
            ((i % (target_width // image_size)) + 1) * image_size,
            ((i // (target_width // image_size)) + 1) * image_size
        )
        # split the image
        split_img = resized_img.crop(box)
        processed_images.append(split_img)
    assert len(processed_images) == blocks
    if use_thumbnail and len(processed_images) != 1:
        thumbnail_img = image.resize((image_size, image_size))
        processed_images.append(thumbnail_img)
    return processed_images

class InternVL2(AutoCaptioningModel):
    transformers_model_class = AutoModelForCausalLM

    def __init__(self,
                 captioning_thread_: 'captioning_thread.CaptioningThread',
                 caption_settings: dict):
        super().__init__(captioning_thread_, caption_settings)

        if self.device.type == 'cuda':
            self.dtype = torch.float16
            self.dtype_argument = ({'dtype': self.dtype})
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
                         image_path: Image) -> dict:
        pil_image = self.load_image(image_path)
        target_image_size = self.model.config.vision_config.image_size

        transform = transforms.Compose([
            transforms.Resize(
                (target_image_size, target_image_size),
                interpolation=transforms.InterpolationMode.BICUBIC
            ),
            transforms.ToTensor(),
            transforms.Normalize((0.48145466, 0.4578275, 0.40821073),
                                 (0.26862954, 0.26130258, 0.27577711))
        ])

        # Break image down into (up to) 12 smaller pieces so we don't lose as much information
        # when resizing to our target size.
        images = dynamic_preprocess(pil_image, image_size=target_image_size, max_num=12)
        pixel_values = torch.stack([transform(image) for image in images]).to(self.device, self.dtype)

        return pixel_values

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
