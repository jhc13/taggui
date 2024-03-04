import gc
import re
import sys
from contextlib import nullcontext, redirect_stdout
from enum import Enum, auto
from inspect import getsource
from pathlib import Path
from time import perf_counter

import torch
from PIL import Image as PilImage, UnidentifiedImageError
from PIL.ImageOps import exif_transpose
from PySide6.QtCore import QModelIndex, QSettings, QThread, Qt, Signal, Slot
from PySide6.QtGui import QFontMetrics, QTextCursor
from PySide6.QtWidgets import (QAbstractScrollArea, QDockWidget, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QScrollArea, QVBoxLayout, QWidget)
from auto_gptq.modeling import BaseGPTQForCausalLM
from transformers import (AutoModelForCausalLM, AutoModelForVision2Seq,
                          AutoProcessor, AutoTokenizer, BatchFeature,
                          BitsAndBytesConfig, LlamaTokenizer)

from models.image_list_model import ImageListModel
from utils.big_widgets import BigCheckBox, TallPushButton
from utils.focused_scroll_widgets import (FocusedScrollComboBox,
                                          FocusedScrollDoubleSpinBox,
                                          FocusedScrollSpinBox)
from utils.image import Image
from utils.settings import get_separator, get_settings
from utils.utils import get_confirmation_dialog_reply, pluralize
from widgets.image_list import ImageList

MODELS = [
    'internlm/internlm-xcomposer2-vl-7b-4bit',
    'internlm/internlm-xcomposer2-vl-7b',
    'THUDM/cogagent-vqa-hf',
    'THUDM/cogvlm-chat-hf',
    'llava-hf/llava-1.5-7b-hf',
    'llava-hf/llava-1.5-13b-hf',
    'llava-hf/bakLlava-v1-hf',
    'Salesforce/instructblip-vicuna-7b',
    'Salesforce/instructblip-vicuna-13b',
    'Salesforce/instructblip-flan-t5-xl',
    'Salesforce/instructblip-flan-t5-xxl',
    'Salesforce/blip2-opt-2.7b',
    'Salesforce/blip2-opt-6.7b',
    'Salesforce/blip2-opt-6.7b-coco',
    'Salesforce/blip2-flan-t5-xl',
    'Salesforce/blip2-flan-t5-xxl',
    'microsoft/kosmos-2-patch14-224'
]


# `StrEnum` is a Python 3.11 feature that can be used here.
class CaptionPosition(str, Enum):
    BEFORE_FIRST_TAG = 'Insert before first tag'
    AFTER_LAST_TAG = 'Insert after last tag'
    OVERWRITE_FIRST_TAG = 'Overwrite first tag'
    OVERWRITE_ALL_TAGS = 'Overwrite all tags'
    DO_NOT_ADD = 'Do not add to tags'


class Device(str, Enum):
    GPU = 'GPU if available'
    CPU = 'CPU'


class ModelType(Enum):
    LLAVA = auto()
    KOSMOS = auto()
    COGVLM = auto()
    COGAGENT = auto()
    XCOMPOSER2 = auto()
    OTHER = auto()


def set_text_edit_height(text_edit: QPlainTextEdit, line_count: int):
    """
    Set the height of a text edit to the height of a given number of lines.
    """
    # From https://stackoverflow.com/a/46997337.
    document = text_edit.document()
    font_metrics = QFontMetrics(document.defaultFont())
    margins = text_edit.contentsMargins()
    height = (font_metrics.lineSpacing() * line_count
              + margins.top() + margins.bottom()
              + document.documentMargin() * 2
              + text_edit.frameWidth() * 2)
    text_edit.setFixedHeight(height)


class HorizontalLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Raised)


def get_directory_paths(directory_path: Path) -> list[Path]:
    """
    Recursively get all directory paths in a directory, including those in
    subdirectories.
    """
    directory_paths = [directory_path]
    for path in directory_path.iterdir():
        if path.is_dir():
            directory_paths.extend(get_directory_paths(path))
    return directory_paths


