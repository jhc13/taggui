import re

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout

from models.image_list_model import ImageListModel
from models.tag_counter_model import TagCounterModel
from utils.settings_widgets import SettingsBigCheckBox, SettingsLineEdit
from widgets.auto_captioner import HorizontalLine


class BatchReorderTagsDialog(QDialog):
    def __init__(self, parent, image_list_model: ImageListModel,
                 tag_counter_model: TagCounterModel):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.setWindowTitle('Batch Reorder Tags')
        layout = QVBoxLayout(self)
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(20, 20, 20, 20)
        top_layout.setSpacing(20)
        do_not_reorder_first_tag_check_box = SettingsBigCheckBox(
            key='do_not_reorder_first_tag', default=True)
        do_not_reorder_first_tag_check_box.setText('Do not reorder first tag')
        top_layout.addWidget(do_not_reorder_first_tag_check_box)
        top_buttons_layout = QVBoxLayout()
        top_buttons_layout.setSpacing(20)
        sort_alphabetically_button = QPushButton('Sort Tags Alphabetically')
        sort_alphabetically_button.clicked.connect(
            lambda: self.image_list_model.sort_tags_alphabetically(
                do_not_reorder_first_tag_check_box.isChecked()))
        top_buttons_layout.addWidget(sort_alphabetically_button)
        sort_by_frequency_button = QPushButton('Sort Tags by Frequency')
        sort_by_frequency_button.clicked.connect(
            lambda: self.image_list_model.sort_tags_by_frequency(
                tag_counter_model.tag_counter,
                do_not_reorder_first_tag_check_box.isChecked()))
        top_buttons_layout.addWidget(sort_by_frequency_button)
        reverse_button = QPushButton('Reverse Order of Tags')
        reverse_button.clicked.connect(
            lambda: self.image_list_model.reverse_tags_order(
                do_not_reorder_first_tag_check_box.isChecked()))
        top_buttons_layout.addWidget(reverse_button)
        shuffle_button = QPushButton('Shuffle Tags Randomly')
        shuffle_button.clicked.connect(
            lambda: self.image_list_model.shuffle_tags(
                do_not_reorder_first_tag_check_box.isChecked()))
        top_buttons_layout.addWidget(shuffle_button)
        top_layout.addLayout(top_buttons_layout)
        horizontal_line = HorizontalLine()
        middle_layout = QHBoxLayout()
        middle_layout.setContentsMargins(20, 20, 20, 20)
        middle_layout.setSpacing(20)
        separate_newline_check_box = SettingsBigCheckBox(
            key='reorder_tags_separate_newline', default=True)
        separate_newline_check_box.setText('Separate by #newline')
        middle_layout.addWidget(separate_newline_check_box)
        sort_sentences_button = QPushButton('Sort Sentence Tags to Bottom')
        sort_sentences_button.clicked.connect(
            lambda: self.image_list_model.sort_sentences_down(
                separate_newline_check_box.isChecked()))
        middle_layout.addWidget(sort_sentences_button)
        horizontal_line2 = HorizontalLine()
        bottom_layout = QVBoxLayout()
        bottom_layout.setContentsMargins(20, 20, 20, 20)
        bottom_layout.setSpacing(20)
        self.move_tags_line_edit = SettingsLineEdit(key='move_to_front_tags')
        self.move_tags_line_edit.setPlaceholderText('Tags to move to front '
                                                    '(comma-separated)')
        self.move_tags_line_edit.setClearButtonEnabled(True)
        self.move_tags_line_edit.textChanged.connect(
            lambda: self.move_tags_button.setEnabled(
                bool(self.move_tags_line_edit.text())))
        self.move_tags_button = QPushButton('Move Tags to Front')
        self.move_tags_button.setEnabled(False)
        self.move_tags_button.clicked.connect(self.move_tags_to_front)
        bottom_layout.addWidget(self.move_tags_line_edit)
        bottom_layout.addWidget(self.move_tags_button)
        layout.addLayout(top_layout)
        layout.addWidget(horizontal_line)
        layout.addLayout(middle_layout)
        layout.addWidget(horizontal_line2)
        layout.addLayout(bottom_layout)

        self.move_tags_line_edit.textChanged.emit(
            self.move_tags_line_edit.text())

    @Slot()
    def move_tags_to_front(self):
        tags = re.split(r'(?<!\\),', self.move_tags_line_edit.text())
        tags = [tag.strip().replace(r'\,', ',') for tag in tags]
        self.image_list_model.move_tags_to_front(tags)
