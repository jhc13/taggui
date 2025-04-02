from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QDialog, QFileDialog, QGridLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from utils.settings import DEFAULT_SETTINGS, settings
from utils.settings_widgets import (SettingsBigCheckBox, SettingsLineEdit,
                                    SettingsSpinBox)


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel('Font size (pt)'), 0, 0,
                              Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('File types to show in image list'), 1, 0,
                              Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('Image width in image list (px)'), 2, 0,
                              Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('Tag separator (\\n for newline)'), 3, 0,
                              Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('Insert space after tag separator'), 4, 0,
                              Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('Show tag autocomplete suggestions'),
                              5, 0, Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('Auto-captioning models directory'), 6, 0,
                              Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('Auto-marking models directory'), 8, 0,
                              Qt.AlignmentFlag.AlignRight)

        font_size_spin_box = SettingsSpinBox(
            key='font_size',
            minimum=1, maximum=99)
        font_size_spin_box.valueChanged.connect(self.show_restart_warning)
        file_types_line_edit = SettingsLineEdit(
            key='image_list_file_formats')
        file_types_line_edit.setMinimumWidth(400)
        file_types_line_edit.textChanged.connect(self.show_restart_warning)
        # Images that are too small cause lag, so set a minimum width.
        image_list_image_width_spin_box = SettingsSpinBox(
            key='image_list_image_width',
            minimum=16, maximum=9999)
        image_list_image_width_spin_box.valueChanged.connect(
            self.show_restart_warning)
        self.insert_space_after_tag_separator_check_box = SettingsBigCheckBox(
            key='insert_space_after_tag_separator')
        self.insert_space_after_tag_separator_check_box.stateChanged.connect(
            self.show_restart_warning)
        tag_separator_line_edit = QLineEdit()
        tag_separator = settings.value(
            'tag_separator', defaultValue=DEFAULT_SETTINGS['tag_separator'],
            type=str)
        if tag_separator == '\n':
            tag_separator = r'\n'
            self.disable_insert_space_after_tag_separator_check_box()
        tag_separator_line_edit.setMaximumWidth(50)
        tag_separator_line_edit.setText(tag_separator)
        tag_separator_line_edit.textChanged.connect(
            self.handle_tag_separator_change)
        autocomplete_tags_check_box = SettingsBigCheckBox(
            key='autocomplete_tags')
        autocomplete_tags_check_box.stateChanged.connect(
            self.show_restart_warning)
        self.models_directory_line_edit = SettingsLineEdit(
            key='models_directory_path')
        self.models_directory_line_edit.setMinimumWidth(400)
        self.models_directory_line_edit.setClearButtonEnabled(True)
        self.models_directory_line_edit.textChanged.connect(
            self.show_restart_warning)
        models_directory_button = QPushButton('Select Directory...')
        models_directory_button.setFixedWidth(
            int(models_directory_button.sizeHint().width() * 1.3))
        models_directory_button.clicked.connect(self.set_models_directory_path)
        self.marking_models_directory_line_edit = SettingsLineEdit(
            key='marking_models_directory_path')
        self.marking_models_directory_line_edit.setMinimumWidth(400)
        self.marking_models_directory_line_edit.setClearButtonEnabled(True)
        marking_models_directory_button = QPushButton('Select Directory...')
        marking_models_directory_button.setFixedWidth(
            int(marking_models_directory_button.sizeHint().width() * 1.3))
        marking_models_directory_button.clicked.connect(
            self.set_marking_models_directory_path)

        grid_layout.addWidget(font_size_spin_box, 0, 1,
                              Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(file_types_line_edit, 1, 1,
                              Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(image_list_image_width_spin_box, 2, 1,
                              Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(tag_separator_line_edit, 3, 1,
                              Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(self.insert_space_after_tag_separator_check_box,
                              4, 1, Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(autocomplete_tags_check_box, 5, 1,
                              Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(self.models_directory_line_edit, 6, 1,
                              Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(models_directory_button, 7, 1,
                              Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(self.marking_models_directory_line_edit, 8, 1,
                              Qt.AlignmentFlag.AlignLeft)
        grid_layout.addWidget(marking_models_directory_button, 9, 1,
                              Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(grid_layout)

        # Prevent the grid layout from moving to the center when the warning
        # label is hidden.
        layout.addStretch()
        self.restart_warning = ('Restart the application to apply the new '
                                'settings.')
        self.warning_label = QLabel(self.restart_warning)
        self.warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

    def disable_insert_space_after_tag_separator_check_box(self):
        self.insert_space_after_tag_separator_check_box.setEnabled(False)
        self.insert_space_after_tag_separator_check_box.setChecked(False)

    @Slot(str)
    def handle_tag_separator_change(self, tag_separator: str):
        if not tag_separator:
            self.warning_label.setText('The tag separator cannot be empty.')
            self.warning_label.show()
            return
        if tag_separator == r'\n':
            tag_separator = '\n'
            self.disable_insert_space_after_tag_separator_check_box()
        else:
            self.insert_space_after_tag_separator_check_box.setEnabled(True)
        settings.setValue('tag_separator', tag_separator)
        self.show_restart_warning()

    @Slot()
    def set_models_directory_path(self):
        models_directory_path = settings.value(
            'models_directory_path',
            defaultValue=DEFAULT_SETTINGS['models_directory_path'], type=str)
        if models_directory_path:
            initial_directory_path = models_directory_path
        elif settings.contains('directory_path'):
            initial_directory_path = settings.value('directory_path', type=str)
        else:
            initial_directory_path = ''
        models_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption='Select directory containing auto-captioning '
                                 'models',
            dir=initial_directory_path)
        if models_directory_path:
            self.models_directory_line_edit.setText(models_directory_path)

    @Slot()
    def set_marking_models_directory_path(self):
        marking_models_directory_path = settings.value(
            'marking_models_directory_path',
            defaultValue=DEFAULT_SETTINGS['marking_models_directory_path'], type=str)
        if marking_models_directory_path:
            initial_directory_path = marking_models_directory_path
        elif settings.contains('directory_path'):
            initial_directory_path = settings.value('directory_path', type=str)
        else:
            initial_directory_path = ''
        marking_models_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption='Select directory containing auto-marking '
                                 'models (YOLO models)',
            dir=initial_directory_path)
        if marking_models_directory_path:
            self.marking_models_directory_line_edit.setText(marking_models_directory_path)
