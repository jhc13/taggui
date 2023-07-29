from pathlib import Path

from PySide6.QtCore import QItemSelection, QModelIndex, QUrl, Qt, Slot
from PySide6.QtGui import (QAction, QCloseEvent, QDesktopServices, QIcon,
                           QKeySequence, QPixmap)
from PySide6.QtWidgets import (QApplication, QFileDialog, QMainWindow,
                               QStackedWidget, QVBoxLayout, QWidget)

from models.image_list_model import ImageListModel
from models.image_tag_list_model import ImageTagListModel
from models.proxy_image_list_model import ProxyImageListModel
from models.tag_counter_model import TagCounterModel
from utils.big_widgets import BigPushButton
from utils.key_press_forwarder import KeyPressForwarder
from utils.settings import get_separator, get_settings
from utils.utils import get_resource_path
from widgets.all_tags_editor import AllTagsEditor
from widgets.blip_2_captioner import Blip2Captioner
from widgets.image_list import ImageList
from widgets.image_tags_editor import ImageTagsEditor
from widgets.image_viewer import ImageViewer
from widgets.settings_dialog import SettingsDialog

ICON_PATH = Path('images/icon.ico')
GITHUB_REPOSITORY_URL = 'https://github.com/jhc13/taggui'


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = get_settings()
        image_list_image_width = self.settings.value('image_list_image_width',
                                                     type=int)
        separator = get_separator(self.settings)
        self.image_list_model = ImageListModel(image_list_image_width,
                                               separator)
        self.proxy_image_list_model = ProxyImageListModel(
            self.image_list_model)
        self.tag_counter_model = TagCounterModel()
        self.image_tag_list_model = ImageTagListModel()

        self.setWindowIcon(QIcon(QPixmap(get_resource_path(ICON_PATH))))
        # Not setting this results in some ugly colors.
        self.setPalette(self.app.style().standardPalette())
        # The font size must be set before creating the widgets to ensure that
        # everything has the correct font size.
        self.set_font_size()
        self.image_viewer = ImageViewer(self.proxy_image_list_model)
        self.create_central_widget()
        self.image_list = ImageList(image_list_image_width,
                                    self.proxy_image_list_model)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.image_list)
        self.image_tags_editor = ImageTagsEditor(
            self.proxy_image_list_model, self.tag_counter_model,
            self.image_tag_list_model, separator)
        self.addDockWidget(Qt.RightDockWidgetArea, self.image_tags_editor)
        self.all_tags_editor = AllTagsEditor(self.tag_counter_model)
        self.addDockWidget(Qt.RightDockWidgetArea, self.all_tags_editor)
        self.blip_2_captioner = Blip2Captioner(self.image_list_model,
                                               self.image_list)
        self.addDockWidget(Qt.RightDockWidgetArea, self.blip_2_captioner)
        self.tabifyDockWidget(self.all_tags_editor, self.blip_2_captioner)
        self.all_tags_editor.raise_()
        # Set default widths for the dock widgets.
        # Temporarily set a size for the window so that the dock widgets can be
        # expanded to their default widths. If the window geometry was
        # previously saved, it will be restored later.
        self.resize(image_list_image_width * 8,
                    int(image_list_image_width * 4.5))
        self.resizeDocks([self.image_list, self.image_tags_editor,
                          self.all_tags_editor],
                         [int(image_list_image_width * 2.5)] * 3,
                         Qt.Horizontal)
        self.toggle_image_list_action = QAction('Images', parent=self)
        self.toggle_image_tags_editor_action = QAction('Image Tags',
                                                       parent=self)
        self.toggle_all_tags_editor_action = QAction('All Tags', parent=self)
        self.toggle_blip_2_captioner_action = QAction('BLIP-2 Captioner',
                                                      parent=self)
        self.create_menus()

        self.image_list_selection_model = (self.image_list.list_view
                                           .selectionModel())
        self.connect_image_list_signals()
        self.connect_image_tags_editor_signals()
        self.connect_all_tags_editor_signals()
        self.connect_blip_2_captioner_signals()
        # Forward any unhandled image changing key presses to the image list.
        key_press_forwarder = KeyPressForwarder(
            parent=self, target=self.image_list.list_view,
            keys_to_forward=(Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp,
                             Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End))
        self.installEventFilter(key_press_forwarder)

        self.restore()

    def closeEvent(self, event: QCloseEvent):
        """Save the window geometry and state before closing."""
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('window_state', self.saveState())
        super().closeEvent(event)

    def set_font_size(self):
        font = self.app.font()
        font_size = self.settings.value('font_size', type=int)
        font.setPointSize(font_size)
        self.app.setFont(font)

    def create_central_widget(self):
        central_widget = QStackedWidget()
        # Put the button inside a widget so that it will not fill up the entire
        # space.
        load_directory_widget = QWidget()
        load_directory_button = BigPushButton('Load Directory')
        load_directory_button.clicked.connect(self.select_and_load_directory)
        QVBoxLayout(load_directory_widget).addWidget(load_directory_button,
                                                     alignment=Qt.AlignCenter)
        central_widget.addWidget(load_directory_widget)
        central_widget.addWidget(self.image_viewer)
        self.setCentralWidget(central_widget)

    def load_directory(self, path: Path, select_index: int = 0):
        self.settings.setValue('directory_path', str(path))
        self.setWindowTitle(path.name)
        self.image_list_model.load_directory(path)
        self.clear_image_list_filter()
        # Clear the current index first to make sure that the `currentChanged`
        # signal is emitted even if the image at the index is already selected.
        self.image_list_selection_model.clearCurrentIndex()
        self.image_list.list_view.setCurrentIndex(
            self.proxy_image_list_model.index(select_index, 0))
        self.centralWidget().setCurrentWidget(self.image_viewer)

    @Slot()
    def select_and_load_directory(self):
        # Use the last loaded directory as the initial directory.
        if self.settings.contains('directory_path'):
            initial_directory_path = self.settings.value('directory_path')
        else:
            initial_directory_path = ''
        load_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption='Select directory to load images from',
            dir=initial_directory_path)
        if not load_directory_path:
            return
        self.load_directory(Path(load_directory_path))

    @Slot()
    def show_settings_dialog(self):
        settings_dialog = SettingsDialog(parent=self, settings=self.settings)
        settings_dialog.exec()

    def create_menus(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu('File')
        load_directory_action = QAction('Load Directory', parent=self)
        load_directory_action.setShortcut(QKeySequence('Ctrl+L'))
        load_directory_action.triggered.connect(self.select_and_load_directory)
        file_menu.addAction(load_directory_action)
        settings_action = QAction('Settings', parent=self)
        settings_action.triggered.connect(self.show_settings_dialog)
        file_menu.addAction(settings_action)
        exit_action = QAction('Exit', parent=self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menu_bar.addMenu('View')
        self.toggle_image_list_action.setCheckable(True)
        self.toggle_image_tags_editor_action.setCheckable(True)
        self.toggle_all_tags_editor_action.setCheckable(True)
        self.toggle_blip_2_captioner_action.setCheckable(True)
        self.toggle_image_list_action.triggered.connect(
            lambda is_checked: self.image_list.setVisible(is_checked))
        self.toggle_image_tags_editor_action.triggered.connect(
            lambda is_checked: self.image_tags_editor.setVisible(is_checked))
        self.toggle_all_tags_editor_action.triggered.connect(
            lambda is_checked: self.all_tags_editor.setVisible(is_checked))
        self.toggle_blip_2_captioner_action.triggered.connect(
            lambda is_checked: self.blip_2_captioner.setVisible(is_checked))
        view_menu.addAction(self.toggle_image_list_action)
        view_menu.addAction(self.toggle_image_tags_editor_action)
        view_menu.addAction(self.toggle_all_tags_editor_action)
        view_menu.addAction(self.toggle_blip_2_captioner_action)

        help_menu = menu_bar.addMenu('Help')
        open_github_repository_action = QAction('GitHub', parent=self)
        open_github_repository_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(GITHUB_REPOSITORY_URL)))
        help_menu.addAction(open_github_repository_action)

    @Slot()
    def save_image_index(self, proxy_image_index: QModelIndex):
        """
        Save the index of the currently selected image if the image list is not
        filtered.
        """
        if not self.proxy_image_list_model.filterRegularExpression().pattern():
            self.settings.setValue('image_index', proxy_image_index.row())

    def connect_image_list_signals(self):
        self.image_list_selection_model.currentChanged.connect(
            self.save_image_index)
        self.image_list_selection_model.currentChanged.connect(
            self.image_list.update_image_index_label)
        self.image_list_selection_model.currentChanged.connect(
            self.image_viewer.load_image)
        self.image_list_selection_model.currentChanged.connect(
            self.image_tags_editor.load_image_tags)
        self.image_list_model.modelReset.connect(
            lambda: self.tag_counter_model.count_tags(
                self.image_list_model.images))
        self.image_list_model.dataChanged.connect(
            lambda: self.tag_counter_model.count_tags(
                self.image_list_model.images))
        # Rows are inserted or removed from the proxy image list model when the
        # filter is changed.
        self.proxy_image_list_model.rowsInserted.connect(
            lambda: self.image_list.update_image_index_label(
                self.image_list.list_view.currentIndex()))
        self.proxy_image_list_model.rowsRemoved.connect(
            lambda: self.image_list.update_image_index_label(
                self.image_list.list_view.currentIndex()))
        # Connecting the signal directly without `isVisible()` causes the menu
        # item to be unchecked when the widget is an inactive tab.
        self.image_list.visibilityChanged.connect(
            lambda: self.toggle_image_list_action.setChecked(
                self.image_list.isVisible()))

    @Slot()
    def update_image_list_model_tags(self):
        self.image_list_model.update_image_tags(
            self.image_tags_editor.image_index,
            self.image_tag_list_model.stringList())

    def connect_image_tags_editor_signals(self):
        # `rowsInserted` does not have to be connected because `dataChanged`
        # is emitted when a tag is added.
        self.image_tag_list_model.dataChanged.connect(
            self.update_image_list_model_tags)
        self.image_tag_list_model.rowsRemoved.connect(
            self.update_image_list_model_tags)
        self.image_tag_list_model.rowsMoved.connect(
            self.update_image_list_model_tags)
        self.image_tags_editor.visibilityChanged.connect(
            lambda: self.toggle_image_tags_editor_action.setChecked(
                self.image_tags_editor.isVisible()))

    @Slot()
    def clear_image_list_filter(self):
        self.all_tags_editor.all_tags_list.selectionModel().clearSelection()
        # Clear the current index.
        self.all_tags_editor.all_tags_list.setCurrentIndex(QModelIndex())
        self.proxy_image_list_model.setFilterRegularExpression('')
        # Select the previously selected image in the unfiltered image list.
        select_index = self.settings.value('image_index', type=int) or 0
        self.image_list.list_view.setCurrentIndex(
            self.proxy_image_list_model.index(select_index, 0))

    @Slot()
    def set_image_list_filter(self, selected: QItemSelection,
                              _deselected: QItemSelection):
        """
        Set the regular expression of the image list filter to the selected
        tag. The tag is not a regular expression, but it has to be set as one
        to be able to be retrieved in the `filterAcceptsRow` method of the
        proxy image list model.
        """
        selected_indices = selected.indexes()
        if not selected_indices:
            return
        self.proxy_image_list_model.setFilterRegularExpression(
            selected_indices[0].data(role=Qt.EditRole))

    def connect_all_tags_editor_signals(self):
        self.all_tags_editor.clear_filter_button.clicked.connect(
            self.clear_image_list_filter)
        all_tags_selection_model = (self.all_tags_editor.all_tags_list
                                    .selectionModel())
        # `selectionChanged` must be used and not `currentChanged` because
        # `currentChanged` is not emitted when the same tag is deselected and
        # selected again.
        all_tags_selection_model.selectionChanged.connect(
            self.set_image_list_filter)
        all_tags_selection_model.selectionChanged.connect(
            lambda: self.image_list.list_view.setCurrentIndex(
                self.proxy_image_list_model.index(0, 0)))
        self.tag_counter_model.tag_renaming_requested.connect(
            self.image_list_model.rename_tag)
        self.tag_counter_model.tag_renaming_requested.connect(
            self.clear_image_list_filter)
        self.all_tags_editor.all_tags_list.tag_deletion_requested.connect(
            self.image_list_model.delete_tag)
        self.all_tags_editor.all_tags_list.tag_deletion_requested.connect(
            self.clear_image_list_filter)
        self.all_tags_editor.visibilityChanged.connect(
            lambda: self.toggle_all_tags_editor_action.setChecked(
                self.all_tags_editor.isVisible()))

    def connect_blip_2_captioner_signals(self):
        self.blip_2_captioner.caption_generated.connect(
            lambda image_index, _, tags:
            self.image_list_model.update_image_tags(image_index, tags))
        self.blip_2_captioner.caption_generated.connect(
            lambda image_index, *_:
            self.image_tags_editor.reload_image_tags_if_index_matches(
                image_index))
        self.blip_2_captioner.visibilityChanged.connect(
            lambda: self.toggle_blip_2_captioner_action.setChecked(
                self.blip_2_captioner.isVisible()))

    def restore(self):
        # Restore the window geometry and state.
        if self.settings.contains('geometry'):
            self.restoreGeometry(self.settings.value('geometry'))
        else:
            self.showMaximized()
        self.restoreState(self.settings.value('window_state'))
        # Get the last index of the last selected image.
        if self.settings.contains('image_index'):
            image_index = self.settings.value('image_index', type=int)
        else:
            image_index = 0
        # Load the last loaded directory.
        if self.settings.contains('directory_path'):
            directory_path = Path(self.settings.value('directory_path'))
            if directory_path.is_dir():
                self.load_directory(
                    Path(self.settings.value('directory_path')),
                    select_index=image_index)
