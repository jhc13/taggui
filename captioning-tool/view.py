import sys

from PySide6.QtCore import QAbstractListModel, QSettings, QSize, Qt, Slot
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog,
                               QListView, QMainWindow, QPushButton,
                               QVBoxLayout, QWidget)

from model import Image, Model

default_settings = {
    'font_size': 18,
    'separator': ',',
    'insert_space_after_separator': True,
    'image_list_image_width': 200
}


class ImageListModel(QAbstractListModel):
    def __init__(self, images: list[Image], image_width: int, parent=None):
        super().__init__(parent)
        self.images = images
        self.image_width = image_width

    def rowCount(self, parent=None):
        return len(self.images)

    def data(self, index, role=None):
        image = self.images[index.row()]
        if role == Qt.DisplayRole:
            # The text shown next to the image.
            text = image.path.name
            if image.caption:
                text += f'\n{image.caption}'
            return text
        if role == Qt.DecorationRole:
            # The image.
            pixmap = QPixmap(str(image.path)).scaledToWidth(self.image_width)
            return QIcon(pixmap)
        if role == Qt.SizeHintRole:
            dimensions = image.dimensions
            if dimensions:
                width, height = dimensions
                # Scale the dimensions to the image width.
                return QSize(self.image_width,
                             int(self.image_width * height / width))
            return QSize(self.image_width, self.image_width)


class ImageList(QDockWidget):
    def __init__(self, image_width: int, parent=None):
        super().__init__(parent)
        self.image_width = image_width
        self.setObjectName('image_list')
        self.setWindowTitle('Images')
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        # Use a QListView instead of a QListWidget for faster loading.
        self.list_view = QListView(self)
        self.list_view.setIconSize(QSize(image_width, image_width * 4))
        self.list_view.setWordWrap(True)
        self.setWidget(self.list_view)

    def set_images(self, images):
        self.list_view.setModel(ImageListModel(images, self.image_width))


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.model = Model(
            separator=self.settings.value('separator'),
            insert_space_after_separator=bool(self.settings.value(
                'insert_space_after_separator')))

        self.setWindowTitle('Captioning Tool')
        was_geometry_restored = False
        if self.settings.contains('geometry'):
            was_geometry_restored = self.restoreGeometry(
                self.settings.value('geometry'))
        if not was_geometry_restored:
            self.resize(1200, 800)
        self.restoreState(self.settings.value('window_state'))

        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu('File')
        load_directory_action = QAction('Load directory', self)
        load_directory_action.setShortcut(QKeySequence('Ctrl+L'))
        load_directory_action.triggered.connect(self.load_directory)
        file_menu.addAction(load_directory_action)
        settings_action = QAction('Settings', self)
        settings_action.setShortcut(QKeySequence('Ctrl+Alt+S'))
        file_menu.addAction(settings_action)

        load_directory_widget = QWidget(self)
        load_directory_button = QPushButton('Load directory',
                                            load_directory_widget)
        load_directory_button.clicked.connect(self.load_directory)
        QVBoxLayout(load_directory_widget).addWidget(load_directory_button,
                                                     alignment=Qt.AlignCenter)
        self.setCentralWidget(load_directory_widget)

        self.image_list = ImageList(
            image_width=int(self.settings.value('image_list_image_width')),
            parent=self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.image_list)

    def closeEvent(self, event):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('window_state', self.saveState())
        super().closeEvent(event)

    @Slot()
    def load_directory(self):
        directory_path = QFileDialog.getExistingDirectory(
            self, 'Select directory containing images')
        if not directory_path:
            return
        images = self.model.load_directory(directory_path)
        self.image_list.set_images(images)


def set_default_settings(settings):
    for key, value in default_settings.items():
        if not settings.contains(key):
            settings.setValue(key, value)


def main():
    app = QApplication([])
    settings = QSettings('captioning-tool', 'captioning-tool')
    set_default_settings(settings)
    font = app.font()
    font.setPointSize(int(settings.value('font_size')))
    app.setFont(font)
    main_window = MainWindow(settings)
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
