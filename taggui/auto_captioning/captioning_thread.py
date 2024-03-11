import gc
import re
import sys
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from time import perf_counter

import torch
from PIL import Image as PilImage, UnidentifiedImageError
from PIL.ImageOps import exif_transpose
from PySide6.QtCore import QModelIndex, QThread, Qt, Signal
from transformers import (AutoModelForCausalLM, AutoModelForVision2Seq,
                          AutoProcessor, AutoTokenizer, BatchFeature,
                          BitsAndBytesConfig, CodeGenTokenizerFast,
                          LlamaTokenizer)

from auto_captioning.cogvlm_cogagent import (get_cogvlm_cogagent_inputs,
                                             monkey_patch_cogagent,
                                             monkey_patch_cogvlm,
                                             monkey_patch_quantizer)
from auto_captioning.enums import CaptionPosition, Device, ModelType
from auto_captioning.models import get_model_type
from auto_captioning.moondream import (get_moondream_error_message,
                                       get_moondream_inputs,
                                       monkey_patch_moondream1)
from auto_captioning.xcomposer2 import (InternLMXComposer2QuantizedForCausalLM,
                                        get_xcomposer2_error_message,
                                        get_xcomposer2_inputs)
from models.image_list_model import ImageListModel
from utils.image import Image


def get_forced_words_ids(forced_words_string: str, model_type: ModelType,
                         processor) -> list[list[list[int]]] | None:
    if not forced_words_string.strip():
        return None
    tokenizer = (processor
                 if model_type in (ModelType.COGVLM, ModelType.COGAGENT,
                                   ModelType.XCOMPOSER2)
                 else processor.tokenizer)
    word_groups = re.split(r'(?<!\\),', forced_words_string)
    forced_words_ids = []
    for word_group in word_groups:
        word_group = word_group.strip().replace(r'\,', ',')
        words = re.split(r'(?<!\\)\|', word_group)
        words = [word.strip().replace(r'\|', '|') for word in words]
        words_ids = tokenizer(words, add_special_tokens=False).input_ids
        forced_words_ids.append(words_ids)
    return forced_words_ids


def add_caption_to_tags(tags: list[str], caption: str,
                        caption_position: CaptionPosition) -> list[str]:
    if caption_position == CaptionPosition.DO_NOT_ADD:
        return tags
    # Make a copy of the tags so that the tags in the image list model are not
    # modified.
    tags = tags.copy()
    if caption_position == CaptionPosition.BEFORE_FIRST_TAG:
        tags.insert(0, caption)
    elif caption_position == CaptionPosition.AFTER_LAST_TAG:
        tags.append(caption)
    elif caption_position == CaptionPosition.OVERWRITE_FIRST_TAG:
        if tags:
            tags[0] = caption
        else:
            tags.append(caption)
    elif caption_position == CaptionPosition.OVERWRITE_ALL_TAGS:
        tags = [caption]
    return tags


