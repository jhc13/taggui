from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QGridLayout, QLabel,
                               QLineEdit, QSpinBox)

default_settings = {
    'font_size': 18,
    'separator': ',',
    'insert_space_after_separator': True,
    'image_list_image_width': 200
}


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')

        font_size_spin_box = QSpinBox()
        font_size_spin_box.setRange(1, 99)
        font_size_spin_box.setValue(int(settings.value('font_size')))
        font_size_spin_box.valueChanged.connect(
            lambda value: settings.setValue('font_size', value))

        separator_line_edit = QLineEdit()
        separator_line_edit.setText(settings.value('separator'))
        separator_line_edit.setMaximumWidth(50)
        separator_line_edit.textChanged.connect(
            lambda text: settings.setValue('separator', text))

        insert_space_after_separator_check_box = QCheckBox()
        # The value is initially a Boolean, but later becomes a string.
        insert_space_after_separator_check_box.setChecked(
            settings.value('insert_space_after_separator')
            in (True, 'true'))
        insert_space_after_separator_check_box.stateChanged.connect(
            lambda state: settings.setValue(
                'insert_space_after_separator',
                state == Qt.CheckState.Checked.value))

        image_list_image_width_spin_box = QSpinBox()
        image_list_image_width_spin_box.setRange(1, 9999)
        image_list_image_width_spin_box.setValue(
            int(settings.value('image_list_image_width')))
        image_list_image_width_spin_box.valueChanged.connect(
            lambda value: settings.setValue('image_list_image_width', value))

        restart_label = QLabel('The application must be restarted for some '
                               'changes to take effect.')
        restart_label.setWordWrap(True)
        restart_label.setAlignment(Qt.AlignCenter)
        restart_label.setStyleSheet('color: #f54242')

        layout = QGridLayout(self)
        layout.addWidget(QLabel('Font size'), 0, 0, Qt.AlignRight)
        layout.addWidget(font_size_spin_box, 0, 1, Qt.AlignLeft)
        layout.addWidget(QLabel('Separator'), 1, 0, Qt.AlignRight)
        layout.addWidget(separator_line_edit, 1, 1, Qt.AlignLeft)
        layout.addWidget(QLabel('Insert space after separator'), 2, 0,
                         Qt.AlignRight)
        layout.addWidget(insert_space_after_separator_check_box, 2, 1,
                         Qt.AlignLeft)
        layout.addWidget(QLabel('Image list image width (px)'), 3, 0,
                         Qt.AlignRight)
        layout.addWidget(image_list_image_width_spin_box, 3, 1, Qt.AlignLeft)
        # Make an empty row.
        layout.addWidget(QLabel(''), 4, 0)
        layout.addWidget(restart_label, 5, 0, 1, 2)
        self.adjustSize()


def set_default_settings(settings):
    for key, value in default_settings.items():
        if not settings.contains(key):
            settings.setValue(key, value)


def get_settings() -> QSettings:
    settings = QSettings('captioning-tool', 'captioning-tool')
    set_default_settings(settings)
    return settings
