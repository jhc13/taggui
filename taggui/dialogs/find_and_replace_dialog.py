from PySide6.QtCore import QSettings, Qt, Slot
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from models.image_list_model import ImageListModel
from utils.big_widgets import BigCheckBox
from utils.settings import get_settings
from utils.utils import pluralize


class FindAndReplaceDialog(QDialog):
    def __init__(self, parent, image_list_model: ImageListModel):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.settings = get_settings()
        self.setWindowTitle('Find and Replace')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        description_label = QLabel(
            'This is for finding and replacing arbitrary text in captions. '
            'You can also use the All Tags pane to rename or delete all '
            'instances of a tag.')
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel('Find text'), 0, 0, Qt.AlignRight)
        grid_layout.addWidget(QLabel('Replace with'), 1, 0, Qt.AlignRight)
        self.find_line_edit = QLineEdit()
        self.find_line_edit.textChanged.connect(self.display_match_count)
        grid_layout.addWidget(self.find_line_edit, 0, 1)
        self.replace_line_edit = QLineEdit()
        grid_layout.addWidget(self.replace_line_edit, 1, 1)
        layout.addLayout(grid_layout)
        horizontal_layout = QHBoxLayout()
        self.only_in_filtered_images_check_box = (
            self.get_check_box(self.settings, text='In filtered images only',
                               settings_key='replace_in_filtered_images_only'))
        horizontal_layout.addWidget(self.only_in_filtered_images_check_box)
        self.whole_tags_only_check_box = (
            self.get_check_box(self.settings, text='Whole tags only',
                               settings_key='replace_whole_tags_only'))
        horizontal_layout.addWidget(self.whole_tags_only_check_box)
        layout.addLayout(horizontal_layout)
        self.replace_button = QPushButton('Replace')
        self.replace_button.clicked.connect(self.replace)
        self.replace_button.clicked.connect(self.display_match_count)
        layout.addWidget(self.replace_button)

    @Slot()
    def display_match_count(self):
        text = self.find_line_edit.text()
        if not text:
            self.replace_button.setText('Replace')
            return
        in_filtered_images_only = (self.only_in_filtered_images_check_box
                                   .isChecked())
        whole_tags_only = self.whole_tags_only_check_box.isChecked()
        match_count = self.image_list_model.get_text_match_count(
            text, in_filtered_images_only, whole_tags_only)
        self.replace_button.setText(f'Replace {match_count} '
                                    f'{pluralize("instance", match_count)}')

    def get_check_box(self, settings: QSettings, text: str,
                      settings_key: str) -> BigCheckBox:
        check_box = BigCheckBox()
        check_box.setText(text)
        check_box.setChecked(settings.value(settings_key, type=bool))
        check_box.stateChanged.connect(
            lambda state: settings.setValue(
                settings_key, state == Qt.CheckState.Checked.value))
        check_box.stateChanged.connect(self.display_match_count)
        return check_box

    @Slot()
    def replace(self):
        in_filtered_images_only = (self.only_in_filtered_images_check_box
                                   .isChecked())
        if self.whole_tags_only_check_box.isChecked():
            replace_text = self.replace_line_edit.text()
            if replace_text:
                self.image_list_model.rename_tag(self.find_line_edit.text(),
                                                 replace_text,
                                                 in_filtered_images_only)
            else:
                self.image_list_model.delete_tag(self.find_line_edit.text(),
                                                 in_filtered_images_only)
        else:
            self.image_list_model.find_and_replace(
                self.find_line_edit.text(), self.replace_line_edit.text(),
                in_filtered_images_only)
