import gc
import sys
from enum import Enum

import torch
from PIL import Image as PilImage
from PySide6.QtCore import QModelIndex, QSettings, QThread, Qt, Signal, Slot
from PySide6.QtGui import QFontMetrics, QTextCursor
from PySide6.QtWidgets import (QAbstractScrollArea, QComboBox, QDockWidget,
                               QDoubleSpinBox, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QProgressBar, QScrollArea,
                               QSpinBox, QVBoxLayout, QWidget)
from huggingface_hub import try_to_load_from_cache
from transformers import (AutoModelForVision2Seq, AutoProcessor,
                          BitsAndBytesConfig)

from models.image_list_model import ImageListModel
from utils.big_widgets import BigCheckBox, TallPushButton
from utils.image import Image
from utils.settings import get_separator, get_settings
from utils.utils import get_confirmation_dialog_reply, pluralize
from widgets.image_list import ImageList

MODELS = [
    'llava-hf/bakLlava-v1-hf',
    'llava-hf/llava-1.5-7b-hf',
    'llava-hf/llava-1.5-13b-hf',
    'Salesforce/blip2-opt-2.7b',
    'Salesforce/blip2-opt-6.7b',
    'Salesforce/blip2-opt-6.7b-coco',
    'Salesforce/blip2-flan-t5-xl',
    'Salesforce/blip2-flan-t5-xxl'
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
        self.caption_position_combo_box = QComboBox()
        self.caption_position_combo_box.addItems(list(CaptionPosition))
        self.model_combo_box = QComboBox()
        self.model_combo_box.setEditable(True)
        self.model_combo_box.addItems(MODELS)
        self.device_combo_box = QComboBox()
        self.device_combo_box.addItems(list(Device))
        self.basic_settings_form.addRow('Prompt', self.prompt_text_edit)
        self.basic_settings_form.addRow('Start caption with',
                                        self.caption_start_line_edit)
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

        self.toggle_advanced_settings_form_button = TallPushButton(
            'Show Advanced Settings')

        self.advanced_settings_form_container = QWidget()
        advanced_settings_form = QFormLayout(
            self.advanced_settings_form_container)
        advanced_settings_form.setLabelAlignment(Qt.AlignRight)
        advanced_settings_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.convert_tag_separators_to_spaces_check_box = BigCheckBox()
        self.min_new_token_count_spin_box = QSpinBox()
        self.min_new_token_count_spin_box.setRange(1, 999)
        self.max_new_token_count_spin_box = QSpinBox()
        self.max_new_token_count_spin_box.setRange(1, 999)
        self.beam_count_spin_box = QSpinBox()
        self.beam_count_spin_box.setRange(1, 99)
        self.length_penalty_spin_box = QDoubleSpinBox()
        self.length_penalty_spin_box.setRange(-5, 5)
        self.length_penalty_spin_box.setSingleStep(0.1)
        self.use_sampling_check_box = BigCheckBox()
        self.temperature_spin_box = QDoubleSpinBox()
        # The temperature must be positive.
        self.temperature_spin_box.setRange(0.01, 2)
        self.temperature_spin_box.setSingleStep(0.01)
        self.top_k_spin_box = QSpinBox()
        self.top_k_spin_box.setRange(0, 200)
        self.top_p_spin_box = QDoubleSpinBox()
        self.top_p_spin_box.setRange(0, 1)
        self.top_p_spin_box.setSingleStep(0.01)
        self.repetition_penalty_spin_box = QDoubleSpinBox()
        self.repetition_penalty_spin_box.setRange(1, 2)
        self.repetition_penalty_spin_box.setSingleStep(0.01)
        self.no_repeat_ngram_size_spin_box = QSpinBox()
        self.no_repeat_ngram_size_spin_box.setRange(0, 5)
        advanced_settings_form.addRow(
            'Tag separators to spaces',
            self.convert_tag_separators_to_spaces_check_box)
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
        self.convert_tag_separators_to_spaces_check_box.stateChanged.connect(
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
        self.caption_position_combo_box.setCurrentText(
            caption_settings.get('caption_position',
                                 CaptionPosition.BEFORE_FIRST_TAG))
        self.model_combo_box.setCurrentText(
            caption_settings.get('model', MODELS[0]))
        self.device_combo_box.setCurrentText(
            caption_settings.get('device', Device.GPU))
        self.load_in_4_bit_check_box.setChecked(
            caption_settings.get('load_in_4_bit', True))
        self.convert_tag_separators_to_spaces_check_box.setChecked(
            caption_settings.get('convert_tag_separators_to_spaces', True))
        generation_parameters = caption_settings.get('generation_parameters',
                                                     {})
        self.min_new_token_count_spin_box.setValue(
            generation_parameters.get('min_new_tokens', 1))
        self.max_new_token_count_spin_box.setValue(
            generation_parameters.get('max_new_tokens', 50))
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
            generation_parameters.get('repetition_penalty', 1.15))
        self.no_repeat_ngram_size_spin_box.setValue(
            generation_parameters.get('no_repeat_ngram_size', 3))

    def get_caption_settings(self) -> dict:
        return {
            'prompt': self.prompt_text_edit.toPlainText(),
            'caption_start': self.caption_start_line_edit.text(),
            'caption_position': self.caption_position_combo_box.currentText(),
            'model': self.model_combo_box.currentText(),
            'device': self.device_combo_box.currentText(),
            'load_in_4_bit': self.load_in_4_bit_check_box.isChecked(),
            'convert_tag_separators_to_spaces':
                self.convert_tag_separators_to_spaces_check_box.isChecked(),
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
                 caption_settings: dict, tag_separator: str):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.selected_image_indices = selected_image_indices
        self.caption_settings = caption_settings
        self.tag_separator = tag_separator

    def run(self):
        # Redirect `stdout` and `stderr` so that the outputs are
        # displayed in the console text edit.
        sys.stdout = self
        sys.stderr = self
        if self.caption_settings['device'] == Device.CPU:
            device = torch.device('cpu')
        else:
            device = torch.device('cuda:0' if torch.cuda.is_available()
                                  else 'cpu')
        # If the processor and model were previously loaded, use them.
        processor = self.parent().processor
        model = self.parent().model
        model_id = self.caption_settings['model']
        # Only GPUs support 4-bit quantization.
        load_in_4_bit = (self.caption_settings['load_in_4_bit']
                         and device.type == 'cuda')
        if (not model or self.parent().model_id != model_id
                or self.parent().model_device_type != device.type
                or self.parent().is_model_loaded_in_4_bit != load_in_4_bit):
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
            # Check if the model is downloaded by checking the cache for the
            # config file. The model might not be fully downloaded even if the
            # config file is in the cache, but it does not matter because the
            # model will then be downloaded when trying to load it.
            if not try_to_load_from_cache(model_id, filename='config.json'):
                print('Model not found. Downloading...')
            processor = AutoProcessor.from_pretrained(model_id)
            self.parent().processor = processor
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
            model = AutoModelForVision2Seq.from_pretrained(
                model_id, device_map=device,
                quantization_config=quantization_config, **dtype_argument)
            self.parent().model = model
            self.parent().model_id = model_id
            self.parent().model_device_type = device.type
            self.parent().is_model_loaded_in_4_bit = load_in_4_bit
        if not load_in_4_bit:
            model.to(device)
        model.eval()
        self.clear_console_text_edit_requested.emit()
        print(f'Captioning... (device: {device})')
        for i, image_index in enumerate(self.selected_image_indices):
            image: Image = self.image_list_model.data(image_index, Qt.UserRole)
            pil_image = PilImage.open(image.path)
            prompt = self.caption_settings['prompt']
            caption_start = self.caption_settings['caption_start']
            is_llava_model = 'llava' in model_id.lower()
            if is_llava_model:
                if not prompt:
                    prompt = 'Briefly caption the image.'
                prompt = f'USER: <image>\n{prompt}\nASSISTANT:'
            if prompt and caption_start:
                text = f'{prompt} {caption_start}'
            else:
                text = prompt + caption_start
            dtype_argument = ({'dtype': torch.float16}
                              if device.type == 'cuda' else {})
            model_inputs = (processor(text=text, images=pil_image,
                                      return_tensors='pt')
                            .to(device, **dtype_argument))
            generation_parameters = self.caption_settings[
                'generation_parameters']
            generated_token_ids = model.generate(**model_inputs,
                                                 **generation_parameters)
            generated_text = processor.batch_decode(
                generated_token_ids, skip_special_tokens=True)[0]
            if is_llava_model:
                prompt = prompt.replace('<image>', ' ')
            if prompt.strip() and generated_text.startswith(prompt):
                # Autoregressive models like LLaVA include the prompt in the
                # generated text.
                caption = generated_text[len(prompt):].strip()
            else:
                # Sequence-to-sequence models like BLIP-2 return only the
                # new tokens in the generated text.
                caption = (caption_start + generated_text).strip()
            if self.caption_settings['convert_tag_separators_to_spaces']:
                caption = caption.replace(self.tag_separator, ' ')
            caption_position = self.caption_settings['caption_position']
            tags = add_caption_to_tags(image.tags, caption, caption_position)
            self.caption_generated.emit(image_index, caption, tags)
            selected_image_count = len(self.selected_image_indices)
            if selected_image_count > 1:
                self.progress_bar_update_requested.emit(i + 1)
            if i == 0:
                self.clear_console_text_edit_requested.emit()
            print(f'{image.path.name}:\n{caption}')

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
        caption_thread = CaptionThread(self, self.image_list_model,
                                       selected_image_indices,
                                       caption_settings, tag_separator)
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
