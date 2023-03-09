import sys
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QFileDialog, QMainWindow,
                               QPushButton, QVBoxLayout, QWidget)

from image_list import ImageList, ImageListModel
from model import Model
from settings import SettingsDialog, get_settings


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = get_settings()
        self.model = Model(self.settings)

        self.setWindowTitle('Captioning Tool')
        self.set_font_size(int(self.settings.value('font_size')))
        self.create_menu_bar()
        self.create_load_directory_button()
        self.image_list_image_width = int(
            self.settings.value('image_list_image_width'))
        self.image_list_model = ImageListModel(self.model.images, self)
        self.image_list = ImageList(self.image_list_model, self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.image_list)

        self.restore()

    @Slot()
    def set_font_size(self, font_size: int):
        font = self.app.font()
        font.setPointSize(font_size)
        self.app.setFont(font)

    @Slot()
    def select_and_load_directory(self):
        if self.model.directory_path:
            initial_directory_path = str(self.model.directory_path)
        else:
            initial_directory_path = ''
        load_directory_path = QFileDialog.getExistingDirectory(
            self, 'Select directory containing images', initial_directory_path)
        if not load_directory_path:
            return
        self.load_directory(Path(load_directory_path))

    @Slot()
    def show_settings_dialog(self):
        settings_dialog = SettingsDialog(self.settings, self)
        settings_dialog.exec()

    def create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu('File')
        load_directory_action = QAction('Load directory', self)
        load_directory_action.setShortcut(QKeySequence('Ctrl+L'))
        load_directory_action.triggered.connect(self.select_and_load_directory)
        file_menu.addAction(load_directory_action)
        settings_action = QAction('Settings', self)
        settings_action.setShortcut(QKeySequence('Ctrl+Alt+S'))
        settings_action.triggered.connect(self.show_settings_dialog)
        file_menu.addAction(settings_action)

    def create_load_directory_button(self):
        load_directory_widget = QWidget(self)
        load_directory_button = QPushButton('Load directory',
                                            load_directory_widget)
        load_directory_button.clicked.connect(self.select_and_load_directory)
        QVBoxLayout(load_directory_widget).addWidget(load_directory_button,
                                                     alignment=Qt.AlignCenter)
        self.setCentralWidget(load_directory_widget)

    def update_image_list(self):
        self.image_list_model.dataChanged.emit(
            self.image_list_model.index(0, 0),
            self.image_list_model.index(len(self.model.images) - 1, 0))

    def load_directory(self, directory_path: Path):
        self.model.load_directory(directory_path)
        self.update_image_list()
        # Select the first image.
        self.image_list.list_view.setCurrentIndex(
            self.image_list_model.index(0, 0))

    def restore(self):
        was_geometry_restored = False
        if self.settings.contains('geometry'):
            was_geometry_restored = self.restoreGeometry(
                self.settings.value('geometry'))
        if not was_geometry_restored:
            self.resize(1200, 800)
        self.restoreState(self.settings.value('window_state'))
        if self.settings.contains('directory_path'):
            self.load_directory(Path(self.settings.value('directory_path')))

    @Slot()
    def set_image_list_image_width(self, image_list_image_width: int):
        self.image_list_image_width = image_list_image_width
        self.update_image_list()
        self.image_list.set_image_width()

    def closeEvent(self, event):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('window_state', self.saveState())
        self.settings.setValue('directory_path',
                               str(self.model.directory_path))
        super().closeEvent(event)


def main():
    app = QApplication([])
    main_window = MainWindow(app)
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