class CaptionSettingsForm(QVBoxLayout):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        try:
            import bitsandbytes
            self.is_bitsandbytes_available = True
        except RuntimeError:
            self.is_bitsandbytes_available = False
        self.basic_settings_form = QFormLayout()
        self.basic_settings_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapAllRows)
        self.basic_settings_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.prompt_text_edit = QPlainTextEdit()
        set_text_edit_height(self.prompt_text_edit, 2)
        self.caption_start_line_edit = QLineEdit()
        self.forced_words_line_edit = QLineEdit()
        self.caption_position_combo_box = FocusedScrollComboBox()
        self.caption_position_combo_box.addItems(list(CaptionPosition))
        self.model_combo_box = FocusedScrollComboBox()
        self.model_combo_box.setEditable(True)
        self.model_combo_box.addItems(self.get_local_model_paths())
        self.model_combo_box.addItems(MODELS)
        self.device_combo_box = FocusedScrollComboBox()
        self.device_combo_box.addItems(list(Device))
        self.basic_settings_form.addRow('Prompt', self.prompt_text_edit)
        self.basic_settings_form.addRow('Start caption with',
                                        self.caption_start_line_edit)
        self.basic_settings_form.addRow('Include in caption',
                                        self.forced_words_line_edit)
        self.basic_settings_form.addRow('Caption position',
                                        self.caption_position_combo_box)
        self.basic_settings_form.addRow('Model', self.model_combo_box)
        self.basic_settings_form.addRow('Device', self.device_combo_box)

        self.load_in_4_bit_container = QWidget()
        self.load_in_4_bit_layout = QHBoxLayout()
        self.load_in_4_bit_layout.setAlignment(Qt.AlignLeft)
        self.load_in_4_bit_layout.setContentsMargins(0, 0, 0, 0)
        self.load_in_4_bit_check_box = BigCheckBox()
        self.load_in_4_bit_layout.addWidget(QLabel('Load in 4-bit'))
        self.load_in_4_bit_layout.addWidget(self.load_in_4_bit_check_box)
        self.load_in_4_bit_container.setLayout(self.load_in_4_bit_layout)

        self.remove_tag_separators_container = QWidget()
        self.remove_tag_separators_layout = QHBoxLayout()
        self.remove_tag_separators_layout.setAlignment(Qt.AlignLeft)
        self.remove_tag_separators_layout.setContentsMargins(0, 0, 0, 0)
        self.remove_tag_separators_check_box = BigCheckBox()
        self.remove_tag_separators_layout.addWidget(
            QLabel('Remove tag separators in caption'))
        self.remove_tag_separators_layout.addWidget(
            self.remove_tag_separators_check_box)
        self.remove_tag_separators_container.setLayout(
            self.remove_tag_separators_layout)

        self.toggle_advanced_settings_form_button = TallPushButton(
            'Show Advanced Settings')

        self.advanced_settings_form_container = QWidget()
        advanced_settings_form = QFormLayout(
            self.advanced_settings_form_container)
        advanced_settings_form.setLabelAlignment(Qt.AlignRight)
        advanced_settings_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.min_new_token_count_spin_box = FocusedScrollSpinBox()
        self.min_new_token_count_spin_box.setRange(1, 999)
        self.max_new_token_count_spin_box = FocusedScrollSpinBox()
        self.max_new_token_count_spin_box.setRange(1, 999)
        self.beam_count_spin_box = FocusedScrollSpinBox()
        self.beam_count_spin_box.setRange(1, 99)
        self.length_penalty_spin_box = FocusedScrollDoubleSpinBox()
        self.length_penalty_spin_box.setRange(-5, 5)
        self.length_penalty_spin_box.setSingleStep(0.1)
        self.use_sampling_check_box = BigCheckBox()
        self.temperature_spin_box = FocusedScrollDoubleSpinBox()
        # The temperature must be positive.
        self.temperature_spin_box.setRange(0.01, 2)
        self.temperature_spin_box.setSingleStep(0.01)
        self.top_k_spin_box = FocusedScrollSpinBox()
        self.top_k_spin_box.setRange(0, 200)
        self.top_p_spin_box = FocusedScrollDoubleSpinBox()
        self.top_p_spin_box.setRange(0, 1)
        self.top_p_spin_box.setSingleStep(0.01)
        self.repetition_penalty_spin_box = FocusedScrollDoubleSpinBox()
        self.repetition_penalty_spin_box.setRange(1, 2)
        self.repetition_penalty_spin_box.setSingleStep(0.01)
        self.no_repeat_ngram_size_spin_box = FocusedScrollSpinBox()
        self.no_repeat_ngram_size_spin_box.setRange(0, 5)
        advanced_settings_form.addRow('Minimum tokens',
                                      self.min_new_token_count_spin_box)
        advanced_settings_form.addRow('Maximum tokens',
                                      self.max_new_token_count_spin_box)
        advanced_settings_form.addRow('Number of beams',
                                      self.beam_count_spin_box)
        advanced_settings_form.addRow('Length penalty',
                                      self.length_penalty_spin_box)
        advanced_settings_form.addRow('Use sampling',
                                      self.use_sampling_check_box)
        advanced_settings_form.addRow('Temperature',
                                      self.temperature_spin_box)
        advanced_settings_form.addRow('Top-k', self.top_k_spin_box)
        advanced_settings_form.addRow('Top-p', self.top_p_spin_box)
        advanced_settings_form.addRow('Repetition penalty',
                                      self.repetition_penalty_spin_box)
        advanced_settings_form.addRow('No repeat n-gram size',
                                      self.no_repeat_ngram_size_spin_box)
        self.advanced_settings_form_container.hide()

        self.addLayout(self.basic_settings_form)
        self.addWidget(self.load_in_4_bit_container)
        self.addWidget(self.remove_tag_separators_container)
        self.addWidget(HorizontalLine())
        self.addWidget(self.toggle_advanced_settings_form_button)
        self.addWidget(self.advanced_settings_form_container)
        self.addStretch()

        self.toggle_advanced_settings_form_button.clicked.connect(
            self.toggle_advanced_settings_form)
        # Make sure the minimum new token count is less than or equal to the
        # maximum new token count.
        self.min_new_token_count_spin_box.valueChanged.connect(
            self.max_new_token_count_spin_box.setMinimum)
        self.max_new_token_count_spin_box.valueChanged.connect(
            self.min_new_token_count_spin_box.setMaximum)
        # Save the caption settings when any of them is changed.
        self.prompt_text_edit.textChanged.connect(self.save_caption_settings)
        self.caption_start_line_edit.textChanged.connect(
            self.save_caption_settings)
        self.forced_words_line_edit.textChanged.connect(
            self.save_caption_settings)
        self.caption_position_combo_box.currentTextChanged.connect(
            self.save_caption_settings)
        self.model_combo_box.currentTextChanged.connect(
            self.save_caption_settings)
        self.device_combo_box.currentTextChanged.connect(
            self.save_caption_settings)
        self.device_combo_box.currentTextChanged.connect(
            self.set_load_in_4_bit_visibility)
        self.load_in_4_bit_check_box.stateChanged.connect(
            self.save_caption_settings)
        self.remove_tag_separators_check_box.stateChanged.connect(
            self.save_caption_settings)
        self.min_new_token_count_spin_box.valueChanged.connect(
            self.save_caption_settings)
        self.max_new_token_count_spin_box.valueChanged.connect(
            self.save_caption_settings)
        self.beam_count_spin_box.valueChanged.connect(
            self.save_caption_settings)
        self.length_penalty_spin_box.valueChanged.connect(
            self.save_caption_settings)
        self.use_sampling_check_box.stateChanged.connect(
            self.save_caption_settings)
        self.temperature_spin_box.valueChanged.connect(
            self.save_caption_settings)
        self.top_k_spin_box.valueChanged.connect(self.save_caption_settings)
        self.top_p_spin_box.valueChanged.connect(self.save_caption_settings)
        self.repetition_penalty_spin_box.valueChanged.connect(
            self.save_caption_settings)
        self.no_repeat_ngram_size_spin_box.valueChanged.connect(
            self.save_caption_settings)

        # Restore previous caption settings.
        self.load_caption_settings()
        if not self.is_bitsandbytes_available:
            self.load_in_4_bit_check_box.setChecked(False)
        self.set_load_in_4_bit_visibility(self.device_combo_box.currentText())

    def get_local_model_paths(self) -> list[str]:
        models_directory_path: str = self.settings.value(
            'models_directory_path', type=str)
        if not models_directory_path:
            return []
        models_directory_path: Path = Path(models_directory_path)
        if not models_directory_path.is_dir():
            return []
        print(f'Loading local auto-captioning model paths under '
              f'{models_directory_path}...')
        directory_paths = get_directory_paths(models_directory_path)
        model_directory_paths = [
            str(directory_path.relative_to(models_directory_path))
            for directory_path in directory_paths
            if (directory_path / 'config.json').is_file()
        ]
        model_directory_paths.sort()
        print(f'Loaded {len(model_directory_paths)} model '
              f'{pluralize("path", len(model_directory_paths))}.')
        return model_directory_paths

    @Slot(str)
    def set_load_in_4_bit_visibility(self, device: str):
        is_load_in_4_bit_available = (self.is_bitsandbytes_available
                                      and device == Device.GPU)
        self.load_in_4_bit_container.setVisible(is_load_in_4_bit_available)

    @Slot()
    def toggle_advanced_settings_form(self):
        if self.advanced_settings_form_container.isHidden():
            self.advanced_settings_form_container.show()
            self.toggle_advanced_settings_form_button.setText(
                'Hide Advanced Settings')
        else:
            self.advanced_settings_form_container.hide()
            self.toggle_advanced_settings_form_button.setText(
                'Show Advanced Settings')

    def load_caption_settings(self):
        caption_settings: dict = self.settings.value('caption_settings')
        if caption_settings is None:
            caption_settings = {}
        self.prompt_text_edit.setPlainText(caption_settings.get('prompt', ''))
        self.caption_start_line_edit.setText(
            caption_settings.get('caption_start', ''))
        self.forced_words_line_edit.setText(
            caption_settings.get('forced_words', ''))
        self.caption_position_combo_box.setCurrentText(
            caption_settings.get('caption_position',
                                 CaptionPosition.BEFORE_FIRST_TAG))
        self.model_combo_box.setCurrentText(
            caption_settings.get('model', MODELS[0]))
        self.device_combo_box.setCurrentText(
            caption_settings.get('device', Device.GPU))
        self.load_in_4_bit_check_box.setChecked(
            caption_settings.get('load_in_4_bit', True))
        self.remove_tag_separators_check_box.setChecked(
            caption_settings.get('remove_tag_separators', True))
        generation_parameters = caption_settings.get('generation_parameters',
                                                     {})
        self.min_new_token_count_spin_box.setValue(
            generation_parameters.get('min_new_tokens', 1))
        self.max_new_token_count_spin_box.setValue(
            generation_parameters.get('max_new_tokens', 100))
        self.beam_count_spin_box.setValue(
            generation_parameters.get('num_beams', 1))
        self.length_penalty_spin_box.setValue(
            generation_parameters.get('length_penalty', 1))
        self.use_sampling_check_box.setChecked(
            generation_parameters.get('do_sample', False))
        self.temperature_spin_box.setValue(
            generation_parameters.get('temperature', 1))
        self.top_k_spin_box.setValue(generation_parameters.get('top_k', 50))
        self.top_p_spin_box.setValue(generation_parameters.get('top_p', 1))
        self.repetition_penalty_spin_box.setValue(
            generation_parameters.get('repetition_penalty', 1))
        self.no_repeat_ngram_size_spin_box.setValue(
            generation_parameters.get('no_repeat_ngram_size', 3))

    def get_caption_settings(self) -> dict:
        return {
            'prompt': self.prompt_text_edit.toPlainText(),
            'caption_start': self.caption_start_line_edit.text(),
            'forced_words': self.forced_words_line_edit.text(),
            'caption_position': self.caption_position_combo_box.currentText(),
            'model': self.model_combo_box.currentText(),
            'device': self.device_combo_box.currentText(),
            'load_in_4_bit': self.load_in_4_bit_check_box.isChecked(),
            'remove_tag_separators':
                self.remove_tag_separators_check_box.isChecked(),
            'generation_parameters': {
                'min_new_tokens': self.min_new_token_count_spin_box.value(),
                'max_new_tokens': self.max_new_token_count_spin_box.value(),
                'num_beams': self.beam_count_spin_box.value(),
                'length_penalty': self.length_penalty_spin_box.value(),
                'do_sample': self.use_sampling_check_box.isChecked(),
                'temperature': self.temperature_spin_box.value(),
                'top_k': self.top_k_spin_box.value(),
                'top_p': self.top_p_spin_box.value(),
                'repetition_penalty': self.repetition_penalty_spin_box.value(),
                'no_repeat_ngram_size':
                    self.no_repeat_ngram_size_spin_box.value()
            }
        }

    @Slot()
    def save_caption_settings(self):
        caption_settings = self.get_caption_settings()
        self.settings.setValue('caption_settings', caption_settings)


