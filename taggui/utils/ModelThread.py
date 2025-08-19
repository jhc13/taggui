from abc import abstractmethod
from datetime import datetime
from time import perf_counter

import numpy as np
from PIL import UnidentifiedImageError
from transformers import BatchFeature
from PySide6.QtCore import QModelIndex, QThread, Qt, Signal

from utils.image import Image
from models.image_list_model import ImageListModel

def format_duration(seconds: float) -> str:
    seconds_per_minute = 60
    seconds_per_hour = 60 * seconds_per_minute
    seconds_per_day = 24 * seconds_per_hour
    if seconds < seconds_per_minute:
        return f'{seconds:.1f} seconds'
    if seconds < seconds_per_hour:
        minutes = seconds / seconds_per_minute
        return f'{minutes:.1f} minutes'
    if seconds < seconds_per_day:
        hours = seconds / seconds_per_hour
        return f'{hours:.1f} hours'
    days = seconds / seconds_per_day
    return f'{days:.1f} days'


class ModelThread(QThread):
    """Base class for all model running threads"""
    text_outputted = Signal(str)
    clear_console_text_edit_requested = Signal()
    progress_bar_update_requested = Signal(int)

    def __init__(self, parent, image_list_model: ImageListModel,
                 selected_image_indices: list[QModelIndex]):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.selected_image_indices = selected_image_indices
        self.is_error = False
        self.error_message = ''
        self.is_canceled = False
        self.device = 'default'
        self.text = {
            'Generating': 'Generating',
            'generating': 'generating'
        }

    def run_generating(self):
        self.load_model()
        if self.is_error:
            self.clear_console_text_edit_requested.emit()
            print(self.error_message)
            return
        if self.is_canceled:
            print(f'Canceled {self.text['generating']}.')
            return
        self.clear_console_text_edit_requested.emit()
        selected_image_count = len(self.selected_image_indices)
        are_multiple_images_selected = selected_image_count > 1
        generating_start_datetime = datetime.now()
        generating_message = self.get_generating_message(
            are_multiple_images_selected, generating_start_datetime)
        print(generating_message)
        for i, image_index in enumerate(self.selected_image_indices):
            start_time = perf_counter()
            if self.is_canceled:
                print(f'Canceled {self.text['generating']}.')
                return
            image: Image = self.image_list_model.data(image_index,
                                                      Qt.ItemDataRole.UserRole)
            try:
                image_prompt, model_inputs = self.get_model_inputs(image)
            except UnidentifiedImageError:
                print(f'Skipping {image.path.name} because its file format is '
                      'not supported or it is a corrupted image.')
                continue
            console_output_caption = self.generate_output(image_index, image,
                                                          image_prompt, model_inputs)
            if are_multiple_images_selected:
                self.progress_bar_update_requested.emit(i + 1)
            if i == 0 and not are_multiple_images_selected:
                self.clear_console_text_edit_requested.emit()
            print(f'{image.path.name} ({perf_counter() - start_time:.1f} s):\n'
                  f'{console_output_caption}')
        if are_multiple_images_selected:
            generating_end_datetime = datetime.now()
            total_generating_duration = ((generating_end_datetime
                                          - generating_start_datetime)
                                         .total_seconds())
            average_generating_duration = (total_generating_duration /
                                           selected_image_count)
            print(f'Finished {self.text['generating']} {selected_image_count} images in '
                  f'{format_duration(total_generating_duration)} '
                  f'({average_generating_duration:.1f} s/image) at '
                  f'{generating_end_datetime.strftime("%Y-%m-%d %H:%M:%S")}.')

    @abstractmethod
    def load_model(self):
        """Load the model for the generating task."""
        pass

    def get_generating_message(self, are_multiple_images_selected: bool,
                               generating_start_datetime: datetime) -> str:
        if are_multiple_images_selected:
            generating_start_datetime_string = (
                generating_start_datetime.strftime('%Y-%m-%d %H:%M:%S'))
            return (f'{self.text['Generating']}... (device: {self.device}, '
                    f'start time: {generating_start_datetime_string})')
        return f'{self.text['Generating']}... (device: {self.device})'

    @abstractmethod
    def get_model_inputs(self, image: Image) -> tuple[
        str | None, BatchFeature | dict | np.ndarray]:
        pass

    @abstractmethod
    def generate_output(self, image_index,
                        image: Image,
                        image_prompt: str | None,
                        model_inputs: BatchFeature | dict | np.ndarray) -> str:
        pass

    def run(self):
        try:
            self.run_generating()
        except Exception as exception:
            self.is_error = True
            # Show the error message in the console text edit.
            raise exception

    def write(self, text: str):
        self.text_outputted.emit(text)
