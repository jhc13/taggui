import gc
import re
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from time import perf_counter
from datetime import datetime

import numpy as np
import torch
from PIL import Image as PilImage, UnidentifiedImageError
from PIL.ImageOps import exif_transpose
from PySide6.QtCore import QModelIndex, QThread, Qt, Signal
from transformers import (AutoConfig, AutoModelForCausalLM,
                          AutoModelForVision2Seq, AutoProcessor, AutoTokenizer,
                          BatchFeature, BitsAndBytesConfig,
                          CodeGenTokenizerFast, LlamaTokenizer)

from auto_captioning.cogvlm2 import (get_cogvlm2_error_message,
                                     get_cogvlm2_inputs)
from auto_captioning.cogvlm_cogagent import (get_cogvlm_cogagent_inputs,
                                             monkey_patch_cogagent,
                                             monkey_patch_cogvlm)
from auto_captioning.models import get_model_type
from auto_captioning.moondream import (get_moondream_error_message,
                                       get_moondream_inputs,
                                       monkey_patch_moondream1)
from auto_captioning.prompts import (format_prompt, get_default_prompt,
                                     postprocess_prompt_and_generated_text)
from auto_captioning.wd_tagger import WdTaggerModel
from auto_captioning.xcomposer2 import (InternLMXComposer2QuantizedForCausalLM,
                                        get_xcomposer2_error_message,
                                        get_xcomposer2_inputs)
from models.image_list_model import ImageListModel
from utils.enums import CaptionDevice, CaptionModelType, CaptionPosition
from utils.image import Image
from utils.settings import get_tag_separator
from utils.utils import get_pretty_duration


def replace_template_variable(match: re.Match, image: Image) -> str:
    template_variable = match.group(0)[1:-1].lower()
    if template_variable == 'tags':
        return ', '.join(image.tags)
    if template_variable == 'name':
        return image.path.stem
    if template_variable in ('directory', 'folder'):
        return image.path.parent.name


def replace_template_variables(text: str, image: Image) -> str:
    # Replace template variables inside curly braces that are not escaped.
    text = re.sub(r'(?<!\\){[^{}]+(?<!\\)}',
                  lambda match: replace_template_variable(match, image), text)
    # Unescape escaped curly braces.
    text = re.sub(r'\\([{}])', r'\1', text)
    return text


def get_tokenizer_from_processor(model_type: CaptionModelType, processor):
    if model_type in (CaptionModelType.COGAGENT, CaptionModelType.COGVLM,
                      CaptionModelType.COGVLM2, CaptionModelType.MOONDREAM1,
                      CaptionModelType.MOONDREAM2,
                      CaptionModelType.XCOMPOSER2,
                      CaptionModelType.XCOMPOSER2_4KHD):
        return processor
    return processor.tokenizer


def get_bad_words_ids(bad_words_string: str,
                      tokenizer) -> list[list[int]] | None:
    if not bad_words_string.strip():
        return None
    words = re.split(r'(?<!\\),', bad_words_string)
    words = [word.strip().replace(r'\,', ',') for word in words]
    # Also discourage generating the versions of the words with spaces before
    # them.
    words += [' ' + word for word in words]
    bad_words_ids = tokenizer(words, add_special_tokens=False).input_ids
    return bad_words_ids


