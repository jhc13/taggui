from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QDialog, QFileDialog, QGridLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from utils.settings import DEFAULT_SETTINGS, get_settings
from utils.settings_widgets import (SettingsBigCheckBox, SettingsLineEdit,
                                    SettingsSpinBox)


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
        grid_layout.addWidget(QLabel('File types to show in image list'), 1, 0,
                              Qt.AlignRight)
        grid_layout.addWidget(QLabel('Image width in image list (px)'), 2, 0,
                              Qt.AlignRight)
        grid_layout.addWidget(QLabel('Tag separator'), 3, 0, Qt.AlignRight)
        grid_layout.addWidget(QLabel('Insert space after tag separator'), 4, 0,
                              Qt.AlignRight)
        grid_layout.addWidget(QLabel('Auto-captioning models directory'), 5, 0,
                              Qt.AlignRight)

        font_size_spin_box = SettingsSpinBox(
            key='font_size', default=DEFAULT_SETTINGS['font_size'],
            minimum=1, maximum=99)
        font_size_spin_box.valueChanged.connect(self.show_restart_warning)
        # Images that are too small cause lag, so set a minimum width.
        image_list_image_width_spin_box = SettingsSpinBox(
            key='image_list_image_width',
            default=DEFAULT_SETTINGS['image_list_image_width'],
            minimum=16, maximum=9999)
        image_list_image_width_spin_box.valueChanged.connect(
            self.show_restart_warning)
        tag_separator_line_edit = QLineEdit()
        tag_separator = self.settings.value(
            'tag_separator', defaultValue=DEFAULT_SETTINGS['tag_separator'],
            type=str)
        tag_separator_line_edit.setMaximumWidth(50)
        tag_separator_line_edit.setText(tag_separator)
        tag_separator_line_edit.textChanged.connect(
            self.handle_tag_separator_change)
        insert_space_after_tag_separator_check_box = SettingsBigCheckBox(
            key='insert_space_after_tag_separator',
            default=DEFAULT_SETTINGS['insert_space_after_tag_separator'])
        insert_space_after_tag_separator_check_box.stateChanged.connect(
            self.show_restart_warning)
        self.models_directory_line_edit = SettingsLineEdit(
            key='models_directory_path',
            default=DEFAULT_SETTINGS['models_directory_path'])
        self.models_directory_line_edit.setMinimumWidth(300)
        self.models_directory_line_edit.setClearButtonEnabled(True)
        self.models_directory_line_edit.textChanged.connect(
            self.show_restart_warning)
        models_directory_button = QPushButton('Select Directory...')
        models_directory_button.setFixedWidth(
            models_directory_button.sizeHint().width() * 1.3)
        models_directory_button.clicked.connect(self.set_models_directory_path)
        file_types_line_edit = SettingsLineEdit(
            key='image_list_file_formats',
            default=DEFAULT_SETTINGS['image_list_file_formats'])
        file_types_line_edit.setMinimumWidth(300)
        file_types_line_edit.textChanged.connect(self.show_restart_warning)

        grid_layout.addWidget(font_size_spin_box, 0, 1, Qt.AlignLeft)
        grid_layout.addWidget(file_types_line_edit, 1, 1, Qt.AlignLeft)
        grid_layout.addWidget(image_list_image_width_spin_box, 2, 1,
                              Qt.AlignLeft)
        grid_layout.addWidget(tag_separator_line_edit, 3, 1, Qt.AlignLeft)
        grid_layout.addWidget(insert_space_after_tag_separator_check_box, 4, 1,
                              Qt.AlignLeft)
        grid_layout.addWidget(self.models_directory_line_edit, 5, 1,
                              Qt.AlignLeft)
        grid_layout.addWidget(models_directory_button, 6, 1, Qt.AlignLeft)
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

    @Slot(str)
    def handle_tag_separator_change(self, tag_separator: str):
        if not tag_separator:
            self.warning_label.setText('The tag separator cannot be empty.')
            self.warning_label.show()
            return
        self.settings.setValue('tag_separator', tag_separator)
        self.show_restart_warning()

    @Slot()
    def set_models_directory_path(self):
        models_directory_path = self.settings.value(
            'models_directory_path',
            defaultValue=DEFAULT_SETTINGS['models_directory_path'], type=str)
        if models_directory_path:
            initial_directory_path = models_directory_path
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
