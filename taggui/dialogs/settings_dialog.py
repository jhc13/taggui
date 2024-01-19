from PySide6.QtCore import QSettings, Qt, Slot
from PySide6.QtWidgets import (QDialog, QGridLayout, QLabel, QLineEdit,
                               QSpinBox, QVBoxLayout)

from utils.big_widgets import BigCheckBox


class SettingsDialog(QDialog):
    def __init__(self, parent, settings: QSettings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle('Settings')
        self.restart_warning = 'Restart the application to apply new settings.'
        self.warning_label = QLabel(self.restart_warning)
        self.warning_label.setAlignment(Qt.AlignCenter)
        self.warning_label.setStyleSheet('color: red;')
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
        # Prevent the grid layout from moving to the center when the warning
        # label is hidden.
        layout.addStretch()
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