class CaptioningThread(QThread):
    text_outputted = Signal(str)
    clear_console_text_edit_requested = Signal()
    # The image index, the caption, and the tags with the caption added. The
    # third parameter must be declared as `list` instead of `list[str]` for it
    # to work.
    caption_generated = Signal(QModelIndex, str, list)
    progress_bar_update_requested = Signal(int)

    def __init__(self, parent, image_list_model: ImageListModel,
                 selected_image_indices: list[QModelIndex],
                 caption_settings: dict, tag_separator: str,
                 models_directory_path: Path | None):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.selected_image_indices = selected_image_indices
        self.caption_settings = caption_settings
        self.tag_separator = tag_separator
        self.models_directory_path = models_directory_path

    def load_processor_and_model(self, device: torch.device,
                                 model_type: ModelType) -> tuple:
        # If the processor and model were previously loaded, use them.
        processor = self.parent().processor
        model = self.parent().model
        model_id = self.caption_settings['model']
        # Only GPUs support 4-bit quantization.
        load_in_4_bit = (self.caption_settings['load_in_4_bit']
                         and device.type == 'cuda')
        if self.models_directory_path:
            config_path = self.models_directory_path / model_id / 'config.json'
            if config_path.is_file():
                model_id = str(self.models_directory_path / model_id)
        if (model and self.parent().model_id == model_id
                and self.parent().model_device_type == device.type
                and self.parent().is_model_loaded_in_4_bit == load_in_4_bit):
            return processor, model
        # Load the new processor and model.
        if model:
            # Garbage collect the previous processor and model to free up
            # memory.
            self.parent().processor = None
            self.parent().model = None
            del processor
            del model
            gc.collect()
        self.clear_console_text_edit_requested.emit()
        print(f'Loading {model_id}...')
        if model_type in (ModelType.COGVLM, ModelType.COGAGENT):
            processor = LlamaTokenizer.from_pretrained('lmsys/vicuna-7b-v1.5')
        else:
            if model_type == ModelType.XCOMPOSER2:
                processor_class = AutoTokenizer
            elif model_type == ModelType.MOONDREAM:
                processor_class = CodeGenTokenizerFast
            else:
                processor_class = AutoProcessor
            processor = processor_class.from_pretrained(model_id,
                                                        trust_remote_code=True)
        self.parent().processor = processor
        if (model_type in (ModelType.COGVLM, ModelType.COGAGENT)
                and load_in_4_bit):
            monkey_patch_quantizer()
        if model_type == ModelType.XCOMPOSER2 and load_in_4_bit:
            with redirect_stdout(None):
                model = InternLMXComposer2QuantizedForCausalLM.from_quantized(
                    model_id, trust_remote_code=True, device=str(device))
        else:
            if load_in_4_bit:
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16
                )
                dtype_argument = {}
            else:
                quantization_config = None
                dtype_argument = ({'torch_dtype': torch.float16}
                                  if device.type == 'cuda' else {})
            model_class = (AutoModelForCausalLM
                           if model_type in (ModelType.COGVLM,
                                             ModelType.COGAGENT,
                                             ModelType.XCOMPOSER2,
                                             ModelType.MOONDREAM)
                           else AutoModelForVision2Seq)
            # Some models print unnecessary messages while loading, so
            # temporarily suppress printing for them.
            context_manager = (redirect_stdout(None)
                               if model_type in (ModelType.COGAGENT,
                                                 ModelType.XCOMPOSER2)
                               else nullcontext())
            with context_manager:
                model = model_class.from_pretrained(
                    model_id, device_map=device, trust_remote_code=True,
                    quantization_config=quantization_config, **dtype_argument)
        if 'moondream1' in model_id:
            model = monkey_patch_moondream1(device, model_id)
        model.eval()
        self.parent().model = model
        self.parent().model_id = model_id
        self.parent().model_device_type = device.type
        self.parent().is_model_loaded_in_4_bit = load_in_4_bit
        return processor, model

    def get_processed_prompt(self, model_type: ModelType) -> str:
        prompt = self.caption_settings['prompt']
        if not prompt:
            if model_type in (ModelType.LLAVA, ModelType.COGVLM,
                              ModelType.COGAGENT, ModelType.MOONDREAM):
                prompt = 'Describe the image in twenty words or less.'
            elif model_type == ModelType.XCOMPOSER2:
                prompt = 'Concisely describe the image.'
        if model_type == ModelType.LLAVA:
            prompt = f'USER: <image>\n{prompt}\nASSISTANT:'
        elif model_type == ModelType.KOSMOS:
            prompt = f'<grounding>{prompt}'
        elif model_type == ModelType.XCOMPOSER2:
            prompt = (f'[UNUSED_TOKEN_146]user\n<ImageHere>{prompt}'
                      f'[UNUSED_TOKEN_145]\n[UNUSED_TOKEN_146]assistant\n')
        elif model_type == ModelType.MOONDREAM:
            prompt = f'<image>\n\nQuestion: {prompt}\n\nAnswer:'
        return prompt

    def get_model_inputs(self, prompt: str, image: Image,
                         model_type: ModelType, device: torch.device, model,
                         processor) -> BatchFeature | dict:
        # Prepare the input text.
        caption_start = self.caption_settings['caption_start']
        if model_type in (ModelType.COGVLM, ModelType.COGAGENT):
            # `caption_start` is added later.
            text = prompt
        elif model_type == ModelType.XCOMPOSER2:
            text = prompt + caption_start
        elif prompt and caption_start:
            text = f'{prompt} {caption_start}'
        else:
            text = prompt or caption_start
        # Load the image.
        pil_image = PilImage.open(image.path)
        # Rotate the image according to the orientation tag.
        pil_image = exif_transpose(pil_image)
        pil_image = pil_image.convert('RGB')
        # Convert the text and image to model inputs.
        dtype_argument = ({'dtype': torch.float16}
                          if device.type == 'cuda' else {})
        if model_type in (ModelType.COGVLM, ModelType.COGAGENT):
            beam_count = self.caption_settings['generation_parameters'][
                'num_beams']
            model_inputs = get_cogvlm_cogagent_inputs(
                model_type, model, processor, text, pil_image, beam_count,
                device, dtype_argument)
        elif model_type == ModelType.XCOMPOSER2:
            load_in_4_bit = self.caption_settings['load_in_4_bit']
            model_inputs = get_xcomposer2_inputs(
                model, processor, load_in_4_bit, text, pil_image, device,
                dtype_argument)
        elif model_type == ModelType.MOONDREAM:
            model_inputs = get_moondream_inputs(
                model, processor, text, pil_image, device, dtype_argument)
        else:
            model_inputs = (processor(text=text, images=pil_image,
                                      return_tensors='pt')
                            .to(device, **dtype_argument))
        return model_inputs

    def get_caption_from_generated_tokens(
            self, generated_token_ids: torch.Tensor, prompt: str, processor,
            model_type: ModelType) -> str:
        generated_text = processor.batch_decode(
            generated_token_ids, skip_special_tokens=True)[0]
        # Postprocess the generated text.
        caption_start = self.caption_settings['caption_start']
        if model_type == ModelType.LLAVA:
            prompt = prompt.replace('<image>', ' ')
        elif model_type == ModelType.KOSMOS:
            generated_text, _ = processor.post_process_generation(
                generated_text)
            prompt = prompt.replace('<grounding>', '')
        elif model_type == ModelType.COGVLM:
            prompt = f'Question: {prompt} Answer:'
        elif model_type == ModelType.COGAGENT:
            prompt = f'<EOI>Question: {prompt} Answer:'
        elif model_type == ModelType.XCOMPOSER2:
            generated_text = generated_text.split('[UNUSED_TOKEN_145]')[0]
        elif model_type == ModelType.MOONDREAM:
            generated_text = re.sub('END$', '', generated_text)
            generated_text = re.sub('<$', '', generated_text)
            pass
        if prompt.strip() and generated_text.startswith(prompt):
            caption = generated_text[len(prompt):]
        elif (caption_start.strip()
              and generated_text.startswith(caption_start)):
            caption = generated_text
        else:
            caption = f'{caption_start.strip()} {generated_text.strip()}'
        caption = caption.strip()
        if self.caption_settings['remove_tag_separators']:
            caption = caption.replace(self.tag_separator, ' ')
        return caption

    def run(self):
        # Redirect `stdout` and `stderr` so that the outputs are
        # displayed in the console text edit.
        sys.stdout = self
        sys.stderr = self
        forced_words_string = self.caption_settings['forced_words']
        generation_parameters = self.caption_settings[
            'generation_parameters']
        beam_count = generation_parameters['num_beams']
        if forced_words_string.strip() and beam_count < 2:
            self.clear_console_text_edit_requested.emit()
            print('`Number of beams` must be greater than 1 when `Include in '
                  'caption` is not empty.')
            return
        if self.caption_settings['device'] == Device.CPU:
            device = torch.device('cpu')
        else:
            device = torch.device('cuda:0' if torch.cuda.is_available()
                                  else 'cpu')
        model_id = self.caption_settings['model']
        model_type = get_model_type(model_id)
        load_in_4_bit = self.caption_settings['load_in_4_bit']
        error_message = None
        if model_type == ModelType.XCOMPOSER2:
            error_message = get_xcomposer2_error_message(
                model_id, self.caption_settings['device'], load_in_4_bit)
        elif model_type == ModelType.MOONDREAM:
            beam_count = self.caption_settings['generation_parameters'][
                'num_beams']
            error_message = get_moondream_error_message(load_in_4_bit,
                                                        beam_count)
        if error_message:
            self.clear_console_text_edit_requested.emit()
            print(error_message)
            return
        processor, model = self.load_processor_and_model(device, model_type)
        # CogVLM and CogAgent have to be monkey patched every time because
        # `caption_start` might have changed.
        caption_start = self.caption_settings['caption_start']
        if model_type == ModelType.COGVLM:
            monkey_patch_cogvlm(caption_start)
        elif model_type == ModelType.COGAGENT:
            monkey_patch_cogagent(model, caption_start)
        self.clear_console_text_edit_requested.emit()
        print(f'Captioning... (device: {device})')
        prompt = self.get_processed_prompt(model_type)
        caption_position = self.caption_settings['caption_position']
        are_multiple_images_selected = len(self.selected_image_indices) > 1
        for i, image_index in enumerate(self.selected_image_indices):
            start_time = perf_counter()
            image: Image = self.image_list_model.data(image_index, Qt.UserRole)
            try:
                model_inputs = self.get_model_inputs(prompt, image, model_type,
                                                     device, model, processor)
            except UnidentifiedImageError:
                print(f'Skipping {image.path.name} because its file format is '
                      'not supported.')
                continue
            forced_words_ids = get_forced_words_ids(forced_words_string,
                                                    model_type, processor)
            generation_model = (model.text_model
                                if model_type == ModelType.MOONDREAM
                                else model)
            with torch.inference_mode():
                generated_token_ids = generation_model.generate(
                    **model_inputs, force_words_ids=forced_words_ids,
                    **generation_parameters)
            caption = self.get_caption_from_generated_tokens(
                generated_token_ids, prompt, processor, model_type)
            tags = add_caption_to_tags(image.tags, caption, caption_position)
            self.caption_generated.emit(image_index, caption, tags)
            if are_multiple_images_selected:
                self.progress_bar_update_requested.emit(i + 1)
            if i == 0:
                self.clear_console_text_edit_requested.emit()
            print(f'{image.path.name} ({perf_counter() - start_time:.1f} s):\n'
                  f'{caption}')

    def write(self, text: str):
        self.text_outputted.emit(text)
