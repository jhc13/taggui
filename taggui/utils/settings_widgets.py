from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QLineEdit,
                               QPlainTextEdit, QSpinBox)

from utils.big_widgets import BigCheckBox
from utils.focused_scroll_mixin import FocusedScrollMixin
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
        setting: str = self.settings.value(self.key, self.default, type=str)
        super().addItems(texts)
        self.currentTextChanged.connect(
            lambda text: self.settings.setValue(self.key, text))
        if setting:
            self.setCurrentText(setting)


class FocusedScrollSettingsComboBox(FocusedScrollMixin, SettingsComboBox):
    pass


class FocusedScrollSettingsDoubleSpinBox(FocusedScrollMixin, QDoubleSpinBox):
    def __init__(self, key: str, default: float, minimum: float,
                 maximum: float):
        super().__init__()
        # The range must be set here so that the setting value is not clamped
        # by the default range.
        self.setRange(minimum, maximum)
        settings = get_settings()
        self.setValue(settings.value(key, default, type=float))
        self.valueChanged.connect(lambda value: settings.setValue(key, value))


class FocusedScrollSettingsSpinBox(FocusedScrollMixin, QSpinBox):
    def __init__(self, key: str, default: int, minimum: int, maximum: int):
        super().__init__()
        self.setRange(minimum, maximum)
        settings = get_settings()
        self.setValue(settings.value(key, default, type=int))
        self.valueChanged.connect(lambda value: settings.setValue(key, value))


class SettingsLineEdit(QLineEdit):
    def __init__(self, key: str, default: str = ''):
        super().__init__()
        settings = get_settings()
        self.setText(settings.value(key, default, type=str))
        self.textChanged.connect(lambda text: settings.setValue(key, text))


class SettingsPlainTextEdit(QPlainTextEdit):
    def __init__(self, key: str, default: str = ''):
        super().__init__()
        settings = get_settings()
        self.setPlainText(settings.value(key, default, type=str))
        self.textChanged.connect(lambda: settings.setValue(key,
                                                           self.toPlainText()))