class InternLMXComposer2QuantizedForCausalLM(BaseGPTQForCausalLM):
    layers_block_name = 'model.layers'
    outside_layer_modules = ['vit', 'vision_proj', 'model.tok_embeddings',
                             'model.norm', 'output']
    inside_layer_modules = [
        ['attention.wqkv.linear'],
        ['attention.wo.linear'],
        ['feed_forward.w1.linear', 'feed_forward.w3.linear'],
        ['feed_forward.w2.linear'],
    ]


def format_cogvlm_prompt(prompt: str, caption_start: str) -> str:
    prompt = f'Question: {prompt} Answer:'
    if caption_start.strip():
        prompt += f' {caption_start}'
    return prompt


def monkey_patch_cogvlm(caption_start: str):
    """Monkey-patch the CogVLM module to support `caption_start`."""
    cogvlm_module = next((module for module_name, module in sys.modules.items()
                          if 'modeling_cogvlm' in module_name))
    cogvlm_module._history_to_prompt = (
        lambda _, __, prompt_: format_cogvlm_prompt(prompt_, caption_start))


def format_cogagent_prompt(prompt: str, caption_start: str) -> str:
    prompt = f'<EOI>Question: {prompt} Answer:'
    if caption_start.strip():
        prompt += f' {caption_start}'
    return prompt


