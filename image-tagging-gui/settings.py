from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QGridLayout, QLabel,
                               QLineEdit, QSpinBox)

default_settings = {
    'font_size': 18,
    'image_list_image_width': 200,
    'tag_separator': ',',
    'insert_space_after_tag_separator': True,
}


class SettingsDialog(QDialog):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle('Settings')
        layout = QGridLayout(self)
        layout.addWidget(QLabel('Font size'), 0, 0, Qt.AlignRight)
        layout.addWidget(QLabel('Image width in image list (px)'), 1, 0,
                         Qt.AlignRight)
        layout.addWidget(QLabel('Tag separator'), 2, 0, Qt.AlignRight)
        layout.addWidget(QLabel('Insert space after tag separator'), 3, 0,
                         Qt.AlignRight)
        layout.addWidget(self.get_font_size_spin_box(), 0, 1, Qt.AlignLeft)
        layout.addWidget(self.get_image_list_image_width_spin_box(), 1, 1,
                         Qt.AlignLeft)
        layout.addWidget(self.get_tag_separator_line_edit(), 2, 1,
                         Qt.AlignLeft)
        layout.addWidget(self.get_insert_space_after_tag_separator_check_box(),
                         3, 1, Qt.AlignLeft)
        self.adjustSize()

    def get_font_size_spin_box(self) -> QSpinBox:
        font_size_spin_box = QSpinBox()
        font_size_spin_box.setRange(1, 99)
        font_size_spin_box.setValue(int(self.settings.value('font_size')))
        font_size_spin_box.valueChanged.connect(
            lambda value: self.settings.setValue('font_size', value))
        font_size_spin_box.valueChanged.connect(self.parent().set_font_size)
        return font_size_spin_box

    def get_image_list_image_width_spin_box(self) -> QSpinBox:
        image_list_image_width_spin_box = QSpinBox()
        # Images that are too small cause lag, so set a minimum width.
        image_list_image_width_spin_box.setRange(16, 9999)
        image_list_image_width_spin_box.setValue(
            int(self.settings.value('image_list_image_width')))
        image_list_image_width_spin_box.valueChanged.connect(
            lambda value: self.settings.setValue('image_list_image_width',
                                                 value))
        image_list_image_width_spin_box.valueChanged.connect(
            self.parent().set_image_list_image_width)
        return image_list_image_width_spin_box

    def get_tag_separator_line_edit(self) -> QLineEdit:
        tag_separator_line_edit = QLineEdit()
        tag_separator_line_edit.setText(self.settings.value('tag_separator'))
        tag_separator_line_edit.setMaximumWidth(50)
        tag_separator_line_edit.textChanged.connect(
            lambda text: self.settings.setValue('tag_separator', text))
        return tag_separator_line_edit

    def get_insert_space_after_tag_separator_check_box(self) -> QCheckBox:
        insert_space_after_tag_separator_check_box = QCheckBox()
        # The value is initially a Boolean, but later becomes a string.
        insert_space_after_tag_separator_check_box.setChecked(
            self.settings.value('insert_space_after_tag_separator')
            in (True, 'true'))
        insert_space_after_tag_separator_check_box.stateChanged.connect(
            lambda state: self.settings.setValue(
                'insert_space_after_tag_separator',
                state == Qt.CheckState.Checked.value))
        return insert_space_after_tag_separator_check_box


def set_default_settings(settings):
    for key, value in default_settings.items():
        if not settings.contains(key):
            settings.setValue(key, value)


def get_settings() -> QSettings:
    settings = QSettings('image-tagging-gui', 'image-tagging-gui')
    set_default_settings(settings)
    return settings


def get_separator(settings) -> str:
    separator = settings.value('tag_separator')
    insert_space_after_separator = bool(
        settings.value('insert_space_after_tag_separator'))
    if insert_space_after_separator:
        separator += ' '
    return separator
