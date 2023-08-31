from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QDialog, QGridLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout)

from models.image_list_model import ImageListModel
from utils.utils import pluralize


class FindAndReplaceDialog(QDialog):
    def __init__(self, parent, image_list_model: ImageListModel):
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.setWindowTitle('Find and Replace')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        warning_label = QLabel(
            'This is for finding and replacing arbitrary text in captions. '
            'To rename all instances of a tag, use the All Tags pane instead.')
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)
        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel('Find text'), 0, 0, Qt.AlignRight)
        grid_layout.addWidget(QLabel('Replace with'), 1, 0, Qt.AlignRight)
        find_line_edit = QLineEdit()
        find_line_edit.textChanged.connect(self.display_match_count)
        grid_layout.addWidget(find_line_edit, 0, 1)
        replace_line_edit = QLineEdit()
        grid_layout.addWidget(replace_line_edit, 1, 1)
        layout.addLayout(grid_layout)
        self.replace_button = QPushButton('Replace')
        self.replace_button.clicked.connect(
            lambda: image_list_model.find_and_replace(
                find_line_edit.text(), replace_line_edit.text()))
        self.replace_button.clicked.connect(
            lambda: self.display_match_count(find_line_edit.text()))
        layout.addWidget(self.replace_button)

    @Slot(str)
    def display_match_count(self, text: str):
        if not text:
            self.replace_button.setText('Replace')
            return
        match_count = self.image_list_model.get_text_match_count(text)
        self.replace_button.setText(f'Replace {match_count} '
                                    f'{pluralize("instance", match_count)}')
