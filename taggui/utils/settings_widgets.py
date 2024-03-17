from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLineEdit

from utils.big_widgets import BigCheckBox
from utils.settings import get_settings


class SettingsBigCheckBox(BigCheckBox):
    def __init__(self, key: str, default: bool):
        super().__init__()
        settings = get_settings()
        self.setChecked(settings.value(key, default, type=bool))
        self.stateChanged.connect(
            lambda state: settings.setValue(
                key, state == Qt.CheckState.Checked.value))


class SettingsComboBox(QComboBox):
    def __init__(self, key: str, default: str | None = None):
        super().__init__()
        self.key = key
        self.default = default
        self.settings = get_settings()

    def addItems(self, texts: list[str]):
        super().addItems(texts)
        # Setting the current text and connecting the signal must be done after
        # adding the items because `addItems()` clears the current text.
        if self.default is not None or self.settings.contains(self.key):
            self.setCurrentText(self.settings.value(self.key, self.default,
                                                    type=str))
        self.currentTextChanged.connect(
            lambda text: self.settings.setValue(self.key, text))


class SettingsLineEdit(QLineEdit):
    def __init__(self, key: str, default: str = ''):
        super().__init__()
        settings = get_settings()
        self.setText(settings.value(key, default, type=str))
        self.textChanged.connect(lambda text: settings.setValue(key, text))
