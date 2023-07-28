import os
import sys
from enum import Enum, auto

import torch
from PIL import Image as PilImage
from PySide6.QtCore import QModelIndex, QThread, Qt, Signal, Slot
from PySide6.QtGui import QFontMetrics, QTextCursor
from PySide6.QtWidgets import (QComboBox, QDockWidget, QFormLayout, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)
from huggingface_hub import try_to_load_from_cache
from transformers import AutoProcessor, Blip2ForConditionalGeneration

from models.image_list_model import ImageListModel
from utils.image import Image
from utils.utils import get_confirmation_dialog_reply
from widgets.image_list import ImageList

# Disable the warning about windows not supporting symlinks.
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

BLIP_2_HUGGINGFACE_REPOSITORY_ID = 'Salesforce/blip2-opt-2.7b'


class CaptionPosition(Enum):
    BEFORE_FIRST_TAG = auto()
    AFTER_LAST_TAG = auto()
    OVERWRITE_FIRST_TAG = auto()
    OVERWRITE_ALL_TAGS = auto()


class Device(Enum):
    GPU = auto()
    CPU = auto()


class CaptionSettingsForm(QFormLayout):
    def __init__(self):
        super().__init__()
        self.setLabelAlignment(Qt.AlignRight)

        self.caption_start_line_edit = QLineEdit()
        self.caption_position_combo_box = QComboBox()
        self.caption_position_combo_box.addItem(
            'Insert before first tag',
            userData=CaptionPosition.BEFORE_FIRST_TAG)
        self.caption_position_combo_box.addItem(
            'Insert after last tag',
            userData=CaptionPosition.AFTER_LAST_TAG)
        self.caption_position_combo_box.addItem(
            'Overwrite first tag',
            userData=CaptionPosition.OVERWRITE_FIRST_TAG)
        self.caption_position_combo_box.addItem(
            'Overwrite all tags',
            userData=CaptionPosition.OVERWRITE_ALL_TAGS)
        self.device_combo_box = QComboBox()
        self.device_combo_box.addItem('GPU if available', userData=Device.GPU)
        self.device_combo_box.addItem('CPU', userData=Device.CPU)
        self.addRow('Start caption with:', self.caption_start_line_edit)
        self.addRow('Caption position:', self.caption_position_combo_box)
        self.addRow('Device:', self.device_combo_box)

    def get_caption_settings(self) -> dict:
        return {
            'caption_start': self.caption_start_line_edit.text(),
            'caption_position': self.caption_position_combo_box.currentData(),
            'device': self.device_combo_box.currentData()
        }


def add_caption_to_tags(tags: list[str], caption: str,
                        caption_position: CaptionPosition) -> list[str]:
    """Add a caption to a list of tags and return the new list."""
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
        # If the processor and model were previously loaded, use them.
        processor = self.parent().processor
        model = self.parent().model
        if not processor or not model:
            print(f'Loading BLIP-2 model...')
            # Check if the model is downloaded by checking the cache for the
            # config file. The model might not be fully downloaded even if the
            # config file is in the cache, but it does not matter because the
            # model will then be downloaded when trying to load it.
            if not try_to_load_from_cache(BLIP_2_HUGGINGFACE_REPOSITORY_ID,
                                          filename='config.json'):
                print('BLIP-2 model not found. Downloading...')
            processor = AutoProcessor.from_pretrained(
                BLIP_2_HUGGINGFACE_REPOSITORY_ID)
            model = Blip2ForConditionalGeneration.from_pretrained(
                BLIP_2_HUGGINGFACE_REPOSITORY_ID)
            self.parent().processor = processor
            self.parent().model = model
        if self.caption_settings['device'] == Device.CPU:
            device = torch.device('cpu')
        else:
            device = torch.device('cuda' if torch.cuda.is_available()
                                  else 'cpu')
        model.to(device)
        model.eval()
        self.clear_text_edit_requested.emit()
        print(f'Captioning... (device: {device})')
        for i, image_index in enumerate(self.selected_image_indices):
            image: Image = self.image_list_model.data(image_index, Qt.UserRole)
            pil_image = PilImage.open(image.path)
            caption_start = self.caption_settings['caption_start']
            model_inputs = processor(pil_image, text=caption_start,
                                     return_tensors='pt').to(device)
            generated_token_ids = model.generate(**model_inputs,
                                                 max_new_tokens=50)
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
        # Whether the last block of text in the text edit should be replaced
        # with the next block of text that is outputted.
        self.replace_last_text_edit_block = False

        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('blip_2_captioner')
        self.setWindowTitle('BLIP-2 Captioner')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.caption_button = QPushButton('Caption with BLIP-2')
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat('%v / %m images captioned (%p%)')
        self.progress_bar.hide()
        self.text_edit = QPlainTextEdit()
        # Set the height of the text edit to 4 lines.
        # From https://stackoverflow.com/a/46997337.
        document = self.text_edit.document()
        font_metrics = QFontMetrics(document.defaultFont())
        margins = self.text_edit.contentsMargins()
        height = (font_metrics.lineSpacing() * 4
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
        selected_proxy_image_indices = (self.image_list.list_view
                                        .selectedIndexes())
        selected_image_indices = [
            self.image_list.proxy_image_list_model.mapToSource(index)
            for index in selected_proxy_image_indices]
        selected_image_count = len(selected_image_indices)
        if selected_image_count > 1:
            reply = get_confirmation_dialog_reply(
                title='Caption with BLIP-2',
                question=f'Caption {selected_image_count} selected images?')
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.caption_button.setEnabled(False)
        if selected_image_count > 1:
            self.progress_bar.setRange(0, selected_image_count)
            self.progress_bar.setValue(0)
            self.progress_bar.show()
        caption_settings = self.caption_settings_form.get_caption_settings()
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
