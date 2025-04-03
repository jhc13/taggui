from pathlib import Path

from PySide6.QtCore import QModelIndex, Signal

from auto_captioning.auto_captioning_model import AutoCaptioningModel
from auto_captioning.models_list import get_model_class
from models.image_list_model import ImageListModel
from utils.enums import CaptionPosition
from utils.image import Image
from utils.settings import get_tag_separator
from utils.ModelThread import ModelThread


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


class CaptioningThread(ModelThread):
    # The image index, the caption, and the tags with the caption added. The
    # third parameter must be declared as `list` instead of `list[str]` for it
    # to work.
    caption_generated = Signal(QModelIndex, str, list)

    def __init__(self, parent, image_list_model: ImageListModel,
                 selected_image_indices: list[QModelIndex],
                 caption_settings: dict, tag_separator: str,
                 models_directory_path: Path | None):
        super().__init__(parent, image_list_model, selected_image_indices)
        self.caption_settings = caption_settings
        self.tag_separator = tag_separator
        self.models_directory_path = models_directory_path
        self.model: AutoCaptioningModel | None = None

    def load_model(self):
        model_id = self.caption_settings['model_id']
        model_class = get_model_class(model_id)
        self.model = model_class(
            captioning_thread_=self, caption_settings=self.caption_settings)
        self.error_message = self.model.get_error_message()
        if self.error_message:
            self.is_error = True
            return
        self.model.load_processor_and_model()
        self.model.monkey_patch_after_loading()
        self.device = self.model.device
        self.text = {
            'Generating': self.model.get_generation_text(),
            'generating': 'captioning'
        }

    def get_model_inputs(self, image: Image):
        image_prompt =  self.model.get_image_prompt(image)
        crop = self.caption_settings['limit_to_crop']
        return image_prompt, self.model.get_model_inputs(image_prompt,
                                                         image,
                                                         crop)

    def generate_output(self, image_index, image: Image, image_prompt: str | None, model_inputs) -> str:
        caption_position = self.caption_settings['caption_position']
        caption, console_output_caption = self.model.generate_caption(
            model_inputs, image_prompt)
        tags = add_caption_to_tags(image.tags, caption, caption_position)
        self.caption_generated.emit(image_index, caption, tags)
        return console_output_caption
