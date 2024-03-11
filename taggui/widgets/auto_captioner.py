import sys
from pathlib import Path

from PySide6.QtCore import QModelIndex, QSettings, Qt, Signal, Slot
from PySide6.QtGui import QFontMetrics, QTextCursor
from PySide6.QtWidgets import (QAbstractScrollArea, QDockWidget, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QScrollArea, QVBoxLayout, QWidget)

from auto_captioning.captioning_thread import CaptioningThread
from auto_captioning.enums import CaptionPosition, Device
from auto_captioning.models import MODELS
from models.image_list_model import ImageListModel
from utils.big_widgets import BigCheckBox, TallPushButton
from utils.focused_scroll_widgets import (FocusedScrollComboBox,
                                          FocusedScrollDoubleSpinBox,
                                          FocusedScrollSpinBox)
from utils.settings import get_separator, get_settings
from utils.utils import get_confirmation_dialog_reply, pluralize
from widgets.image_list import ImageList


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
        captioning_thread = CaptioningThread(
            self, self.image_list_model, selected_image_indices,
            caption_settings, tag_separator, models_directory_path)
        captioning_thread.text_outputted.connect(self.update_console_text_edit)
        captioning_thread.clear_console_text_edit_requested.connect(
            self.console_text_edit.clear)
        captioning_thread.caption_generated.connect(self.caption_generated)
        captioning_thread.progress_bar_update_requested.connect(
            self.progress_bar.setValue)
        captioning_thread.finished.connect(restore_stdout_and_stderr)
        captioning_thread.finished.connect(
            lambda: self.caption_button.setEnabled(True))
        captioning_thread.finished.connect(self.progress_bar.hide)
        captioning_thread.start()
