import sys
from pathlib import Path

from PySide6.QtCore import QPersistentModelIndex, Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QFileDialog, QMainWindow,
                               QPushButton, QStackedWidget, QVBoxLayout,
                               QWidget)

from image_list import ImageList, ImageListModel
from image_tag_editor import ImageTagEditor
from image_viewer import ImageViewer
from settings import SettingsDialog, get_settings


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = get_settings()

        self.setWindowTitle('Captioning Tool')
        self.set_font_size(int(self.settings.value('font_size')))
        self.add_menus()
        self.image_viewer = ImageViewer(self)
        self.create_central_widget()

        self.image_list_image_width = int(
            self.settings.value('image_list_image_width'))
        self.image_list_model = ImageListModel(self.settings)
        self.image_list = ImageList(self.image_list_model, self)
        self.image_list.list_view.selectionModel().currentChanged.connect(
            self.set_image)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.image_list)

        self.image_tag_editor = ImageTagEditor(self.image_list_model, self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.image_tag_editor)

        self.restore()

    @Slot()
    def set_font_size(self, font_size: int):
        font = self.app.font()
        font.setPointSize(font_size)
        self.app.setFont(font)

    @Slot()
    def select_and_load_directory(self):
        if self.image_list_model.directory_path:
            initial_directory_path = str(self.image_list_model.directory_path)
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

    def add_menus(self):
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

    def create_central_widget(self):
        central_widget = QStackedWidget(self)
        load_directory_widget = QWidget()
        load_directory_button = QPushButton('Load directory')
        load_directory_button.clicked.connect(self.select_and_load_directory)
        QVBoxLayout(load_directory_widget).addWidget(load_directory_button,
                                                     alignment=Qt.AlignCenter)
        central_widget.addWidget(load_directory_widget)
        central_widget.addWidget(self.image_viewer)
        self.setCentralWidget(central_widget)

    @Slot()
    def set_image(self, index):
        index = QPersistentModelIndex(index)
        image = self.image_list_model.images[index.row()]
        self.image_viewer.load_image(image.path)
        self.image_tag_editor.load_tags(index, image.tags)

    def update_image_list(self):
        self.image_list_model.dataChanged.emit(
            self.image_list_model.index(0, 0),
            self.image_list_model.index(len(self.image_list_model.images) - 1,
                                        0))

    def load_directory(self, directory_path: Path):
        self.image_list_model.load_directory(directory_path)
        self.update_image_list()
        # Select the first image.
        self.image_list.list_view.setCurrentIndex(
            self.image_list_model.index(0, 0))
        self.centralWidget().setCurrentWidget(self.image_viewer)

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
                               str(self.image_list_model.directory_path))
        super().closeEvent(event)


def main():
    app = QApplication([])
    main_window = MainWindow(app)
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
