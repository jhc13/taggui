import gc
import os
import sys
from enum import Enum

import torch
from PIL import Image as PilImage
from PySide6.QtCore import QModelIndex, QThread, Qt, Signal, Slot
from PySide6.QtGui import QFontMetrics, QTextCursor
from PySide6.QtWidgets import (QAbstractScrollArea, QComboBox, QDockWidget,
                               QDoubleSpinBox, QFormLayout, QFrame, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)
from huggingface_hub import try_to_load_from_cache
from transformers import AutoProcessor, Blip2ForConditionalGeneration

from models.image_list_model import ImageListModel
from utils.big_widgets import BigCheckBox, TallPushButton
from utils.image import Image
from utils.settings import get_settings
from utils.utils import get_confirmation_dialog_reply
from widgets.image_list import ImageList

# Disable the warning about windows not supporting symlinks.
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

BLIP_2_HUGGINGFACE_REPOSITORY_ID = 'Salesforce/blip2-opt-2.7b'


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


class CaptionSettingsForm(QVBoxLayout):
    def __init__(self):
        super().__init__()
        self.settings = get_settings()

        basic_settings_form = QFormLayout()
        basic_settings_form.setLabelAlignment(Qt.AlignRight)
        self.caption_start_line_edit = QLineEdit()
        self.caption_position_combo_box = QComboBox()
        self.caption_position_combo_box.addItems(list(CaptionPosition))
        self.device_combo_box = QComboBox()
        self.device_combo_box.addItems(list(Device))
        basic_settings_form.addRow('Start caption with:',
                                   self.caption_start_line_edit)
        basic_settings_form.addRow('Caption position:',
                                   self.caption_position_combo_box)
        basic_settings_form.addRow('Device:', self.device_combo_box)

        horizontal_line = QFrame()
        horizontal_line.setFrameShape(QFrame.Shape.HLine)
        horizontal_line.setFrameShadow(QFrame.Shadow.Raised)
        self.toggle_advanced_settings_form_button = TallPushButton(
            'Show Advanced Settings')

        advanced_settings_form_container = QWidget()
        self.advanced_settings_form_scroll_area = QScrollArea()
        self.advanced_settings_form_scroll_area.setWidgetResizable(True)
        self.advanced_settings_form_scroll_area.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.advanced_settings_form_scroll_area.setFrameShape(
            QFrame.Shape.NoFrame)
        self.advanced_settings_form_scroll_area.setWidget(
            advanced_settings_form_container)
        self.advanced_settings_form_scroll_area.hide()
        advanced_settings_form = QFormLayout(
            advanced_settings_form_container)
        advanced_settings_form.setLabelAlignment(Qt.AlignRight)
        self.min_new_token_count_spin_box = QSpinBox()
        self.min_new_token_count_spin_box.setRange(1, 99)
        self.max_new_token_count_spin_box = QSpinBox()
        self.max_new_token_count_spin_box.setRange(1, 99)
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
        advanced_settings_form.addRow('Minimum tokens:',
                                      self.min_new_token_count_spin_box)
        advanced_settings_form.addRow('Maximum tokens:',
                                      self.max_new_token_count_spin_box)
        advanced_settings_form.addRow('Number of beams:',
                                      self.beam_count_spin_box)
        advanced_settings_form.addRow('Length penalty:',
                                      self.length_penalty_spin_box)
        advanced_settings_form.addRow('Use sampling:',
                                      self.use_sampling_check_box)
        advanced_settings_form.addRow('Temperature:',
                                      self.temperature_spin_box)
        advanced_settings_form.addRow('Top-k:', self.top_k_spin_box)
        advanced_settings_form.addRow('Top-p:', self.top_p_spin_box)
        advanced_settings_form.addRow('Repetition penalty:',
                                      self.repetition_penalty_spin_box)
        advanced_settings_form.addRow('No repeat n-gram size:',
                                      self.no_repeat_ngram_size_spin_box)

        self.addLayout(basic_settings_form)
        self.addWidget(horizontal_line)
        self.addWidget(self.toggle_advanced_settings_form_button)
        self.addWidget(self.advanced_settings_form_scroll_area)
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
        self.caption_start_line_edit.textChanged.connect(
            self.save_caption_settings)
        self.caption_position_combo_box.currentTextChanged.connect(
            self.save_caption_settings)
        self.device_combo_box.currentTextChanged.connect(
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

    @Slot()
    def toggle_advanced_settings_form(self):
        if self.advanced_settings_form_scroll_area.isHidden():
            self.advanced_settings_form_scroll_area.show()
            self.toggle_advanced_settings_form_button.setText(
                'Hide Advanced Settings')
        else:
            self.advanced_settings_form_scroll_area.hide()
            self.toggle_advanced_settings_form_button.setText(
                'Show Advanced Settings')

    def load_caption_settings(self):
        caption_settings: dict = self.settings.value('caption_settings')
        if caption_settings is None:
            caption_settings = {}
        self.caption_start_line_edit.setText(
            caption_settings.get('caption_start', ''))
        self.caption_position_combo_box.setCurrentText(
            caption_settings.get('caption_position',
                                 CaptionPosition.BEFORE_FIRST_TAG))
        self.device_combo_box.setCurrentText(
            caption_settings.get('device', Device.GPU))
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
            'caption_start': self.caption_start_line_edit.text(),
            'caption_position': self.caption_position_combo_box.currentText(),
            'device': self.device_combo_box.currentText(),
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
    clear_text_edit_requested = Signal()
    # The image index, the caption, and the tags with the caption added. The
    # third parameter must be declared as `list` instead of `list[str]` for it
    # to work.
    caption_generated = Signal(QModelIndex, str, list)
    progress_bar_update_requested = Signal(int)

    def __init__(self, parent, image_list_model: ImageListModel,
                 selected_image_indices: list[QModelIndex],
                 caption_settings: dict):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.selected_image_indices = selected_image_indices
        self.caption_settings = caption_settings

    def run(self):
        # Redirect `stdout` and `stderr` so that the outputs are
        # displayed in the text edit.
        sys.stdout = self
        sys.stderr = self
        if self.caption_settings['device'] == Device.CPU:
            device = torch.device('cpu')
        else:
            device = torch.device('cuda' if torch.cuda.is_available()
                                  else 'cpu')
        # If the processor and model were previously loaded, use them.
        processor = self.parent().processor
        model = self.parent().model
        do_device_types_match = (self.parent().model_device_type
                                 == device.type)
        if not model or not do_device_types_match:
            if not do_device_types_match:
                # Garbage collect the previous model to free up memory.
                self.parent().model = None
                del model
                gc.collect()
            self.clear_text_edit_requested.emit()
            print(f'Loading BLIP-2 model...')
            # Check if the model is downloaded by checking the cache for the
            # config file. The model might not be fully downloaded even if the
            # config file is in the cache, but it does not matter because the
            # model will then be downloaded when trying to load it.
            if not try_to_load_from_cache(BLIP_2_HUGGINGFACE_REPOSITORY_ID,
                                          filename='config.json'):
                print('BLIP-2 model not found. Downloading...')
            if not processor:
                processor = AutoProcessor.from_pretrained(
                    BLIP_2_HUGGINGFACE_REPOSITORY_ID)
                self.parent().processor = processor
            dtype_argument = ({'torch_dtype': torch.float16}
                              if device.type == 'cuda' else {})
            model = Blip2ForConditionalGeneration.from_pretrained(
                BLIP_2_HUGGINGFACE_REPOSITORY_ID, device_map=device,
                **dtype_argument)
            self.parent().model = model
            self.parent().model_device_type = device.type
        model.to(device)
        model.eval()
        self.clear_text_edit_requested.emit()
        print(f'Captioning... (device: {device})')
        for i, image_index in enumerate(self.selected_image_indices):
            image: Image = self.image_list_model.data(image_index, Qt.UserRole)
            pil_image = PilImage.open(image.path)
            caption_start = self.caption_settings['caption_start']
            dtype_argument = ({'dtype': torch.float16}
                              if device.type == 'cuda' else {})
            model_inputs = (processor(pil_image, text=caption_start,
                                      return_tensors='pt')
                            .to(device, **dtype_argument))
            generation_parameters = self.caption_settings[
                'generation_parameters']
            generated_token_ids = model.generate(**model_inputs,
                                                 **generation_parameters)
            generated_text = processor.batch_decode(
                generated_token_ids, skip_special_tokens=True)[0]
            caption = (caption_start + generated_text).strip()
            caption_position = self.caption_settings['caption_position']
            tags = add_caption_to_tags(image.tags, caption, caption_position)
            self.caption_generated.emit(image_index, caption, tags)
            selected_image_count = len(self.selected_image_indices)
            if selected_image_count > 1:
                self.progress_bar_update_requested.emit(i + 1)
            if i == 0:
                self.clear_text_edit_requested.emit()
            print(f'{image.path.name}:\n{caption}')

    def write(self, text: str):
        self.text_outputted.emit(text)


@Slot()
def restore_stdout_and_stderr():
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__


class Blip2Captioner(QDockWidget):
    caption_generated = Signal(QModelIndex, str, list)

    def __init__(self, image_list_model: ImageListModel,
                 image_list: ImageList):
        super().__init__()
        self.image_list_model = image_list_model
        self.image_list = image_list
        self.processor = None
        self.model = None
        self.model_device_type: str | None = None
        # Whether the last block of text in the text edit should be replaced
        # with the next block of text that is outputted.
        self.replace_last_text_edit_block = False

        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('blip_2_captioner')
        self.setWindowTitle('BLIP-2 Captioner')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.caption_button = TallPushButton('Caption With BLIP-2')
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat('%v / %m images captioned (%p%)')
        self.progress_bar.hide()
        self.text_edit = QPlainTextEdit()
        # Set the height of the text edit to 5 lines.
        # From https://stackoverflow.com/a/46997337.
        document = self.text_edit.document()
        font_metrics = QFontMetrics(document.defaultFont())
        margins = self.text_edit.contentsMargins()
        height = (font_metrics.lineSpacing() * 5
                  + margins.top() + margins.bottom()
                  + document.documentMargin() * 2
                  + self.text_edit.frameWidth() * 2)
        self.text_edit.setFixedHeight(height)
        self.text_edit.setReadOnly(True)
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.caption_button)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.text_edit)
        self.caption_settings_form = CaptionSettingsForm()
        layout.addLayout(self.caption_settings_form)
        self.setWidget(container)

        self.caption_button.clicked.connect(self.caption_with_blip_2)

    @Slot(str)
    def update_text_edit(self, text: str):
        # '\x1b[A' is the ANSI escape sequence for moving the cursor up.
        if text == '\x1b[A':
            self.replace_last_text_edit_block = True
            return
        text = text.strip()
        if not text:
            return
        if self.replace_last_text_edit_block:
            self.replace_last_text_edit_block = False
            # Select and remove the last block of text.
            self.text_edit.moveCursor(QTextCursor.End)
            self.text_edit.moveCursor(QTextCursor.StartOfBlock,
                                      QTextCursor.KeepAnchor)
            self.text_edit.textCursor().removeSelectedText()
            # Delete the newline.
            self.text_edit.textCursor().deletePreviousChar()
        self.text_edit.appendPlainText(text)

    @Slot()
    def caption_with_blip_2(self):
        selected_image_indices = self.image_list.get_selected_image_indices()
        selected_image_count = len(selected_image_indices)
        if selected_image_count > 1:
            reply = get_confirmation_dialog_reply(
                title='Caption with BLIP-2',
                question=f'Caption {selected_image_count} selected images?')
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.caption_button.setEnabled(False)
        caption_settings = self.caption_settings_form.get_caption_settings()
        if caption_settings['caption_position'] != CaptionPosition.DO_NOT_ADD:
            self.image_list_model.add_to_undo_stack(
                action_name='Caption with BLIP-2',
                should_ask_for_confirmation=selected_image_count > 1)
        if selected_image_count > 1:
            self.progress_bar.setRange(0, selected_image_count)
            self.progress_bar.setValue(0)
            self.progress_bar.show()
        caption_thread = CaptionThread(self, self.image_list_model,
                                       selected_image_indices,
                                       caption_settings)
        caption_thread.text_outputted.connect(self.update_text_edit)
        caption_thread.clear_text_edit_requested.connect(self.text_edit.clear)
        caption_thread.caption_generated.connect(self.caption_generated)
        caption_thread.progress_bar_update_requested.connect(
            self.progress_bar.setValue)
        caption_thread.finished.connect(restore_stdout_and_stderr)
        caption_thread.finished.connect(
            lambda: self.caption_button.setEnabled(True))
        caption_thread.finished.connect(self.progress_bar.hide)
        caption_thread.start()
