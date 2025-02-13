from pathlib import Path

from PySide6.QtCore import QModelIndex, QSize, Qt, Slot
from PySide6.QtGui import QImageReader, QPixmap, QResizeEvent, QImage
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from models.proxy_image_list_model import ProxyImageListModel
from utils.image import Image
from PIL import Image as pilimage
import pillow_jxl  # Ensure this is installed

class ImageLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.image_path = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(QSize(1, 1))  # Allows the label to shrink

    def resizeEvent(self, event):
        """Reload the image whenever the label is resized."""
        if self.image_path:
            self.load_image(self.image_path)

    def load_image(self, image_path: Path):
        self.image_path = image_path

        if image_path.suffix.lower() == ".jxl":
            self.load_jxl_image(image_path)
        else:
            self.load_standard_image(image_path)

    def load_jxl_image(self, image_path: Path):
        """Manually load a JPEG XL image and convert it to QPixmap."""
        try:
            pil_image = pilimage.open(image_path)  # Decode JXL using Pillow
            pil_image = pil_image.convert("RGBA")  # Ensure RGBA format

            qimage = QImage(
                pil_image.tobytes("raw", "RGBA"),
                pil_image.width,
                pil_image.height,
                QImage.Format_RGBA8888
            )

            self.display_qimage(qimage)

        except Exception as e:
            print(f"Error loading JXL image {image_path}: {e}")
            self.clear()

    def load_standard_image(self, image_path: Path):
        """Load standard images using QImageReader."""
        image_reader = QImageReader(str(image_path))
        image_reader.setAutoTransform(True)  # Apply EXIF rotation
        qimage = image_reader.read()

        if qimage.isNull():
            print(f"Error: QImageReader failed to load {image_path}")
            self.clear()
            return

        self.display_qimage(qimage)

    def display_qimage(self, qimage: QImage):
        """Scale and display the QImage while maintaining aspect ratio."""
        pixmap = QPixmap.fromImage(qimage)
        pixmap.setDevicePixelRatio(self.devicePixelRatio())
        pixmap = pixmap.scaled(
            self.size() * pixmap.devicePixelRatio(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(pixmap)


class ImageViewer(QWidget):
    def __init__(self, proxy_image_list_model: ProxyImageListModel):
        super().__init__()
        self.proxy_image_list_model = proxy_image_list_model
        self.image_label = ImageLabel()
        QVBoxLayout(self).addWidget(self.image_label)

    @Slot()
    def load_image(self, proxy_image_index: QModelIndex):
        image: Image = self.proxy_image_list_model.data(
            proxy_image_index, Qt.ItemDataRole.UserRole)
        self.image_label.load_image(image.path)
