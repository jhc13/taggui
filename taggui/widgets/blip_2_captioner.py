import os
import sys

import torch
from PIL import Image as PilImage
from PySide6.QtCore import QModelIndex, QThread, Qt, Signal, Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QDockWidget, QMessageBox, QPushButton,
                               QTextEdit, QVBoxLayout, QWidget)
from huggingface_hub import try_to_load_from_cache
from transformers import AutoProcessor, Blip2ForConditionalGeneration

from models.image_list_model import ImageListModel
from utils.image import Image
from utils.utils import get_confirmation_dialog_reply
from widgets.image_list import ImageList

# Disable the warning about windows not supporting symlinks.
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

BLIP_2_HUGGINGFACE_REPOSITORY_ID = 'Salesforce/blip2-opt-2.7b'


def add_caption_to_tags(tags: list[str], caption: str) -> list[str]:
    """Add a caption to a list of tags and return the new list."""
    # Make a copy of the tags so that the tags in the image list model are not
    # modified.
    tags = tags.copy()
    tags.insert(0, caption)
    return tags


class CaptionThread(QThread):
    text_outputted = Signal(str)
    clear_text_edit_requested = Signal()
    # The image index, the caption, and the tags with the caption added. The
    # third parameter must be declared as `list` instead of `list[str]` for it
    # to work.
    caption_generated = Signal(QModelIndex, str, list)

    def __init__(self, parent, image_list_model: ImageListModel,
                 selected_image_indices: list[QModelIndex]):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.selected_image_indices = selected_image_indices

    def run(self):
        # Redirect `stdout` and `stderr` so that the outputs are
        # displayed in the text edit.
        sys.stdout = self
        sys.stderr = self
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        # If the processor and model were previously loaded, use them.
        processor = self.parent().processor
        model = self.parent().model
        if not processor or not model:
            print(f'Loading BLIP-2 model... (device: {device})')
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
        model.to(device)
        model.eval()
        self.clear_text_edit_requested.emit()
        print('Captioning...')
        for i, image_index in enumerate(self.selected_image_indices):
            image: Image = self.image_list_model.data(image_index, Qt.UserRole)
            pil_image = PilImage.open(image.path)
            model_inputs = processor(pil_image, return_tensors='pt').to(device)
            caption_token_ids = model.generate(**model_inputs,
                                               max_new_tokens=100)
            caption = processor.batch_decode(
                caption_token_ids, skip_special_tokens=True)[0].strip()
            tags = add_caption_to_tags(image.tags, caption)
            self.caption_generated.emit(image_index, caption, tags)
            self.clear_text_edit_requested.emit()
            selected_image_count = len(self.selected_image_indices)
            if selected_image_count > 1:
                captioned_ratio = (i + 1) / selected_image_count
                print(f'{i + 1} / {selected_image_count} images captioned '
                      f'({captioned_ratio:.1%})')
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
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        self.caption_button = QPushButton('Caption with BLIP-2')
        self.caption_button.clicked.connect(self.caption_with_blip_2)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout = QVBoxLayout(container)
        layout.addWidget(self.caption_button)
        layout.addWidget(self.text_edit)
        self.setWidget(container)

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
        self.text_edit.append(text)

    @Slot()
    def caption_with_blip_2(self):
        selected_proxy_image_indices = (self.image_list.list_view
                                        .selectedIndexes())
        selected_image_indices = [
            self.image_list.proxy_image_list_model.mapToSource(index)
            for index in selected_proxy_image_indices]
        if len(selected_image_indices) > 1:
            reply = get_confirmation_dialog_reply(
                title='Caption with BLIP-2',
                question=f'Caption {len(selected_image_indices)} selected '
                         f'images?')
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.caption_button.setEnabled(False)
        caption_thread = CaptionThread(self, self.image_list_model,
                                       selected_image_indices)
        caption_thread.text_outputted.connect(self.update_text_edit)
        caption_thread.clear_text_edit_requested.connect(self.text_edit.clear)
        caption_thread.caption_generated.connect(self.caption_generated)
        caption_thread.finished.connect(restore_stdout_and_stderr)
        caption_thread.finished.connect(
            lambda: self.caption_button.setEnabled(True))
        caption_thread.start()