def monkey_patch_cogagent(model, caption_start: str):
    """
    Monkey-patch the CogAgent module to support beam search and
    `caption_start`.
    """
    cogagent_module = next((module for module_name, module
                            in sys.modules.items()
                            if 'modeling_cogagent' in module_name))
    cogagent_module_source = getsource(cogagent_module)
    # Modify the source code to make beam search work (line 613 of
    # `modeling_cogagent.py`).
    cogagent_module_source = cogagent_module_source.replace('(batch_size, 1)',
                                                            '(1, 1)')
    # Replace the method in the class with the updated version.
    exec(cogagent_module_source, cogagent_module.__dict__)
    model.model.__class__.llm_forward = (cogagent_module.CogAgentModel
                                         .llm_forward)
    cogagent_module._history_to_prompt = {
        'chat_old': lambda _, prompt_: format_cogagent_prompt(prompt_,
                                                              caption_start)
    }


def get_cogvlm_cogagent_inputs(model_type: ModelType, model, processor,
                               text: str, pil_image: PilImage, beam_count: int,
                               device: torch.device,
                               dtype_argument: dict) -> dict:
    template_version = ('chat_old' if model_type == ModelType.COGAGENT
                        else None)
    model_inputs = model.build_conversation_input_ids(
        processor, query=text, images=[pil_image],
        template_version=template_version)
    cross_images = model_inputs.get('cross_images')
    model_inputs = {
        'input_ids': model_inputs['input_ids'].unsqueeze(0).to(device),
        'token_type_ids': (model_inputs['token_type_ids'].unsqueeze(0)
                           .to(device)),
        'attention_mask': (model_inputs['attention_mask'].unsqueeze(0)
                           .to(device)),
        'images': [
            [model_inputs['images'][0].to(device, **dtype_argument)]
            for _ in range(beam_count)
        ]
    }
    if model_type == ModelType.COGAGENT:
        model_inputs['cross_images'] = [
            [cross_images[0].to(device, **dtype_argument)]
            for _ in range(beam_count)
        ]
    return model_inputs


