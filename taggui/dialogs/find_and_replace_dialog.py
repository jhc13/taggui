from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from models.image_list_model import ImageListModel, Scope
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
        grid_layout.addWidget(QLabel('Scope'), 2, 0, Qt.AlignRight)
        grid_layout.addWidget(QLabel('Whole tags only'), 3, 0, Qt.AlignRight)
        self.find_line_edit = QLineEdit()
        self.find_line_edit.textChanged.connect(self.display_match_count)
        grid_layout.addWidget(self.find_line_edit, 0, 1)
        self.replace_line_edit = QLineEdit()
        grid_layout.addWidget(self.replace_line_edit, 1, 1)
        self.scope_combo_box = QComboBox()
        self.scope_combo_box.addItems(list(Scope))
        self.scope_combo_box.setCurrentText(
            self.settings.value('replace_scope', defaultValue=Scope.ALL_IMAGES,
                                type=str))
        self.scope_combo_box.currentTextChanged.connect(
            lambda text: self.settings.setValue('replace_scope', text))
        self.scope_combo_box.currentTextChanged.connect(
            self.display_match_count)
        grid_layout.addWidget(self.scope_combo_box, 2, 1)
        self.whole_tags_only_check_box = BigCheckBox()
        self.whole_tags_only_check_box.setChecked(
            self.settings.value('replace_whole_tags_only', defaultValue=False,
                                type=bool))
        self.whole_tags_only_check_box.stateChanged.connect(
            lambda state: self.settings.setValue(
                'replace_whole_tags_only',
                state == Qt.CheckState.Checked.value))
        self.whole_tags_only_check_box.stateChanged.connect(
            self.display_match_count)
        grid_layout.addWidget(self.whole_tags_only_check_box, 3, 1)
        layout.addLayout(grid_layout)
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
        scope = self.scope_combo_box.currentText()
        whole_tags_only = self.whole_tags_only_check_box.isChecked()
        match_count = self.image_list_model.get_text_match_count(
            text, scope, whole_tags_only)
        self.replace_button.setText(f'Replace {match_count} '
                                    f'{pluralize("instance", match_count)}')

    @Slot()
    def replace(self):
        scope = self.scope_combo_box.currentText()
        if self.whole_tags_only_check_box.isChecked():
            replace_text = self.replace_line_edit.text()
            if replace_text:
                self.image_list_model.rename_tag(self.find_line_edit.text(),
                                                 replace_text, scope)
            else:
                self.image_list_model.delete_tag(self.find_line_edit.text(),
                                                 scope)
        else:
            self.image_list_model.find_and_replace(
                self.find_line_edit.text(), self.replace_line_edit.text(),
                scope)