def get_forced_words_ids(forced_words_string: str,
                         tokenizer) -> list[list[list[int]]] | None:
    if not forced_words_string.strip():
        return None
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
    if caption_position == CaptionPosition.DO_NOT_ADD or not caption:
        return tags
    tag_separator = get_tag_separator()
    new_tags = caption.split(tag_separator)
    # Make a copy of the tags so that the tags in the image list model are not
    # modified.
    tags = tags.copy()
    if caption_position == CaptionPosition.BEFORE_FIRST_TAG:
        tags[:0] = new_tags
    elif caption_position == CaptionPosition.AFTER_LAST_TAG:
        tags.extend(new_tags)
    elif caption_position == CaptionPosition.OVERWRITE_FIRST_TAG:
        if tags:
            tags[:1] = new_tags
        else:
            tags = new_tags
    elif caption_position == CaptionPosition.OVERWRITE_ALL_TAGS:
        tags = new_tags
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
        self.is_canceled = False

    def load_processor_and_model(self, device: torch.device,
                                 model_type: CaptionModelType) -> tuple:
        # If the processor and model were previously loaded, use them.
        processor = self.parent().processor
        model = self.parent().model
        model_id = self.caption_settings['model']
        # Only GPUs support 4-bit quantization.
        load_in_4_bit = (self.caption_settings['load_in_4_bit']
                         and device.type == 'cuda')
        if self.models_directory_path:
            config_path = self.models_directory_path / model_id / 'config.json'
            tags_path = (self.models_directory_path / model_id
                         / 'selected_tags.csv')
            if config_path.is_file() or tags_path.is_file():
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
        if model_type in (CaptionModelType.COGAGENT, CaptionModelType.COGVLM):
            processor = LlamaTokenizer.from_pretrained('lmsys/vicuna-7b-v1.5')
        elif model_type == CaptionModelType.WD_TAGGER:
            processor = None
        else:
            if model_type == CaptionModelType.MOONDREAM1:
                processor_class = CodeGenTokenizerFast
            elif model_type in (CaptionModelType.COGVLM2,
                                CaptionModelType.MOONDREAM2,
                                CaptionModelType.XCOMPOSER2,
                                CaptionModelType.XCOMPOSER2_4KHD):
                processor_class = AutoTokenizer
            else:
                processor_class = AutoProcessor
            processor = processor_class.from_pretrained(model_id,
                                                        trust_remote_code=True)
        if model_type in (CaptionModelType.LLAVA_NEXT_34B,
                          CaptionModelType.LLAVA_NEXT_MISTRAL,
                          CaptionModelType.LLAVA_NEXT_VICUNA):
            processor.tokenizer.padding_side = 'left'
        self.parent().processor = processor
        if model_type == CaptionModelType.XCOMPOSER2 and load_in_4_bit:
            with redirect_stdout(None):
                model = InternLMXComposer2QuantizedForCausalLM.from_quantized(
                    model_id, trust_remote_code=True, device=str(device))
        elif model_type == CaptionModelType.WD_TAGGER:
            model = WdTaggerModel(model_id)
        else:
            if model_type == CaptionModelType.MOONDREAM2:
                revision_argument = {'revision': '2024-03-13'}
            else:
                revision_argument = {}
            if load_in_4_bit:
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type='nf4',
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True
                )
                dtype_argument = {}
                if model_type == CaptionModelType.COGVLM2:
                    config = AutoConfig.from_pretrained(model_id,
                                                        trust_remote_code=True)
                    config.quantization_config = quantization_config
                    quantization_config_argument = {}
                    config_argument = {'config': config}
                else:
                    quantization_config_argument = {
                        'quantization_config': quantization_config
                    }
                    config_argument = {}
            else:
                dtype_argument = ({'torch_dtype': torch.float16}
                                  if device.type == 'cuda' else {})
                quantization_config_argument = {}
                config_argument = {}
            model_class = (AutoModelForCausalLM
                           if model_type in (CaptionModelType.COGAGENT,
                                             CaptionModelType.COGVLM,
                                             CaptionModelType.COGVLM2,
                                             CaptionModelType.MOONDREAM1,
                                             CaptionModelType.MOONDREAM2,
                                             CaptionModelType.XCOMPOSER2,
                                             CaptionModelType.XCOMPOSER2_4KHD)
                           else AutoModelForVision2Seq)
            # Some models print unnecessary messages while loading, so
            # temporarily suppress printing for them.
            context_manager = (
                redirect_stdout(None)
                if model_type in (CaptionModelType.COGAGENT,
                                  CaptionModelType.XCOMPOSER2,
                                  CaptionModelType.XCOMPOSER2_4KHD)
                else nullcontext())
            with context_manager:
                model = model_class.from_pretrained(
                    model_id, device_map=device, trust_remote_code=True,
                    **revision_argument, **dtype_argument,
                    **quantization_config_argument, **config_argument)
        if model_type == CaptionModelType.MOONDREAM1:
            model = monkey_patch_moondream1(device, model_id)
        if model_type != CaptionModelType.WD_TAGGER:
            model.eval()
        self.parent().model = model
        self.parent().model_id = model_id
        self.parent().model_device_type = device.type
        self.parent().is_model_loaded_in_4_bit = load_in_4_bit
        return processor, model

    def get_prompt(self, model_type: CaptionModelType,
                   image: Image) -> str | None:
        if model_type == CaptionModelType.WD_TAGGER:
            return None
        prompt = self.caption_settings['prompt']
        if prompt:
            prompt = replace_template_variables(prompt, image)
        else:
            prompt = get_default_prompt(model_type)
        prompt = format_prompt(prompt, model_type)
        return prompt

    def get_model_inputs(self, image: Image, prompt: str | None,
                         model_type: CaptionModelType, device: torch.device,
                         model, processor) -> BatchFeature | dict | np.ndarray:
        # Load the image.
        pil_image = PilImage.open(image.path)
        # Rotate the image according to the orientation tag.
        pil_image = exif_transpose(pil_image)
        mode = 'RGBA' if model_type == CaptionModelType.WD_TAGGER else 'RGB'
        pil_image = pil_image.convert(mode)
        if model_type == CaptionModelType.WD_TAGGER:
            return model.get_inputs(pil_image)
        # Prepare the input text.
        caption_start = self.caption_settings['caption_start']
        if model_type in (CaptionModelType.COGAGENT, CaptionModelType.COGVLM):
            # `caption_start` is added later.
            text = prompt
        elif model_type in (CaptionModelType.LLAVA_LLAMA_3,
                            CaptionModelType.LLAVA_NEXT_34B,
                            CaptionModelType.XCOMPOSER2,
                            CaptionModelType.XCOMPOSER2_4KHD):
            text = prompt + caption_start
        elif prompt and caption_start:
            text = f'{prompt} {caption_start}'
        else:
            text = prompt or caption_start
        # Convert the text and image to model inputs.
        beam_count = self.caption_settings['generation_parameters'][
            'num_beams']
        dtype_argument = ({'dtype': torch.float16}
                          if device.type == 'cuda' else {})
        if model_type in (CaptionModelType.COGAGENT, CaptionModelType.COGVLM):
            model_inputs = get_cogvlm_cogagent_inputs(
                model_type, model, processor, text, pil_image, beam_count,
                device, dtype_argument)
        elif model_type == CaptionModelType.COGVLM2:
            model_inputs = get_cogvlm2_inputs(model, processor, text,
                                              pil_image, device,
                                              dtype_argument, beam_count)
        elif model_type in (CaptionModelType.MOONDREAM1,
                            CaptionModelType.MOONDREAM2):
            model_inputs = get_moondream_inputs(
                model, processor, text, pil_image, device, dtype_argument)
        elif model_type in (CaptionModelType.XCOMPOSER2,
                            CaptionModelType.XCOMPOSER2_4KHD):
            load_in_4_bit = self.caption_settings['load_in_4_bit']
            model_inputs = get_xcomposer2_inputs(
                model_type, model, processor, load_in_4_bit, text, pil_image,
                device, dtype_argument)
        else:
            model_inputs = (processor(text=text, images=pil_image,
                                      return_tensors='pt')
                            .to(device, **dtype_argument))
        return model_inputs

    def get_caption_from_generated_tokens(
            self, generated_token_ids: torch.Tensor, prompt: str, processor,
            model_type: CaptionModelType) -> str:
        generated_text = processor.batch_decode(
            generated_token_ids, skip_special_tokens=True)[0]
        prompt, generated_text = postprocess_prompt_and_generated_text(
            model_type, processor, prompt, generated_text)
        caption_start = self.caption_settings['caption_start']
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
        model_id = self.caption_settings['model']
        model_type = get_model_type(model_id)
        forced_words_string = self.caption_settings['forced_words']
        generation_parameters = self.caption_settings[
            'generation_parameters']
        beam_count = generation_parameters['num_beams']
        if (forced_words_string.strip() and beam_count < 2
                and model_type != CaptionModelType.WD_TAGGER):
            self.clear_console_text_edit_requested.emit()
            print('`Number of beams` must be greater than 1 when `Include in '
                  'caption` is not empty.')
            return
        if self.caption_settings['device'] == CaptionDevice.CPU:
            device = torch.device('cpu')
        else:
            gpu_index = self.caption_settings['gpu_index']
            device = torch.device(f'cuda:{gpu_index}'
                                  if torch.cuda.is_available() else 'cpu')
        load_in_4_bit = self.caption_settings['load_in_4_bit']
        error_message = None
        if model_type == CaptionModelType.COGVLM2:
            error_message = get_cogvlm2_error_message(
                model_id, self.caption_settings['device'], load_in_4_bit)
        elif model_type in (CaptionModelType.MOONDREAM1,
                            CaptionModelType.MOONDREAM2):
            beam_count = self.caption_settings['generation_parameters'][
                'num_beams']
            error_message = get_moondream_error_message(load_in_4_bit,
                                                        beam_count)
        elif model_type in (CaptionModelType.XCOMPOSER2,
                            CaptionModelType.XCOMPOSER2_4KHD):
            error_message = get_xcomposer2_error_message(
                model_id, self.caption_settings['device'], load_in_4_bit)
        if error_message:
            self.clear_console_text_edit_requested.emit()
            print(error_message)
            return
        processor, model = self.load_processor_and_model(device, model_type)
        # CogVLM and CogAgent have to be monkey patched every time because
        # `caption_start` might have changed.
        caption_start = self.caption_settings['caption_start']
        if model_type == CaptionModelType.COGVLM:
            monkey_patch_cogvlm(caption_start)
        elif model_type == CaptionModelType.COGAGENT:
            monkey_patch_cogagent(model, caption_start)
        if self.is_canceled:
            print('Canceled captioning.')
            return
        self.clear_console_text_edit_requested.emit()
        captioning_message = ('Generating tags...'
                              if model_type == CaptionModelType.WD_TAGGER
                              else f'Captioning... (device: {device})')
        print(captioning_message)
        caption_position = self.caption_settings['caption_position']
        are_multiple_images_selected = len(self.selected_image_indices) > 1
        start_datetime = datetime.now()
        if are_multiple_images_selected:
            print(f"Captioning started at {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        captioning_times = []
        for i, image_index in enumerate(self.selected_image_indices):
            start_time = perf_counter()
            if self.is_canceled:
                print('Canceled captioning.')
                return
            image: Image = self.image_list_model.data(image_index,
                                                      Qt.ItemDataRole.UserRole)
            prompt = self.get_prompt(model_type, image)
            try:
                model_inputs = self.get_model_inputs(image, prompt, model_type,
                                                     device, model, processor)
            except UnidentifiedImageError:
                print(f'Skipping {image.path.name} because its file format is '
                      'not supported or it is a corrupted image.')
                continue
            console_output_caption = None
            if model_type == CaptionModelType.WD_TAGGER:
                wd_tagger_settings = self.caption_settings[
                    'wd_tagger_settings']
                tags, probabilities = model.generate_tags(model_inputs,
                                                          wd_tagger_settings)
                caption = self.tag_separator.join(tags)
                if wd_tagger_settings['show_probabilities']:
                    console_output_caption = self.tag_separator.join(
                        f'{tag} ({probability:.2f})'
                        for tag, probability in zip(tags, probabilities)
                    )
            else:
                generation_model = (
                    model.text_model
                    if model_type in (CaptionModelType.MOONDREAM1,
                                      CaptionModelType.MOONDREAM2)
                    else model
                )
                bad_words_string = self.caption_settings['bad_words']
                tokenizer = get_tokenizer_from_processor(model_type, processor)
                bad_words_ids = get_bad_words_ids(bad_words_string, tokenizer)
                forced_words_ids = get_forced_words_ids(forced_words_string,
                                                        tokenizer)
                if model_type == CaptionModelType.COGVLM2:
                    special_generation_parameters = {'pad_token_id': 128002}
                elif model_type == CaptionModelType.LLAVA_LLAMA_3:
                    eos_token_id = (tokenizer('<|eot_id|>',
                                              add_special_tokens=False)
                                    .input_ids)[0]
                    special_generation_parameters = {
                        'eos_token_id': eos_token_id
                    }
                else:
                    special_generation_parameters = {}
                with torch.inference_mode():
                    generated_token_ids = generation_model.generate(
                        **model_inputs, bad_words_ids=bad_words_ids,
                        force_words_ids=forced_words_ids,
                        **generation_parameters,
                        **special_generation_parameters)
                caption = self.get_caption_from_generated_tokens(
                    generated_token_ids, prompt, processor, model_type)
            tags = add_caption_to_tags(image.tags, caption, caption_position)
            self.caption_generated.emit(image_index, caption, tags)
            captioning_time = perf_counter() - start_time
            captioning_times.append(captioning_time)
            #avg_time = sum(captioning_times) / len(captioning_times)
            if are_multiple_images_selected:
                self.progress_bar_update_requested.emit(i + 1)
            if i == 0:
                self.clear_console_text_edit_requested.emit()
            if console_output_caption is None:
                console_output_caption = caption
            print(f'{image.path.name} ({captioning_time:.1f} s):\n'
                  f'{console_output_caption}')
        if are_multiple_images_selected:
            end_datetime = datetime.now()
            diff_datetime = end_datetime - start_datetime
            diff_secs = diff_datetime.total_seconds()
            avg_time = sum(captioning_times) / len(captioning_times)
            print(f"\nCaptioning finished in {get_pretty_duration(diff_secs)} (avg: {avg_time:.1f} s/img) at {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")

    def write(self, text: str):
        self.text_outputted.emit(text)
