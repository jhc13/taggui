import re

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QDialog, QGridLayout, QLabel, QPushButton,
                               QVBoxLayout)

from models.image_list_model import ImageListModel, Scope
from utils.settings_widgets import (SettingsBigCheckBox, SettingsComboBox,
                                    SettingsLineEdit)
from utils.utils import pluralize


class FindAndReplaceDialog(QDialog):
    def __init__(self, parent, image_list_model: ImageListModel):
        super().__init__(parent)
        self.image_list_model = image_list_model
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
        grid_layout.addWidget(QLabel('Find text'), 0, 0,
                              Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('Replace with'), 1, 0,
                              Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('Scope'), 2, 0,
                              Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('Whole tags only'), 3, 0,
                              Qt.AlignmentFlag.AlignRight)
        grid_layout.addWidget(QLabel('Use regex for find text'), 4, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.find_text_line_edit = SettingsLineEdit(key='find_text')
        self.find_text_line_edit.setClearButtonEnabled(True)
        self.find_text_line_edit.textChanged.connect(self.display_match_count)
        grid_layout.addWidget(self.find_text_line_edit, 0, 1)
        self.replace_text_line_edit = SettingsLineEdit(key='replace_text')
        self.replace_text_line_edit.setClearButtonEnabled(True)
        grid_layout.addWidget(self.replace_text_line_edit, 1, 1)
        self.scope_combo_box = SettingsComboBox(key='replace_scope')
        self.scope_combo_box.addItems(list(Scope))
        self.scope_combo_box.currentTextChanged.connect(
            self.display_match_count)
        grid_layout.addWidget(self.scope_combo_box, 2, 1)
        self.whole_tags_only_check_box = SettingsBigCheckBox(
            key='replace_whole_tags_only', default=False)
        self.whole_tags_only_check_box.stateChanged.connect(
            self.display_match_count)
        grid_layout.addWidget(self.whole_tags_only_check_box, 3, 1)
        self.use_regex_check_box = SettingsBigCheckBox(key='replace_use_regex',
                                                       default=False)
        self.use_regex_check_box.stateChanged.connect(self.display_match_count)
        grid_layout.addWidget(self.use_regex_check_box, 4, 1)
        layout.addLayout(grid_layout)
        self.replace_button = QPushButton('Replace')
        self.replace_button.clicked.connect(self.replace)
        self.replace_button.clicked.connect(self.display_match_count)
        layout.addWidget(self.replace_button)
        self.display_match_count()

    def disable_replace_button(self):
        self.replace_button.setText('Replace')
        self.replace_button.setEnabled(False)

    @Slot()
    def display_match_count(self):
        text = self.find_text_line_edit.text()
        if not text:
            self.disable_replace_button()
            return
        self.replace_button.setEnabled(True)
        scope = self.scope_combo_box.currentText()
        whole_tags_only = self.whole_tags_only_check_box.isChecked()
        use_regex = self.use_regex_check_box.isChecked()
        try:
            match_count = self.image_list_model.get_text_match_count(
                text, scope, whole_tags_only, use_regex)
        except re.error:
            self.disable_replace_button()
            return
        self.replace_button.setText(f'Replace {match_count} '
                                    f'{pluralize("instance", match_count)}')

    @Slot()
    def replace(self):
        scope = self.scope_combo_box.currentText()
        use_regex = self.use_regex_check_box.isChecked()
        if self.whole_tags_only_check_box.isChecked():
            replace_text = self.replace_text_line_edit.text()
            if replace_text:
                self.image_list_model.rename_tags(
                    [self.find_text_line_edit.text()], replace_text, scope,
                    use_regex)
            else:
                self.image_list_model.delete_tags(
                    [self.find_text_line_edit.text()], scope, use_regex)
        else:
            self.image_list_model.find_and_replace(
                self.find_text_line_edit.text(),
                self.replace_text_line_edit.text(), scope, use_regex)
