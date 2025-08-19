import sys
from pathlib import Path

from PySide6.QtCore import Signal, QModelIndex, Qt, Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QDockWidget, QProgressBar, QPlainTextEdit,
                               QWidget, QVBoxLayout, QScrollArea,
                               QAbstractScrollArea, QFrame, QFormLayout,
                               QMessageBox, QTableWidget, QHeaderView,
                               QTableWidgetItem, QComboBox)

from utils.icons import create_add_box_icon
from models.image_list_model import ImageListModel
from utils.utils import pluralize
from utils.big_widgets import TallPushButton
from utils.settings import settings, DEFAULT_SETTINGS
from utils.settings_widgets import (FocusedScrollSettingsComboBox,
                                    FocusedScrollSettingsDoubleSpinBox,
                                    FocusedScrollSettingsSpinBox)
from widgets.auto_captioner import (set_text_edit_height,
                                    restore_stdout_and_stderr, HorizontalLine)
from widgets.image_list import ImageList
from auto_marking.marking_thread import MarkingThread
from dialogs.caption_multiple_images_dialog import CaptionMultipleImagesDialog


class MarkingSettingsForm(QVBoxLayout):
    model_selected = Signal(bool)

    def __init__(self):
        super().__init__()
        basic_settings_form = QFormLayout()
        basic_settings_form.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapAllRows)
        basic_settings_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.model_combo_box = FocusedScrollSettingsComboBox(key='marking_model_id')
        self.model_combo_box.setPlaceholderText('Set marking model directory in "Settings..."')
        self.model_combo_box.activated.connect(lambda _: self.model_selected.emit(True))
        self.get_local_model_paths()
        settings.change.connect(lambda key, value: self.get_local_model_paths()
            if key == 'marking_models_directory_path' else 0)
        basic_settings_form.addRow('Model', self.model_combo_box)

        self.class_table = QTableWidget(0, 2)
        self.class_table.setHorizontalHeaderLabels(['Class', 'Marking'])
        self.class_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.class_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        basic_settings_form.addRow('Classes', self.class_table)

        self.toggle_advanced_settings_form_button = TallPushButton(
            'Show Advanced Settings')

        self.advanced_settings_form_container = QWidget()
        advanced_settings_form = QFormLayout(
            self.advanced_settings_form_container)
        advanced_settings_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        advanced_settings_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # Sets the minimum confidence threshold for detections.
        # Objects detected with confidence below this threshold will be
        # disregarded. Adjusting this value can help reduce false positives.
        self.confidence_spin_box = FocusedScrollSettingsDoubleSpinBox(
            key='confidence', default=0.25, minimum=0.01, maximum=1.0)
        self.confidence_spin_box.setSingleStep(0.01)
        advanced_settings_form.addRow('Confidence',
                                      self.confidence_spin_box)
        # Intersection Over Union (IoU) threshold for Non-Maximum Suppression
        # (NMS). Lower values result in fewer detections by eliminating
        # overlapping boxes, useful for reducing duplicates.
        self.iou_spin_box = FocusedScrollSettingsDoubleSpinBox(
            key='iou', default=0.7, minimum=0.01, maximum=1.0)
        self.iou_spin_box.setSingleStep(0.01)
        advanced_settings_form.addRow('Intersection Over Union (IoU)',
                                      self.iou_spin_box)
        # Maximum number of detections allowed per image.
        # Limits the total number of objects the model can detect in a single
        # inference, preventing excessive outputs in dense scenes.
        self.max_det_spin_box = FocusedScrollSettingsSpinBox(
            key='max_det', default=300, minimum=1, maximum=500)
        advanced_settings_form.addRow('Maximum number of detections', self.max_det_spin_box)
        self.advanced_settings_form_container.hide()

        self.addLayout(basic_settings_form)
        self.horizontal_line = HorizontalLine()
        self.addWidget(self.horizontal_line)
        self.addWidget(self.toggle_advanced_settings_form_button)
        self.addWidget(self.advanced_settings_form_container)

        self.toggle_advanced_settings_form_button.clicked.connect(
            self.toggle_advanced_settings_form)

    def get_local_model_paths(self):
        models_directory_path = settings.value(
            'marking_models_directory_path',
            defaultValue=DEFAULT_SETTINGS['marking_models_directory_path'],
            type=str)
        if not models_directory_path:
            return
        models_directory_path = Path(models_directory_path)
        print(f'Loading local auto-marking model paths under '
              f'{models_directory_path}...')
        config_paths = set(models_directory_path.glob('**/*.pt'))
        self.model_selected.emit(False)
        self.model_combo_box.clear()
        if len(config_paths) == 0:
            self.model_combo_box.setPlaceholderText(
                'Set marking model directory in "Settings..."')
        else:
            self.model_combo_box.setPlaceholderText('Select marking model')
            for path in config_paths:
                self.model_combo_box.addItem(
                    str(path.relative_to(models_directory_path)), userData=path)

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

    def get_marking_settings(self) -> dict:
        return {
            'model_path': self.model_combo_box.currentData(),
            'conf': self.confidence_spin_box.value(),
            'iou': self.iou_spin_box.value(),
            'max_det': self.max_det_spin_box.value(),
            'classes': []
        }

