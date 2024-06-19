from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QDialog, QFileDialog, QGridLayout, QLabel,
                               QLineEdit, QPushButton, QTabWidget, QVBoxLayout,
                               QWidget)

from utils.settings import DEFAULT_SETTINGS, get_settings
from utils.settings_widgets import (SettingsBigCheckBox, SettingsLineEdit,
                                    SettingsSpinBox)


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.settings = get_settings()
        self.setWindowTitle('Settings')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Create tab widget and tabs
        tabs: QTabWidget = QTabWidget()
        appearance_tab: QWidget = QWidget()
        tagging_tab: QWidget = QWidget()
        directories_tab: QWidget = QWidget()

        tabs.addTab(appearance_tab, "Appearance")
        tabs.addTab(tagging_tab, "Tagging")
        tabs.addTab(directories_tab, "Directories")

        # Appearance Tab
        appearance_layout: QGridLayout = QGridLayout(appearance_tab)
        appearance_layout.addWidget(QLabel('Font size (pt)'), 0, 0, Qt.AlignmentFlag.AlignRight)
        font_size_spin_box: SettingsSpinBox = SettingsSpinBox(
            key='font_size', default=DEFAULT_SETTINGS['font_size'],
            minimum=1, maximum=99)
        font_size_spin_box.valueChanged.connect(self.show_restart_warning)
        appearance_layout.addWidget(font_size_spin_box, 0, 1, Qt.AlignmentFlag.AlignLeft)

        appearance_layout.addWidget(QLabel('Image width in image list (px)'), 1, 0, Qt.AlignmentFlag.AlignRight)
        image_list_image_width_spin_box: SettingsSpinBox = SettingsSpinBox(
            key='image_list_image_width',
            default=DEFAULT_SETTINGS['image_list_image_width'],
            minimum=16, maximum=9999)
        image_list_image_width_spin_box.valueChanged.connect(self.show_restart_warning)
        appearance_layout.addWidget(image_list_image_width_spin_box, 1, 1, Qt.AlignmentFlag.AlignLeft)

        # Tagging Tab
        tagging_layout: QGridLayout = QGridLayout(tagging_tab)

        tagging_layout.addWidget(QLabel('Tag separator'), 1, 0, Qt.AlignmentFlag.AlignRight)
        tag_separator_line_edit: QLineEdit = QLineEdit()
        tag_separator: str = self.settings.value(
            'tag_separator', defaultValue=DEFAULT_SETTINGS['tag_separator'],
            type=str)
        tag_separator_line_edit.setMaximumWidth(50)
        tag_separator_line_edit.setText(tag_separator)
        tag_separator_line_edit.textChanged.connect(self.handle_tag_separator_change)
        tagging_layout.addWidget(tag_separator_line_edit, 1, 1, Qt.AlignmentFlag.AlignLeft)

        tagging_layout.addWidget(QLabel('Insert space after tag separator'), 2, 0, Qt.AlignmentFlag.AlignRight)
        insert_space_after_tag_separator_check_box: SettingsBigCheckBox = SettingsBigCheckBox(
            key='insert_space_after_tag_separator',
            default=DEFAULT_SETTINGS['insert_space_after_tag_separator'])
        insert_space_after_tag_separator_check_box.stateChanged.connect(self.show_restart_warning)
        tagging_layout.addWidget(insert_space_after_tag_separator_check_box, 2, 1, Qt.AlignmentFlag.AlignLeft)

        tagging_layout.addWidget(QLabel('Show tag autocomplete suggestions'), 3, 0, Qt.AlignmentFlag.AlignRight)
        autocomplete_tags_check_box: SettingsBigCheckBox = SettingsBigCheckBox(
            key='autocomplete_tags',
            default=DEFAULT_SETTINGS['autocomplete_tags'])
        autocomplete_tags_check_box.stateChanged.connect(self.show_restart_warning)
        tagging_layout.addWidget(autocomplete_tags_check_box, 3, 1, Qt.AlignmentFlag.AlignLeft)

        # Directories Tab
        files_layout: QGridLayout = QGridLayout(directories_tab)
        files_layout.addWidget(QLabel('File types to show in image list'), 0, 0, Qt.AlignmentFlag.AlignRight)
        file_types_line_edit: SettingsLineEdit = SettingsLineEdit(
            key='image_list_file_formats',
            default=DEFAULT_SETTINGS['image_list_file_formats'])
        file_types_line_edit.setMinimumWidth(400)
        file_types_line_edit.textChanged.connect(self.show_restart_warning)
        files_layout.addWidget(file_types_line_edit, 0, 1, Qt.AlignmentFlag.AlignLeft)

        files_layout.addWidget(QLabel('Auto-captioning models directory'), 1, 0, Qt.AlignmentFlag.AlignRight)
        self.models_files_line_edit: SettingsLineEdit = SettingsLineEdit(
            key='models_directory_path',
            default=DEFAULT_SETTINGS['models_directory_path'])
        self.models_files_line_edit.setMinimumWidth(400)
        self.models_files_line_edit.setClearButtonEnabled(True)
        self.models_files_line_edit.textChanged.connect(self.show_restart_warning)
        files_layout.addWidget(self.models_files_line_edit, 1, 1, Qt.AlignmentFlag.AlignLeft)

        models_directory_button = QPushButton('Select Directory...')
        models_directory_button.setFixedWidth(int(models_directory_button.sizeHint().width() * 1.3))
        models_directory_button.clicked.connect(self.set_models_directory_path)
        files_layout.addWidget(models_directory_button, 2, 1, Qt.AlignmentFlag.AlignLeft)



        layout.addWidget(tabs)

        # Prevent the grid layout from moving to the center when the warning label is hidden.
        layout.addStretch()
        self.restart_warning = 'Restart the application to apply the new settings.'
        self.warning_label = QLabel(self.restart_warning)
        self.warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.warning_label.setStyleSheet('color: red;')
        layout.addWidget(self.warning_label)
        self.setFixedSize(self.sizeHint())
        self.warning_label.hide()

    @Slot()
    def show_restart_warning(self):
        self.warning_label.setText(self.restart_warning)
        self.warning_label.show()

    @Slot(str)
    def handle_tag_separator_change(self, tag_separator: str):
        if not tag_separator:
            self.warning_label.setText('The tag separator cannot be empty.')
            self.warning_label.show()
            return
        self.settings.setValue('tag_separator', tag_separator)
        self.show_restart_warning()

    @Slot()
    def set_models_directory_path(self):
        models_directory_path = self.settings.value(
            'models_directory_path',
            defaultValue=DEFAULT_SETTINGS['models_directory_path'], type=str)
        if models_directory_path:
            initial_directory_path = models_directory_path
        elif self.settings.contains('directory_path'):
            initial_directory_path = self.settings.value('directory_path')
        else:
            initial_directory_path = ''
        models_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption='Select directory containing auto-captioning models',
            dir=initial_directory_path)
        if models_directory_path:
            self.models_files_line_edit.setText(models_directory_path)


