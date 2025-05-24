from math import ceil, floor
from PySide6.QtCore import (QPoint, QPointF, QRect, QSize)
from utils.enums import BucketStrategy
from utils.settings import settings
import utils.target_dimension as target_dimension

class Grid:
    """Span a grid inside the screen.

    The screen is adjusted according to bucket strategy and scaled to the
    target dimension and then the grid respects the latent size.
    """

    def __init__(self, screen: QRect):
        # the full image or the user cropped part of it
        self.screen: QRect
        # the visible part of the screen, i.e. the bucket cropped part of it
        self.visible: QRect
        # the size of the exported image
        self.target: QSize
        self.scale_x: float
        self.scale_y: float
        self.aspect_ratio: tuple[int, int, float] | None = None

        self.update(screen)

    def update(self, screen: QRect | None = None):
        assert screen == None or isinstance(screen, QRect)
        bucket_strategy = settings.value('export_bucket_strategy', type=str)
        if screen != None:
            self.screen = screen

        if self.screen.width() == 0 or self.screen.height() == 0:
            self.visible = self.screen
            self.target = QSize(1, 1)
            self.scale_x = 1
            self.scale_y = 1
            return

        vis_size = self.screen.size()
        self.target = target_dimension.get(vis_size)
        aspect_ratio = self.target.width() / self.target.height()

        if (bucket_strategy == BucketStrategy.CROP or
            bucket_strategy == BucketStrategy.CROP_SCALE):
            if (self.screen.height() * self.target.width()
                < self.target.height() * self.screen.width()): # too wide
                vis_size.setWidth(floor(self.screen.height() * aspect_ratio))
            else:
                vis_size.setHeight(floor(self.screen.width() / aspect_ratio))
        if bucket_strategy == BucketStrategy.CROP_SCALE:
                vis_size.setWidth(floor((self.screen.width() + vis_size.width())/2))
                vis_size.setHeight(floor((self.screen.height() + vis_size.height())/2))

        delta = self.screen.size() - vis_size
        self.visible = self.screen.adjusted(floor(delta.width()/2),
                                            floor(delta.height()/2),
                                            -ceil(delta.width()/2),
                                            -ceil(delta.height()/2))

        self.scale_x = self.target.width() / self.visible.width()
        self.scale_y = self.target.height() / self.visible.height()

        self.aspect_ratio = target_dimension.get_noteable_aspect_ratio(
            self.target.width(), self.target.height())

    def is_visible_equal_screen_size(self) -> bool:
        return self.screen.size() == self.visible

    def map_raw(self, point: QPoint) -> QPointF:
        """Translate point into screen coordinates."""
        assert isinstance(point, QPoint)
        return QPointF((point.x()-self.visible.x())*self.scale_x,
                       (point.y()-self.visible.y())*self.scale_y)


    def map(self, point: QPoint, method = round) -> QPoint:
        """Align the point to the closest position on the grid aligned at
        `base_point` and with a step width of `grid`.
        """
        assert isinstance(point, QPoint)
        latent_size = max(settings.value('export_latent_size', type=int), 1)
        raw = self.map_raw(point)
        return QPoint(method(raw.x()/latent_size)*latent_size,
                      method(raw.y()/latent_size)*latent_size)

    def snap(self, point: QPoint, method = round) -> QPointF:
        """Align the point to the closest position on the grid but in
        screen coordinates.
        """
        assert isinstance(point, QPoint)
        mapped = self.map(point, method)
        return QPointF(mapped.x()/self.scale_x + self.visible.x(),
                       mapped.y()/self.scale_y + self.visible.y())
