from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QDialog, QFileDialog, QGridLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QVBoxLayout)

from utils.big_widgets import BigCheckBox
from utils.settings import get_settings


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.settings = get_settings()
        self.setWindowTitle('Settings')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel('Font size (pt)'), 0, 0, Qt.AlignRight)
        grid_layout.addWidget(QLabel('Image width in image list (px)'), 1, 0,
                              Qt.AlignRight)
        grid_layout.addWidget(QLabel('Tag separator'), 2, 0, Qt.AlignRight)
        grid_layout.addWidget(QLabel('Insert space after tag separator'), 3, 0,
                              Qt.AlignRight)
        grid_layout.addWidget(QLabel('Auto-captioning models directory'), 4, 0,
                              Qt.AlignRight)
        grid_layout.addWidget(self.get_font_size_spin_box(), 0, 1,
                              Qt.AlignLeft)
        grid_layout.addWidget(self.get_image_list_image_width_spin_box(), 1, 1,
                              Qt.AlignLeft)
        grid_layout.addWidget(self.get_tag_separator_line_edit(), 2, 1,
                              Qt.AlignLeft)
        grid_layout.addWidget(
            self.get_insert_space_after_tag_separator_check_box(), 3, 1,
            Qt.AlignLeft)
        self.models_directory_line_edit = self.get_models_directory_line_edit()
        grid_layout.addWidget(self.models_directory_line_edit, 4, 1,
                              Qt.AlignLeft)
        grid_layout.addWidget(self.get_models_directory_button(), 5, 1,
                              Qt.AlignLeft)
        layout.addLayout(grid_layout)
        # Prevent the grid layout from moving to the center when the warning
        # label is hidden.
        layout.addStretch()
        self.restart_warning = ('Restart the application to apply the new '
                                'settings.')
        self.warning_label = QLabel(self.restart_warning)
        self.warning_label.setAlignment(Qt.AlignCenter)
        self.warning_label.setStyleSheet('color: red;')
        layout.addWidget(self.warning_label)
        # Fix the size of the dialog to its size when the warning label is
        # shown.
        self.setFixedSize(self.sizeHint())
        self.warning_label.hide()

    @Slot()
    def show_restart_warning(self):
        self.warning_label.setText(self.restart_warning)
        self.warning_label.show()

    def get_font_size_spin_box(self) -> QSpinBox:
        font_size_spin_box = QSpinBox()
        font_size_spin_box.setRange(1, 99)
        font_size_spin_box.setValue(self.settings.value('font_size', type=int))
        font_size_spin_box.valueChanged.connect(
            lambda value: self.settings.setValue('font_size', value))
        font_size_spin_box.valueChanged.connect(self.show_restart_warning)
        return font_size_spin_box

    def get_image_list_image_width_spin_box(self) -> QSpinBox:
        image_list_image_width_spin_box = QSpinBox()
        # Images that are too small cause lag, so set a minimum width.
        image_list_image_width_spin_box.setRange(16, 9999)
        image_list_image_width_spin_box.setValue(
            self.settings.value('image_list_image_width', type=int))
        image_list_image_width_spin_box.valueChanged.connect(
            lambda value: self.settings.setValue('image_list_image_width',
                                                 value))
        image_list_image_width_spin_box.valueChanged.connect(
            self.show_restart_warning)
        return image_list_image_width_spin_box

    @Slot(str)
    def handle_tag_separator_change(self, tag_separator: str):
        if not tag_separator:
            self.warning_label.setText('The tag separator cannot be empty.')
            self.warning_label.show()
            return
        self.settings.setValue('tag_separator', tag_separator)
        self.show_restart_warning()

    def get_tag_separator_line_edit(self) -> QLineEdit:
        tag_separator_line_edit = QLineEdit()
        tag_separator_line_edit.setText(self.settings.value('tag_separator'))
        tag_separator_line_edit.setMaximumWidth(50)
        tag_separator_line_edit.textChanged.connect(
            self.handle_tag_separator_change)
        return tag_separator_line_edit

    def get_insert_space_after_tag_separator_check_box(self) -> BigCheckBox:
        insert_space_after_tag_separator_check_box = BigCheckBox()
        insert_space_after_tag_separator_check_box.setChecked(
            self.settings.value('insert_space_after_tag_separator', type=bool))
        insert_space_after_tag_separator_check_box.stateChanged.connect(
            lambda state: self.settings.setValue(
                'insert_space_after_tag_separator',
                state == Qt.CheckState.Checked.value))
        insert_space_after_tag_separator_check_box.stateChanged.connect(
            self.show_restart_warning)
        return insert_space_after_tag_separator_check_box

    def get_models_directory_line_edit(self) -> QLineEdit:
        models_directory_line_edit = QLineEdit()
        models_directory_line_edit.setMinimumWidth(300)
        models_directory_line_edit.setText(
            self.settings.value('models_directory_path', type=str))
        models_directory_line_edit.textChanged.connect(
            lambda text: self.settings.setValue('models_directory_path', text))
        models_directory_line_edit.textChanged.connect(
            self.show_restart_warning)
        return models_directory_line_edit

    @Slot()
    def set_models_directory_path(self):
        if self.settings.contains('models_directory_path'):
            initial_directory_path = self.settings.value(
                'models_directory_path')
        elif self.settings.contains('directory_path'):
            initial_directory_path = self.settings.value('directory_path')
        else:
            initial_directory_path = ''
        models_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption='Select directory containing auto-captioning '
                                 'models',
            dir=initial_directory_path)
        if models_directory_path:
            self.models_directory_line_edit.setText(models_directory_path)

    def get_models_directory_button(self) -> QPushButton:
        models_directory_button = QPushButton('Select Directory...')
        models_directory_button.setFixedWidth(
            models_directory_button.sizeHint().width() * 1.3)
        models_directory_button.clicked.connect(self.set_models_directory_path)
        return models_directory_button