def get_xcomposer2_inputs(model, processor, load_in_4_bit: bool, text: str,
                          pil_image: PilImage, device: torch.device,
                          dtype_argument: dict) -> dict:
    input_embeddings_parts = []
    image_mask_parts = []
    processed_image = model.vis_processor(pil_image).unsqueeze(0).to(
        device, **dtype_argument)
    image_embeddings, *_ = model.img2emb(processed_image)
    for text_part in text.split('<ImageHere>'):
        part_token_ids = processor(
            text_part, return_tensors='pt').input_ids.to(device)
        if load_in_4_bit:
            part_embeddings = model.model.model.tok_embeddings(
                part_token_ids)
        else:
            part_embeddings = model.model.tok_embeddings(
                part_token_ids)
        input_embeddings_parts.append(part_embeddings)
        image_mask_parts.append(torch.zeros(part_embeddings.shape[:2]))
    input_embeddings_parts.insert(1, image_embeddings[0].unsqueeze(0))
    image_mask_parts.insert(
        1, torch.ones(1, image_embeddings[0].shape[0]))
    input_embeddings = torch.cat(
        input_embeddings_parts, dim=1).to(device)
    image_mask = torch.cat(image_mask_parts, dim=1).bool().to(device)
    eos_token_id = [
        processor.eos_token_id,
        processor.convert_tokens_to_ids(['[UNUSED_TOKEN_145]'])[0]
    ]
    model_inputs = {
        'inputs_embeds': input_embeddings,
        'im_mask': image_mask,
        'eos_token_id': eos_token_id
    }
    return model_inputs


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
    """Add a caption to a list of tags and return the new list."""
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


