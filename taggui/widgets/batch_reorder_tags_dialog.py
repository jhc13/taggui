from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout

from models.image_list_model import ImageListModel
from models.tag_counter_model import TagCounterModel
from utils.big_widgets import BigCheckBox
from utils.settings import get_settings


class BatchReorderTagsDialog(QDialog):
    def __init__(self, parent, image_list_model: ImageListModel,
                 tag_counter_model: TagCounterModel):
        super().__init__(parent)
        self.setWindowTitle('Batch Reorder Tags')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        do_not_reorder_first_tag_check_box = (
            get_do_not_reorder_first_tag_check_box())
        layout.addWidget(do_not_reorder_first_tag_check_box)
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(20)
        sort_alphabetically_button = QPushButton('Sort Tags Alphabetically')
        sort_alphabetically_button.clicked.connect(
            lambda: image_list_model.sort_tags_alphabetically(
                do_not_reorder_first_tag_check_box.isChecked()))
        buttons_layout.addWidget(sort_alphabetically_button)
        sort_by_frequency_button = QPushButton('Sort Tags by Frequency')
        sort_by_frequency_button.clicked.connect(
            lambda: image_list_model.sort_tags_by_frequency(
                tag_counter_model.tag_counter,
                do_not_reorder_first_tag_check_box.isChecked()))
        buttons_layout.addWidget(sort_by_frequency_button)
        shuffle_button = QPushButton('Shuffle Tags Randomly')
        shuffle_button.clicked.connect(
            lambda: image_list_model.shuffle_tags(
                do_not_reorder_first_tag_check_box.isChecked()))
        buttons_layout.addWidget(shuffle_button)
        layout.addLayout(buttons_layout)


def get_do_not_reorder_first_tag_check_box() -> BigCheckBox:
    check_box = BigCheckBox()
    check_box.setText('Do not reorder first tag')
    settings = get_settings()
    check_box.setChecked(settings.value('do_not_reorder_first_tag',
                                        type=bool))
    check_box.stateChanged.connect(
        lambda state: settings.setValue(
            'do_not_reorder_first_tag',
            state == Qt.CheckState.Checked.value))
    return check_box
