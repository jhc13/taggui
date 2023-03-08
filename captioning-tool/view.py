import sys

from PySide6.QtCore import QAbstractListModel, QSettings, QSize, Qt, Slot
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDockWidget,
                               QFileDialog, QGridLayout, QLabel, QLineEdit,
                               QListView, QMainWindow, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from model import Image, Model

default_settings = {
    'font_size': 18,
    'separator': ',',
    'insert_space_after_separator': True,
    'image_list_image_width': 200
}


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')

        font_size_spin_box = QSpinBox()
        font_size_spin_box.setRange(1, 99)
        font_size_spin_box.setValue(int(settings.value('font_size')))
        font_size_spin_box.valueChanged.connect(
            lambda value: settings.setValue('font_size', value))

        separator_line_edit = QLineEdit()
        separator_line_edit.setText(settings.value('separator'))
        separator_line_edit.setMaximumWidth(50)
        separator_line_edit.textChanged.connect(
            lambda text: settings.setValue('separator', text))

        insert_space_after_separator_check_box = QCheckBox()
        # The value is initially a Boolean, but later becomes a string.
        insert_space_after_separator_check_box.setChecked(
            settings.value('insert_space_after_separator')
            in (True, 'true'))
        insert_space_after_separator_check_box.stateChanged.connect(
            lambda state: settings.setValue(
                'insert_space_after_separator',
                state == Qt.CheckState.Checked.value))

        image_list_image_width_spin_box = QSpinBox()
        image_list_image_width_spin_box.setRange(1, 9999)
        image_list_image_width_spin_box.setValue(
            int(settings.value('image_list_image_width')))
        image_list_image_width_spin_box.valueChanged.connect(
            lambda value: settings.setValue('image_list_image_width', value))

        layout = QGridLayout(self)
        layout.addWidget(QLabel('Font size'), 0, 0, Qt.AlignRight)
        layout.addWidget(font_size_spin_box, 0, 1, Qt.AlignLeft)
        layout.addWidget(QLabel('Separator'), 1, 0, Qt.AlignRight)
        layout.addWidget(separator_line_edit, 1, 1, Qt.AlignLeft)
        layout.addWidget(QLabel('Insert space after separator'), 2, 0,
                         Qt.AlignRight)
        layout.addWidget(insert_space_after_separator_check_box, 2, 1,
                         Qt.AlignLeft)
        layout.addWidget(QLabel('Image list image width (px)'), 3, 0,
                         Qt.AlignRight)
        layout.addWidget(image_list_image_width_spin_box, 3, 1, Qt.AlignLeft)
        self.adjustSize()


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
        settings_action.triggered.connect(self.show_settings_dialog)
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

    @Slot()
    def show_settings_dialog(self):
        settings_dialog = SettingsDialog(self.settings, self)
        settings_dialog.exec()


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
