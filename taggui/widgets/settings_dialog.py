from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QDialog, QGridLayout, QLabel, QLineEdit,
                               QSpinBox, QVBoxLayout)

from utils.big_widgets import BigCheckBox


class SettingsDialog(QDialog):
    def __init__(self, parent, settings: QSettings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle('Settings')
        self.restart_label = QLabel(
            'Restart the application to apply new settings.')
        self.restart_label.setStyleSheet('color: red;')
        layout = QVBoxLayout(self)
        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel('Font size (pt)'), 0, 0, Qt.AlignRight)
        grid_layout.addWidget(QLabel('Image width in image list (px)'), 1, 0,
                              Qt.AlignRight)
        grid_layout.addWidget(QLabel('Tag separator'), 2, 0, Qt.AlignRight)
        grid_layout.addWidget(QLabel('Insert space after tag separator'), 3, 0,
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
        layout.addLayout(grid_layout)
        # Prevent the grid layout from moving to the center when the restart
        # label is hidden.
        layout.addStretch()
        layout.addWidget(self.restart_label)
        # Fix the size of the dialog to its size when the restart label is
        # shown.
        self.setFixedSize(self.sizeHint())
        self.restart_label.hide()

    def get_font_size_spin_box(self) -> QSpinBox:
        font_size_spin_box = QSpinBox()
        font_size_spin_box.setRange(1, 99)
        font_size_spin_box.setValue(self.settings.value('font_size', type=int))
        font_size_spin_box.valueChanged.connect(
            lambda value: self.settings.setValue('font_size', value))
        font_size_spin_box.valueChanged.connect(self.restart_label.show)
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
            self.restart_label.show)
        return image_list_image_width_spin_box

    def get_tag_separator_line_edit(self) -> QLineEdit:
        tag_separator_line_edit = QLineEdit()
        tag_separator_line_edit.setText(self.settings.value('tag_separator'))
        tag_separator_line_edit.setMaximumWidth(50)
        tag_separator_line_edit.textChanged.connect(
            lambda text: self.settings.setValue('tag_separator', text))
        tag_separator_line_edit.textChanged.connect(self.restart_label.show)
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
            self.restart_label.show)
        return insert_space_after_tag_separator_check_box
