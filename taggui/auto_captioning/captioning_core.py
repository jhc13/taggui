import gc
import re
from contextlib import nullcontext, redirect_stdout
from pathlib import Path

import numpy as np
import torch
from PIL import Image as PilImage, UnidentifiedImageError
from PIL.ImageOps import exif_transpose
from transformers import (AutoConfig, AutoModelForCausalLM,
                          AutoModelForVision2Seq, AutoProcessor, AutoTokenizer,
                          BatchFeature, BitsAndBytesConfig,
                          CodeGenTokenizerFast, LlamaTokenizer)

from auto_captioning.cogvlm2 import (get_cogvlm2_error_message,
                                     get_cogvlm2_inputs)
from auto_captioning.cogvlm_cogagent import (get_cogvlm_cogagent_inputs,
                                             monkey_patch_cogagent,
                                             monkey_patch_cogvlm)
from auto_captioning.florence_2 import get_florence_2_error_message
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
from utils.enums import CaptionDevice, CaptionModelType


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
    words = [word.strip() for word in words if word.strip()]
    if not words:
        return None
    words = [word.replace(r'\,', ',') for word in words]
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
        words = [word.strip() for word in words if word.strip()]
        if not words:
            continue
        words = [word.replace(r'\|', '|') for word in words]
        words_ids = tokenizer(words, add_special_tokens=False).input_ids
        forced_words_ids.append(words_ids)
    if not forced_words_ids:
        return None
    return forced_words_ids


class CaptioningCore():
    model_id = ""
    model_device_type = ""
    model_type = None
    is_model_loaded_in_4_bit = False
    device = None
    processor = None
    model = None

    def __init__(self,
                 caption_settings: dict, tag_separator: str,
                 models_directory_path: Path | None):
        self.caption_settings = caption_settings
        self.tag_separator = tag_separator
        self.models_directory_path = models_directory_path

    def load_processor_and_model(self, device: torch.device,
                                 model_type: CaptionModelType) -> tuple:
        # If the processor and model were previously loaded, use them.
        processor = self.processor
        model = self.model
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
        if (model and self.model_id == model_id
                and self.model_device_type == device.type
                and self.is_model_loaded_in_4_bit == load_in_4_bit):
            return processor, model
        # Load the new processor and model.
        if model:
            # Garbage collect the previous processor and model to free up
            # memory.
            self.processor = None
            self.model = None
            del processor
            del model
            gc.collect()
        #print(f'Loading {model_id}...')
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
        self.processor = processor
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
                                             CaptionModelType.FLORENCE_2,
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
        self.model = model
        self.model_id = model_id
        self.model_device_type = device.type
        self.is_model_loaded_in_4_bit = load_in_4_bit
        return processor, model

    def get_prompt(self, model_type: CaptionModelType) -> str | None:
        if model_type == CaptionModelType.WD_TAGGER:
            return None
        prompt = self.caption_settings['prompt']
        if not prompt:
            prompt = get_default_prompt(model_type)
        prompt = format_prompt(prompt, model_type)
        return prompt

    def get_model_inputs(self, pil_image: PilImage.Image, prompt: str | None,
                         model_type: CaptionModelType, device: torch.device,
                         model, processor) -> BatchFeature | dict | np.ndarray:
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

    def start_captioning(self) -> str | None:
        model_id = self.caption_settings['model']
        model_type = get_model_type(model_id)
        forced_words_string = self.caption_settings['forced_words']
        generation_parameters = self.caption_settings[
            'generation_parameters']
        beam_count = generation_parameters['num_beams']
        if (forced_words_string.strip() and beam_count < 2
                and model_type != CaptionModelType.WD_TAGGER):
            error_message = '`Number of beams` must be greater than 1 when `Include in caption` is not empty.'
            return error_message
        if self.caption_settings['device'] == CaptionDevice.CPU:
            device = torch.device('cpu')
        else:
            gpu_index = self.caption_settings['gpu_index']
            device = torch.device(f'cuda:{gpu_index}'
                                  if torch.cuda.is_available() else 'cpu')
        load_in_4_bit = self.caption_settings['load_in_4_bit']
        caption_start = self.caption_settings['caption_start']
        error_message = None
        if model_type == CaptionModelType.COGVLM2:
            error_message = get_cogvlm2_error_message(
                model_id, self.caption_settings['device'], load_in_4_bit)
        elif model_type == CaptionModelType.FLORENCE_2:
            error_message = get_florence_2_error_message(
                caption_settings['prompt'], caption_start)
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
            return error_message
        processor, model = self.load_processor_and_model(device, model_type)
        # CogVLM and CogAgent have to be monkey patched every time because
        # `caption_start` might have changed.
        if model_type == CaptionModelType.COGVLM:
            monkey_patch_cogvlm(caption_start)
        elif model_type == CaptionModelType.COGAGENT:
            monkey_patch_cogagent(model, caption_start)
        self.processor = processor
        self.model = model
        self.model_type = model_type
        self.device = device

    def run_captioning(self, pil_image: PilImage.Image) -> tuple[bool, str, str]:
        forced_words_string = self.caption_settings['forced_words'].strip()
        generation_parameters = self.caption_settings['generation_parameters']
        prompt = self.get_prompt(self.model_type)
        try:
            model_inputs = self.get_model_inputs(pil_image, prompt, self.model_type,
                                                    self.device, self.model, self.processor)
        except UnidentifiedImageError:
            error_message = f'Image file format is not supported or it is a corrupted image.'
            return False, error_message, ""
        console_output_caption = None
        if self.model_type == CaptionModelType.WD_TAGGER:
            wd_tagger_settings = self.caption_settings[
                'wd_tagger_settings']
            tags, probabilities = self.model.generate_tags(model_inputs,
                                                        wd_tagger_settings)
            caption = self.tag_separator.join(tags)
            if wd_tagger_settings['show_probabilities']:
                console_output_caption = self.tag_separator.join(
                    f'{tag} ({probability:.2f})'
                    for tag, probability in zip(tags, probabilities)
                )
        else:
            generation_model = (
                self.model.text_model
                if self.model_type in (CaptionModelType.MOONDREAM1,
                                    CaptionModelType.MOONDREAM2)
                else self.model
            )
            bad_words_string = self.caption_settings['bad_words']
            tokenizer = get_tokenizer_from_processor(self.model_type, self.processor)
            bad_words_ids = get_bad_words_ids(bad_words_string, tokenizer)
            forced_words_ids = get_forced_words_ids(forced_words_string,
                                                    tokenizer)
            if self.model_type == CaptionModelType.COGVLM2:
                special_generation_parameters = {'pad_token_id': 128002}
            elif self.model_type == CaptionModelType.LLAVA_LLAMA_3:
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
                generated_token_ids, prompt, self.processor, self.model_type)

        if console_output_caption is None:
            console_output_caption = caption
        return True, console_output_caption, caption