class CaptionThread(QThread):
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

    def get_model_type(self) -> ModelType:
        model_id = self.caption_settings['model']
        if 'llava' in model_id.lower():
            return ModelType.LLAVA
        if 'kosmos' in model_id.lower():
            return ModelType.KOSMOS
        if 'cogvlm' in model_id.lower():
            return ModelType.COGVLM
        if 'cogagent' in model_id.lower():
            return ModelType.COGAGENT
        if 'xcomposer2' in model_id.lower():
            return ModelType.XCOMPOSER2
        return ModelType.OTHER

    def check_xcomposer2_settings_consistency(self) -> bool:
        model_id = self.caption_settings['model']
        is_4_bit_model = '4bit' in model_id
        device = self.caption_settings['device']
        load_in_4_bit = self.caption_settings['load_in_4_bit']
        error_message = None
        if is_4_bit_model:
            if device == Device.CPU:
                error_message = (
                    'This version of the model can only be loaded on a GPU. '
                    'Select internlm/internlm-xcomposer2-vl-7b if you want to '
                    'load the model on the CPU.')
            if not load_in_4_bit:
                error_message = (
                    'This version of the model can only be loaded in 4-bit. '
                    'Select internlm/internlm-xcomposer2-vl-7b if you do not '
                    'want to load the model in 4-bit.')
        else:
            if load_in_4_bit:
                error_message = (
                    'This version of the model cannot be loaded in 4-bit. '
                    'Select internlm/internlm-xcomposer2-vl-7b-4bit if you '
                    'want to load the model in 4-bit.')
        if error_message:
            self.clear_console_text_edit_requested.emit()
            print(error_message)
            return False
        return True

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
            processor_class = (AutoTokenizer
                               if model_type == ModelType.XCOMPOSER2
                               else AutoProcessor)
            processor = processor_class.from_pretrained(model_id,
                                                        trust_remote_code=True)
        self.parent().processor = processor
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
                                             ModelType.XCOMPOSER2)
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
        if not load_in_4_bit:
            model.to(device)
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
                              ModelType.COGAGENT):
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
        model_type = self.get_model_type()
        if model_type == ModelType.XCOMPOSER2:
            if not self.check_xcomposer2_settings_consistency():
                return
        processor, model = self.load_processor_and_model(device, model_type)
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
            with torch.inference_mode():
                generated_token_ids = model.generate(
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


@Slot()
def restore_stdout_and_stderr():
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__


class AutoCaptioner(QDockWidget):
    caption_generated = Signal(QModelIndex, str, list)

    def __init__(self, image_list_model: ImageListModel,
                 image_list: ImageList):
        super().__init__()
        self.image_list_model = image_list_model
        self.image_list = image_list
        self.settings = get_settings()
        self.processor = None
        self.model = None
        self.model_id: str | None = None
        self.model_device_type: str | None = None
        self.is_model_loaded_in_4_bit = None
        # Whether the last block of text in the console text edit should be
        # replaced with the next block of text that is outputted.
        self.replace_last_console_text_edit_block = False

        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('auto_captioner')
        self.setWindowTitle('Auto-Captioner')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.caption_button = TallPushButton('Run Auto-Captioner')
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat('%v / %m images captioned (%p%)')
        self.progress_bar.hide()
        self.console_text_edit = QPlainTextEdit()
        set_text_edit_height(self.console_text_edit, 4)
        self.console_text_edit.setReadOnly(True)
        self.console_text_edit.hide()
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.caption_button)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.console_text_edit)
        self.caption_settings_form = CaptionSettingsForm(self.settings)
        layout.addLayout(self.caption_settings_form)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(container)
        self.setWidget(scroll_area)

        self.caption_button.clicked.connect(self.generate_captions)

    @Slot(str)
    def update_console_text_edit(self, text: str):
        # '\x1b[A' is the ANSI escape sequence for moving the cursor up.
        if text == '\x1b[A':
            self.replace_last_console_text_edit_block = True
            return
        text = text.strip()
        if not text:
            return
        if self.console_text_edit.isHidden():
            self.console_text_edit.show()
        if self.replace_last_console_text_edit_block:
            self.replace_last_console_text_edit_block = False
            # Select and remove the last block of text.
            self.console_text_edit.moveCursor(QTextCursor.End)
            self.console_text_edit.moveCursor(QTextCursor.StartOfBlock,
                                              QTextCursor.KeepAnchor)
            self.console_text_edit.textCursor().removeSelectedText()
            # Delete the newline.
            self.console_text_edit.textCursor().deletePreviousChar()
        self.console_text_edit.appendPlainText(text)

    @Slot()
    def generate_captions(self):
        selected_image_indices = self.image_list.get_selected_image_indices()
        selected_image_count = len(selected_image_indices)
        if selected_image_count > 1:
            reply = get_confirmation_dialog_reply(
                title='Generate Captions',
                question=f'Caption {selected_image_count} selected images?')
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.caption_button.setEnabled(False)
        caption_settings = self.caption_settings_form.get_caption_settings()
        if caption_settings['caption_position'] != CaptionPosition.DO_NOT_ADD:
            self.image_list_model.add_to_undo_stack(
                action_name=f'Generate '
                            f'{pluralize("Caption", selected_image_count)}',
                should_ask_for_confirmation=selected_image_count > 1)
        if selected_image_count > 1:
            self.progress_bar.setRange(0, selected_image_count)
            self.progress_bar.setValue(0)
            self.progress_bar.show()
        tag_separator = get_separator(self.settings)
        models_directory_path: str = self.settings.value(
            'models_directory_path', type=str)
        models_directory_path: Path | None = (Path(models_directory_path)
                                              if models_directory_path
                                              else None)
        caption_thread = CaptionThread(self, self.image_list_model,
                                       selected_image_indices,
                                       caption_settings, tag_separator,
                                       models_directory_path)
        caption_thread.text_outputted.connect(self.update_console_text_edit)
        caption_thread.clear_console_text_edit_requested.connect(
            self.console_text_edit.clear)
        caption_thread.caption_generated.connect(self.caption_generated)
        caption_thread.progress_bar_update_requested.connect(
            self.progress_bar.setValue)
        caption_thread.finished.connect(restore_stdout_and_stderr)
        caption_thread.finished.connect(
            lambda: self.caption_button.setEnabled(True))
        caption_thread.finished.connect(self.progress_bar.hide)
        caption_thread.start()
