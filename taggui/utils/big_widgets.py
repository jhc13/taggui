from PySide6.QtWidgets import QCheckBox, QPushButton

from utils.settings import DEFAULT_SETTINGS, settings


class BigPushButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        new_size = self.sizeHint() * 1.5
        self.setFixedSize(new_size)


class TallPushButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        new_height = int(self.sizeHint().height() * 1.5)
        self.setFixedHeight(new_height)


class BigCheckBox(QCheckBox):
    def __init__(self, text: str | None = None):
        super().__init__(text)
        font_size = settings.value(
            'font_size', defaultValue=DEFAULT_SETTINGS['font_size'], type=int)
        new_size = font_size * 1.5
        self.setStyleSheet(
            f'QCheckBox::indicator '
            f'{{ width: {new_size}px; height: {new_size}px; }}')
