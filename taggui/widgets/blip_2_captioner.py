from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QVBoxLayout, QWidget


class Blip2Captioner(QDockWidget):
    def __init__(self):
        super().__init__()
        # Each `QDockWidget` needs a unique object name for saving its state.
        self.setObjectName('blip_2_captioner')
        self.setWindowTitle('BLIP-2 Captioner')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        # A container widget is required to use a layout with a `QDockWidget`.
        container = QWidget()
        layout = QVBoxLayout(container)
        self.setWidget(container)
