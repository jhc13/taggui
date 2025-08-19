import gc
import re
from contextlib import nullcontext
from datetime import datetime

import numpy as np
import torch
import pillow_jxl
from PIL import Image as PilImage
from PIL.ImageOps import exif_transpose
from transformers import (AutoModelForVision2Seq, AutoProcessor,
                          BatchFeature, BitsAndBytesConfig)
from transformers.utils.import_utils import is_torch_bf16_gpu_available

import auto_captioning.captioning_thread as captioning_thread
from utils.enums import CaptionDevice
from utils.image import Image


def replace_template_variable(match: re.Match, image: Image, skip_hash: bool) -> str:
    template_variable = match.group(0)[1:-1].lower()
    if template_variable == 'tags':
        if skip_hash:
            return ', '.join([t for t in image.tags if not t.startswith('#')])
        else:
            return ', '.join(image.tags)
    if template_variable == 'name':
        return image.path.stem
    if template_variable in ('directory', 'folder'):
        return image.path.parent.name


def replace_template_variables(text: str, image: Image, skip_hash: bool) -> str:
    # Replace template variables inside curly braces that are not escaped.
    text = re.sub(r'(?<!\\){[^{}]+(?<!\\)}',
                  lambda match: replace_template_variable(match, image, skip_hash), text)
    # Unescape escaped curly braces.
    text = re.sub(r'\\([{}])', r'\1', text)
    return text