class AutoMarkings(QDockWidget):
    marking_generated = Signal(QModelIndex, list)

    def __init__(self, image_list_model: ImageListModel,
                 image_list: ImageList, parent):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.image_list = image_list
        self.is_marking = False
        self.marking_thread = None
        self.show_alert_when_finished = False
        # Whether the last block of text in the console text edit should be
        # replaced with the next block of text that is outputted.
        self.replace_last_console_text_edit_block = False
        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('auto_markings')
        self.setWindowTitle('Auto-Markings')
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                             Qt.DockWidgetArea.RightDockWidgetArea)

        self.start_cancel_button = TallPushButton('Start Auto-Marking')
        self.start_cancel_button.setEnabled(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat('%v / %m images marked (%p%)')
        self.progress_bar.hide()
        self.console_text_edit = QPlainTextEdit()
        set_text_edit_height(self.console_text_edit, 4)
        self.console_text_edit.setReadOnly(True)
        self.console_text_edit.hide()
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.start_cancel_button)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.console_text_edit)
        self.marking_settings_form = MarkingSettingsForm()
        layout.addLayout(self.marking_settings_form)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(container)
        self.setWidget(scroll_area)

        self.start_cancel_button.clicked.connect(
            self.start_or_cancel_marking)
        self.marking_settings_form.model_selected.connect(lambda _: self.prepare_generation())
        self.marking_settings_form.model_selected.connect(self.start_cancel_button.setEnabled)

    @Slot()
    def start_or_cancel_marking(self):
        if self.is_marking:
            # Cancel marking.
            self.marking_thread.is_canceled = True
            self.start_cancel_button.setEnabled(False)
            self.start_cancel_button.setText('Canceling Auto-Marking...')
        else:
            # Start marking.
            self.generate_markings()

    def set_is_marking(self, is_marking: bool):
        self.is_marking = is_marking
        button_text = ('Cancel Auto-Marking' if is_marking
                       else 'Start Auto-Marking')
        self.start_cancel_button.setText(button_text)

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
            self.console_text_edit.moveCursor(QTextCursor.MoveOperation.End)
            self.console_text_edit.moveCursor(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor)
            self.console_text_edit.textCursor().removeSelectedText()
            # Delete the newline.
            self.console_text_edit.textCursor().deletePreviousChar()
        self.console_text_edit.appendPlainText(text)

    @Slot()
    def show_alert(self):
        if self.marking_thread.is_canceled:
            return
        if self.marking_thread.is_error:
            icon = QMessageBox.Icon.Critical
            text = ('An error occurred during marking. See the '
                    'Auto-Marking console for more information.')
        else:
            icon = QMessageBox.Icon.Information
            text = 'Marking has finished.'
        alert = QMessageBox()
        alert.setIcon(icon)
        alert.setText(text)
        alert.exec()

    def prepare_generation(self):
        selected_image_indices = self.image_list.get_selected_image_indices()
        marking_settings = self.marking_settings_form.get_marking_settings()
        self.marking_thread = MarkingThread(
            self, self.image_list_model, selected_image_indices,
            marking_settings)
        self.marking_thread.text_outputted.connect(
            self.update_console_text_edit)
        self.marking_thread.clear_console_text_edit_requested.connect(
            self.console_text_edit.clear)
        self.marking_thread.marking_generated.connect(
            self.marking_generated)
        self.marking_thread.progress_bar_update_requested.connect(
            self.progress_bar.setValue)
        self.marking_thread.finished.connect(
            lambda: self.set_is_marking(False))
        self.marking_thread.finished.connect(restore_stdout_and_stderr)
        self.marking_thread.finished.connect(self.progress_bar.hide)
        self.marking_thread.finished.connect(
            lambda: self.start_cancel_button.setEnabled(True))
        if self.show_alert_when_finished:
            self.marking_thread.finished.connect(self.show_alert)
        self.marking_thread.preload_model()
        self.marking_settings_form.class_table.setRowCount(
            len(self.marking_thread.model.names))
        for row, (class_id, class_name) in enumerate(
                self.marking_thread.model.names.items()):
            self.marking_settings_form.class_table.setItem(
                row, 0, QTableWidgetItem(class_name))
            combo = QComboBox()
            combo.addItem('ignore')
            combo.addItem(create_add_box_icon(Qt.gray), 'hint')
            combo.addItem(create_add_box_icon(Qt.red), 'exclude')
            combo.addItem(create_add_box_icon(Qt.green), 'include')
            self.marking_settings_form.class_table.setCellWidget(row, 1, combo)
        # NOTE: As this thread has no place to display the output, we keep
        # `stdout` and `stderr`.
        # Redirect `stdout` and `stderr` so that the outputs are displayed in
        # the console text edit.
        ###sys.stdout = self.marking_thread
        ###sys.stderr = self.marking_thread

    @Slot()
    def generate_markings(self):
        selected_image_indices = self.image_list.get_selected_image_indices()
        if self.marking_thread is None:
            self.prepare_generation()
        self.marking_thread.selected_image_indices = selected_image_indices
        self.marking_thread.marking_settings = self.marking_settings_form.get_marking_settings()
        classes = {}
        for row, (class_id, class_name) in enumerate(
                self.marking_thread.model.names.items()):
            combo = self.marking_settings_form.class_table.cellWidget(row, 1).currentText()
            if combo != 'ignore':
                classes[class_id] = (class_name, combo)
        self.marking_thread.marking_settings['classes'] = classes
        selected_image_count = len(selected_image_indices)
        self.image_list_model.add_to_undo_stack(
            action_name=f'Generate '
                        f'{pluralize('Marking', selected_image_count)}',
            should_ask_for_confirmation=selected_image_count > 1)
        if selected_image_count > 1:
            confirmation_dialog = CaptionMultipleImagesDialog(
                selected_image_count, 'Mark', 'Markings')
            reply = confirmation_dialog.exec()
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.show_alert_when_finished = (confirmation_dialog
                                             .show_alert_check_box.isChecked())
        self.set_is_marking(True)
        if selected_image_count > 1:
            self.progress_bar.setRange(0, selected_image_count)
            self.progress_bar.setValue(0)
            self.progress_bar.show()
        self.marking_thread.start()
