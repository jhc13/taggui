from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


class ImageLabel(QLabel):
    def __init__(self, image_path: Path | None, parent):
        super().__init__(parent)
        self.image_path = image_path
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # This allows the label to shrink.
        self.setMinimumSize(QSize(1, 1))
        self.setAlignment(Qt.AlignCenter)

    def resizeEvent(self, event):
        """Resize the image whenever the label is resized."""
        if self.image_path:
            self.load_image(self.image_path)

    def load_image(self, image_path: Path):
        self.image_path = image_path
        pixmap = QPixmap(str(image_path)).scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)


class ImageViewer(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.image_label = ImageLabel(image_path=None, parent=self)
        QVBoxLayout(self).addWidget(self.image_label)

    def load_image(self, image_path: Path):
        self.image_label.load_image(image_path)