class AutoCaptioningModel:
    dtype = torch.float16
    # When loading a model, if the `use_safetensors` argument is not set and
    # both a safetensors and a non-safetensors version of the model are
    # available, both versions get downloaded. This should be set to `None` for
    # models that do not have a safetensors version.
    use_safetensors = True
    model_load_context_manager = nullcontext()
    transformers_model_class = AutoModelForVision2Seq
    image_mode = 'RGB'

    def __init__(self,
                 captioning_thread_: 'captioning_thread.CaptioningThread',
                 caption_settings: dict):
        self.thread = captioning_thread_
        self.thread_parent = captioning_thread_.parent()
        self.caption_settings = caption_settings
        self.model_id = caption_settings['model_id']
        self.prompt = caption_settings['prompt']
        self.skip_hash = caption_settings['skip_hash']
        self.caption_start = caption_settings['caption_start']
        self.device_setting: CaptionDevice = caption_settings['device']
        self.device: torch.device = self.get_device()
        if self.dtype == torch.bfloat16:
            if self.device.type != 'cuda' or not is_torch_bf16_gpu_available():
                self.dtype = torch.float16
        self.dtype_argument = ({'dtype': self.dtype}
                               if self.device.type == 'cuda' else {})
        self.load_in_4_bit = caption_settings['load_in_4_bit']
        self.bad_words_string = caption_settings['bad_words']
        self.forced_words_string = caption_settings['forced_words']
        self.remove_tag_separators = caption_settings['remove_tag_separators']
        self.generation_parameters = caption_settings['generation_parameters']
        self.beam_count = self.generation_parameters['num_beams']
        self.processor = None
        self.model = None
        self.tokenizer = None

    def get_device(self) -> torch.device:
        if (self.device_setting == CaptionDevice.GPU
                and torch.cuda.is_available()):
            gpu_index = self.caption_settings['gpu_index']
            device = torch.device(f'cuda:{gpu_index}')
        else:
            device = torch.device('cpu')
        return device

    def get_additional_error_message(self) -> str | None:
        return None

    def get_error_message(self) -> str | None:
        if self.forced_words_string.strip() and self.beam_count < 2:
            return ('`Number of beams` must be greater than 1 when `Include '
                    'in caption` is not empty.')
        return self.get_additional_error_message()

    def get_processor(self):
        return AutoProcessor.from_pretrained(self.model_id,
                                             trust_remote_code=True)

    def get_model_load_arguments(self) -> dict:
        arguments = {'device_map': self.device, 'trust_remote_code': True,
                     'use_safetensors': self.use_safetensors}
        if self.load_in_4_bit:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type='nf4',
                bnb_4bit_compute_dtype=self.dtype,
                bnb_4bit_quant_storage=self.dtype,
                bnb_4bit_use_double_quant=True
            )
            arguments['quantization_config'] = quantization_config
        if self.device.type == 'cuda':
            arguments['torch_dtype'] = self.dtype
        return arguments

    def load_model(self, model_load_arguments: dict):
        with self.model_load_context_manager:
            model = self.transformers_model_class.from_pretrained(
                self.model_id, **model_load_arguments)
        model.eval()
        return model

    def patch_source_code(self) -> bool:
        # Return `True` if the source code was patched.
        return False

    def get_model(self):
        model_load_arguments = self.get_model_load_arguments()
        model = self.load_model(model_load_arguments)
        if self.patch_source_code():
            print('Patched the model source code. Reloading the model...')
            model = self.load_model(model_load_arguments)
        return model

    def load_processor_and_model(self):
        models_directory_path = self.thread.models_directory_path
        if models_directory_path:
            config_path = models_directory_path / self.model_id / 'config.json'
            tags_path = (models_directory_path / self.model_id
                         / 'selected_tags.csv')
            if config_path.is_file() or tags_path.is_file():
                self.model_id = str(models_directory_path / self.model_id)
        # If the processor and model were previously loaded, use them.
        processor = self.thread_parent.processor
        model = self.thread_parent.model
        # Only GPUs support 4-bit quantization.
        self.load_in_4_bit = self.load_in_4_bit and self.device.type == 'cuda'
        if (model and self.thread_parent.model_id == self.model_id
                and (self.thread_parent.model_device_type
                     == self.device.type)
                and (self.thread_parent.is_model_loaded_in_4_bit
                     == self.load_in_4_bit)):
            self.processor = processor
            self.model = model
            return
        # Load the new processor and model.
        if model:
            # Garbage collect the previous processor and model to free up
            # memory.
            self.thread_parent.processor = None
            self.thread_parent.model = None
            del processor
            del model
            gc.collect()
        self.thread.clear_console_text_edit_requested.emit()
        print(f'Loading {self.model_id}...')
        self.processor = self.get_processor()
        self.thread_parent.processor = self.processor
        self.model = self.get_model()
        self.thread_parent.model = self.model
        self.thread_parent.model_id = self.model_id
        self.thread_parent.model_device_type = self.device.type
        self.thread_parent.is_model_loaded_in_4_bit = self.load_in_4_bit

    def monkey_patch_after_loading(self):
        return

    @staticmethod
    def get_generation_text() -> str:
        return 'Captioning'

    @staticmethod
    def get_default_prompt() -> str:
        return ''

    @staticmethod
    def format_prompt(prompt: str) -> str:
        return prompt

    def get_image_prompt(self, image: Image) -> str | None:
        if self.prompt:
            image_prompt = replace_template_variables(self.prompt, image,
                                                      self.skip_hash)
        else:
            self.prompt = self.get_default_prompt()
            image_prompt = self.prompt
        image_prompt = self.format_prompt(image_prompt)
        return image_prompt

    def get_input_text(self, image_prompt: str) -> str:
        if image_prompt and self.caption_start:
            text = f'{image_prompt} {self.caption_start}'
        else:
            text = image_prompt or self.caption_start
        return text

    def load_image(self, image: Image, crop: bool) -> PilImage:
        pil_image = PilImage.open(image.path)
        # Rotate the image according to the orientation tag.
        pil_image = exif_transpose(pil_image)
        pil_image = pil_image.convert(self.image_mode)
        if crop and image.crop is not None:
            pil_image = pil_image.crop(image.crop.getCoords())
        return pil_image

    def get_model_inputs(self, image_prompt: str, image: Image,
                         crop: bool) -> BatchFeature | dict | np.ndarray:
        text = self.get_input_text(image_prompt)
        pil_image = self.load_image(image, crop)
        model_inputs = (self.processor(text=text, images=pil_image,
                                       return_tensors='pt')
                        .to(self.device, **self.dtype_argument))
        return model_inputs

    def get_generation_model(self):
        return self.model

    def get_tokenizer(self):
        return self.processor.tokenizer

    def get_bad_words_ids(self) -> list[list[int]] | None:
        if not self.bad_words_string.strip():
            return None
        words = re.split(r'(?<!\\),', self.bad_words_string)
        words = [word.strip() for word in words if word.strip()]
        if not words:
            return None
        words = [word.replace(r'\,', ',') for word in words]
        # Also discourage generating the versions of the words with spaces
        # before them.
        words += [' ' + word for word in words]
        bad_words_ids = self.tokenizer(words,
                                       add_special_tokens=False).input_ids
        return bad_words_ids

    def get_forced_words_ids(self) -> list[list[list[int]]] | None:
        if not self.forced_words_string.strip():
            return None
        word_groups = re.split(r'(?<!\\),', self.forced_words_string)
        forced_words_ids = []
        for word_group in word_groups:
            word_group = word_group.strip().replace(r'\,', ',')
            words = re.split(r'(?<!\\)\|', word_group)
            words = [word.strip() for word in words if word.strip()]
            if not words:
                continue
            words = [word.replace(r'\|', '|') for word in words]
            words_ids = self.tokenizer(words,
                                       add_special_tokens=False).input_ids
            forced_words_ids.append(words_ids)
        if not forced_words_ids:
            return None
        return forced_words_ids

    @staticmethod
    def get_additional_generation_parameters() -> dict:
        return {}

    @staticmethod
    def postprocess_image_prompt(image_prompt: str) -> str:
        return image_prompt

    @staticmethod
    def postprocess_generated_text(generated_text: str) -> str:
        return generated_text

    def get_caption_from_generated_tokens(
            self, generated_token_ids: torch.Tensor, image_prompt: str) -> str:
        generated_text = self.processor.batch_decode(
            generated_token_ids, skip_special_tokens=True)[0]
        image_prompt = self.postprocess_image_prompt(image_prompt)
        generated_text = self.postprocess_generated_text(generated_text)
        if image_prompt.strip() and generated_text.startswith(image_prompt):
            caption = generated_text[len(image_prompt):]
        elif (self.caption_start.strip()
              and generated_text.startswith(self.caption_start)):
            caption = generated_text
        else:
            caption = f'{self.caption_start.strip()} {generated_text.strip()}'
        caption = caption.strip()
        if self.remove_tag_separators:
            caption = caption.replace(self.thread.tag_separator, ' ')
        return caption

    def generate_caption(self, model_inputs: BatchFeature | dict | np.ndarray,
                         image_prompt: str) -> tuple[str, str]:
        generation_model = self.get_generation_model()
        self.tokenizer = self.get_tokenizer()
        bad_words_ids = self.get_bad_words_ids()
        forced_words_ids = self.get_forced_words_ids()
        additional_generation_parameters = (
            self.get_additional_generation_parameters())
        with torch.inference_mode():
            generated_token_ids = generation_model.generate(
                **model_inputs, bad_words_ids=bad_words_ids,
                force_words_ids=forced_words_ids, **self.generation_parameters,
                **additional_generation_parameters)
        caption = self.get_caption_from_generated_tokens(generated_token_ids,
                                                         image_prompt)
        console_output_caption = caption
        return caption, console_output_caption
