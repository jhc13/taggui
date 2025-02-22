from pathlib import Path
from PySide6.QtCore import QModelIndex, QPoint, QPointF, QRect, QSize, Qt, Signal, Slot, QEvent
from PySide6.QtGui import QCursor, QImageReader, QMouseEvent, QPixmap, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import (QFrame, QLabel, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from models.proxy_image_list_model import ProxyImageListModel
from utils.image import Image

class ImageLabel(QLabel):
    def __init__(self, scroll_area):
        super().__init__()
        self.scroll_area = scroll_area
        self.image_path = None
        self.is_zoom_to_fit = True
        self.zoom_factor = 1.0
        self.in_update = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setScaledContents(False)

    def resizeEvent(self, event: QResizeEvent):
        """Resize the image whenever the label is resized."""
        if self.image_path:
            self.update_image()

    def load_image(self, image_path: Path):
        self.image_path = image_path
        image_reader = QImageReader(str(self.image_path))
        # Rotate the image according to the orientation tag.
        image_reader.setAutoTransform(True)
        self.pixmap_orig = QPixmap.fromImageReader(image_reader)
        self.pixmap_orig.setDevicePixelRatio(self.devicePixelRatio())
        self.update_image()

    def update_image(self):
        if not self.pixmap_orig or self.in_update:
            return

        self.in_update = True

        if self.is_zoom_to_fit:
            self.zoom_factor = self.zoom_fit_ratio()

        pixmap = self.pixmap_orig.scaled(
            self.pixmap_orig.size() * self.pixmap_orig.devicePixelRatio() * self.zoom_factor,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(pixmap)
        self.adjustSize()
        self.in_update = False

    def zoom_in(self):
        self.is_zoom_to_fit = False # No longer zoom to fit
        self.zoom_factor = min(self.zoom_factor * 1.25, 4)
        self.update_image()

    def zoom_out(self):
        self.is_zoom_to_fit = False # No longer zoom to fit
        zoom_fit_ratio = self.zoom_fit_ratio()
        self.zoom_factor = max(self.zoom_factor / 1.25, min(self.zoom_fit_ratio(), 1.0))
        if self.zoom_factor == zoom_fit_ratio:
            self.is_zoom_to_fit = True # At the limit? Activate fit mode again
        self.update_image()

    def zoom_original(self):
        self.is_zoom_to_fit = False # No longer zoom to fit
        self.zoom_factor = 1.0
        self.update_image()

    def zoom_fit(self):
        self.is_zoom_to_fit = True
        self.update_image()

    def zoom_fit_ratio(self):
        widget_width = self.scroll_area.viewport().width()
        widget_height = self.scroll_area.viewport().height()
        image_width = self.pixmap_orig.width()
        image_height = self.pixmap_orig.height()

        if image_width > 0 and image_height > 0:
            width_ratio = widget_width / image_width
            height_ratio = widget_height / image_height
            return min(width_ratio, height_ratio)

        return 1.0 # this should not happen anyway

class ImageViewer(QWidget):
    zoom = Signal(float, name='zoomChanged')

    def __init__(self, proxy_image_list_model: ProxyImageListModel):
        super().__init__()
        self.proxy_image_list_model = proxy_image_list_model
        self.drag_start_pos = None
        self.drag_image_pos = None

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameStyle(QFrame.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Install event filter on the scroll area as the wheelEvent handler
        # didn't catch everything leading to strange bugs during zooming
        self.scroll_area.viewport().installEventFilter(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.scroll_area)
        self.setLayout(layout)


        self.image_label = ImageLabel(self.scroll_area)
        self.scroll_area.setWidget(self.image_label)

    @Slot()
    def load_image(self, proxy_image_index: QModelIndex):
        image: Image = self.proxy_image_list_model.data(
            proxy_image_index, Qt.ItemDataRole.UserRole)
        self.image_label.load_image(image.path)
        self.zoom_emit()

    @Slot()
    def zoom_in(self, center_pos: QPoint = None):
        factors = self.get_scroll_area_factors()
        self.image_label.zoom_in()
        self.move_scroll_area(factors)
        self.zoom_emit()

    @Slot()
    def zoom_out(self, center_pos: QPoint = None):
        factors = self.get_scroll_area_factors()
        self.image_label.zoom_out()
        self.move_scroll_area(factors)
        self.zoom_emit()

    @Slot()
    def zoom_original(self):
        factors = self.get_scroll_area_factors()
        self.image_label.zoom_original()
        self.move_scroll_area(factors)
        self.zoom_emit()

    @Slot()
    def zoom_fit(self):
        self.image_label.zoom_fit()
        self.zoom_emit()

    def zoom_emit(self):
        if self.image_label.is_zoom_to_fit:
            self.zoom.emit(-1)
        else:
            self.zoom.emit(self.image_label.zoom_factor)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            # Reset zoom - and toggle between original size and fit mode
            if self.image_label.is_zoom_to_fit:
                self.zoom_original()
            else:
                self.zoom_fit()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.drag_image_pos = (self.scroll_area.horizontalScrollBar().value(), self.scroll_area.verticalScrollBar().value())
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drag_start_pos:
            delta = event.pos() - self.drag_start_pos
            self.scroll_area.horizontalScrollBar().setValue(self.drag_image_pos[0] - delta.x())
            self.scroll_area.verticalScrollBar().setValue(self.drag_image_pos[1] - delta.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = None
            self.drag_image_pos = None
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().mouseReleaseEvent(event)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ControlModifier:
                # Handle the control key + mouse wheel event
                factors = self.get_scroll_area_factors(event.position())

                if event.angleDelta().y() > 0:
                    self.zoom_in()
                else:
                    self.zoom_out()

                self.move_scroll_area(factors)
                return True  # Event is handled
        return super().eventFilter(source, event)

    def get_scroll_area_factors(self, position: QPointF | None = None) -> tuple[float, float, float, float]:
        """
        Get the factos (fractions, percentages) of the mouse position on the
        image as well as it on the scroll area.
        """
        widgetPos = self.image_label.geometry()
        image_size = self.image_label.pixmap_orig.size()*self.image_label.zoom_factor
        if image_size.width() < self.scroll_area.viewport().width():
            offset_x = (self.scroll_area.width() - image_size.width())/2
        else:
            offset_x = 0
        if image_size.height() < self.scroll_area.viewport().height():
            offset_y = (self.scroll_area.height() - image_size.height())/2
        else:
            offset_y = 0

        if position:
            img_fac_x = (position.x()-widgetPos.x()-offset_x)/image_size.width()
            img_fac_y = (position.y()-widgetPos.y()-offset_y)/image_size.height()
            scroll_area_fac_x = position.x() / self.scroll_area.viewport().width()
            scroll_area_fac_y = position.y() / self.scroll_area.viewport().height()
        else:
            # No position -> assume center
            img_fac_x = (self.scroll_area.viewport().width()/2-widgetPos.x()-offset_x)/image_size.width()
            img_fac_y = (self.scroll_area.viewport().height()/2-widgetPos.y()-offset_y)/image_size.height()
            scroll_area_fac_x = 0.5
            scroll_area_fac_y = 0.5

        return (img_fac_x, img_fac_y, scroll_area_fac_x, scroll_area_fac_y)

    def move_scroll_area(self, factors):
        """
        Move the image in the scroll area so that the (fractional) position
        on the image appears on the (fractional) position of the scroll area
        """
        img_fac_x, img_fac_y, scroll_area_fac_x, scroll_area_fac_y = factors
        image_size = self.image_label.pixmap_orig.size()*self.image_label.zoom_factor
        if image_size.width() > self.scroll_area.viewport().width():
            viewport_x = scroll_area_fac_x * self.scroll_area.viewport().width()
            scroll_area_x = img_fac_x * image_size.width()
            self.scroll_area.horizontalScrollBar().setValue(scroll_area_x - viewport_x)
        if image_size.height() > self.scroll_area.viewport().height():
            viewport_y = scroll_area_fac_y * self.scroll_area.viewport().height()
            scroll_area_y = img_fac_y * image_size.height()
            self.scroll_area.verticalScrollBar().setValue(scroll_area_y - viewport_y)
