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
        is_remote = hasattr(model_class, "api_urls")
        if is_remote:
            # Create multiple instances for remote model
            temp_model = model_class(
                captioning_thread_=self,
                caption_settings=self.caption_settings
            )
            num_instances = len(temp_model.api_urls) if temp_model.api_urls else 1
            models = [model_class(
                captioning_thread_=self,
                caption_settings=self.caption_settings
            ) for _ in range(num_instances)]
            for index, model in enumerate(models):
                model.setapiIndex(index)
        else:
            # Single instance for local models
            models = [model_class(
                captioning_thread_=self,
                caption_settings=self.caption_settings
            )]
        #model: AutoCaptioningModel = model_class(captioning_thread_=self, caption_settings=self.caption_settings)
        self.error_message = model.get_error_message()
        if self.error_message:
            self.is_error = True
            return
        for model in models:
            model.load_processor_and_model()
            model.monkey_patch_after_loading()
        if self.is_canceled:
            print('Canceled captioning.')
            return
        self.clear_console_text_edit_requested.emit()
        selected_image_count = len(self.selected_image_indices)
        are_multiple_images_selected = selected_image_count > 1
        captioning_start_datetime = datetime.now()
        captioning_message = model.get_captioning_message(
            are_multiple_images_selected, captioning_start_datetime)
        print(captioning_message)
        caption_position = self.caption_settings['caption_position']
        def realcaptionthread(i, image_index):
            start_time = perf_counter()
            if self.is_canceled:
                print('Canceled captioning.')
                return
            model = models[i % len(models)] if is_remote else models[0]
            image: Image = self.image_list_model.data(image_index,
                                                    Qt.ItemDataRole.UserRole)
            image_prompt = model.get_image_prompt(image)
            try:
                model_inputs = model.get_model_inputs(image_prompt, image)
            except UnidentifiedImageError:
                print(f'Skipping {image.path.name} because its file format is '
                    'not supported or it is a corrupted image.')
                return
            caption, console_output_caption = model.generate_caption(
                model_inputs, image_prompt)
            tags = add_caption_to_tags(image.tags, caption, caption_position)
            self.caption_generated.emit(image_index, caption, tags)
            if are_multiple_images_selected:
                self.progress_bar_update_requested.emit(i + 1)
            if i == 0 and not are_multiple_images_selected:
                self.clear_console_text_edit_requested.emit()
            if console_output_caption is None:
                console_output_caption = caption
            print(f'{image.path.name} ({perf_counter() - start_time:.1f} s):\n'
                f'{console_output_caption}')

        for i1, image_index1 in enumerate(self.selected_image_indices):
            realcaptionthread(i1, image_index1)

        if are_multiple_images_selected:
            captioning_end_datetime = datetime.now()
            total_captioning_duration = ((captioning_end_datetime
                                          - captioning_start_datetime)
                                         .total_seconds())
            average_captioning_duration = (total_captioning_duration /
                                           selected_image_count)
            print(f'Finished captioning {selected_image_count} images in '
                  f'{format_duration(total_captioning_duration)} '
                  f'({average_captioning_duration:.1f} s/image) at '
                  f'{captioning_end_datetime.strftime("%Y-%m-%d %H:%M:%S")}.')

    def run(self):
        try:
            self.run_captioning()
        except Exception as exception:
            self.is_error = True
            # Show the error message in the console text edit.
            raise exception

    def write(self, text: str):
        self.text_outputted.emit(text)
