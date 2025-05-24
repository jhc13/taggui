from pathlib import Path

from PySide6.QtCore import QKeyCombination, QModelIndex, QUrl, Qt, Slot
from PySide6.QtGui import (QAction, QActionGroup, QCloseEvent, QDesktopServices,
                           QIcon, QKeySequence, QShortcut, QMouseEvent)
from PySide6.QtWidgets import (QApplication, QFileDialog, QMainWindow,
                               QMessageBox, QStackedWidget, QToolBar,
                               QVBoxLayout, QWidget, QSizePolicy, QHBoxLayout,
                               QLabel)

from transformers import AutoTokenizer

from dialogs.batch_reorder_tags_dialog import BatchReorderTagsDialog
from dialogs.find_and_replace_dialog import FindAndReplaceDialog
from dialogs.export_dialog import ExportDialog
from dialogs.settings_dialog import SettingsDialog
from models.image_list_model import ImageListModel
from models.image_tag_list_model import ImageTagListModel
from models.proxy_image_list_model import ProxyImageListModel
from models.tag_counter_model import TagCounterModel
from utils.icons import (taggui_icon, create_add_box_icon, toggle_marking_icon,
                         show_markings_icon, show_labels_icon,
                         show_marking_latent_icon)
from utils.big_widgets import BigPushButton
from utils.image import Image
from utils.key_press_forwarder import KeyPressForwarder
from utils.settings import DEFAULT_SETTINGS, settings, get_tag_separator
from utils.shortcut_remover import ShortcutRemover
from utils.utils import get_resource_path, pluralize
from widgets.all_tags_editor import AllTagsEditor
from widgets.auto_captioner import AutoCaptioner
from widgets.auto_markings import AutoMarkings
from widgets.image_list import ImageList
from widgets.image_tags_editor import ImageTagsEditor
from widgets.image_viewer import ImageViewer, ImageMarking

GITHUB_REPOSITORY_URL = 'https://github.com/jhc13/taggui'
TOKENIZER_DIRECTORY_PATH = Path('clip-vit-base-patch32')


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        # The path of the currently loaded directory. This is set later when a
        # directory is loaded.
        self.directory_path = None
        self.is_running = True
        app.aboutToQuit.connect(lambda: setattr(self, 'is_running', False))
        image_list_image_width = settings.value(
            'image_list_image_width',
            defaultValue=DEFAULT_SETTINGS['image_list_image_width'], type=int)
        tag_separator = get_tag_separator()
        self.image_list_model = ImageListModel(image_list_image_width,
                                               tag_separator)
        tokenizer = AutoTokenizer.from_pretrained(
            get_resource_path(TOKENIZER_DIRECTORY_PATH))
        self.proxy_image_list_model = ProxyImageListModel(
            self.image_list_model, tokenizer, tag_separator)
        self.image_list_model.proxy_image_list_model = (
            self.proxy_image_list_model)
        self.tag_counter_model = TagCounterModel()
        self.image_tag_list_model = ImageTagListModel()

        self.setWindowIcon(taggui_icon())
        # Not setting this results in some ugly colors.
        self.setPalette(self.app.style().standardPalette())
        # The font size must be set before creating the widgets to ensure that
        # everything has the correct font size.
        self.set_font_size()
        self.image_viewer = ImageViewer(self.proxy_image_list_model)
        self.create_central_widget()

        self.toolbar = QToolBar('Main toolbar', self)
        self.toolbar.setObjectName('Main toolbar')
        self.toolbar.setFloatable(True)
        self.addToolBar(self.toolbar)
        self.zoom_fit_best_action = QAction(QIcon.fromTheme('zoom-fit-best'),
                                            'Zoom to fit', self)
        self.zoom_fit_best_action.setCheckable(True)
        self.toolbar.addAction(self.zoom_fit_best_action)
        self.zoom_in_action = QAction(QIcon.fromTheme('zoom-in'),
                                      'Zoom in', self)
        self.toolbar.addAction(self.zoom_in_action)
        self.zoom_original_action = QAction(QIcon.fromTheme('zoom-original'),
                                            'Original size', self)
        self.zoom_original_action.setCheckable(True)
        self.toolbar.addAction(self.zoom_original_action)
        self.zoom_out_action = QAction(QIcon.fromTheme('zoom-out'),
                                       'Zoom out', self)
        self.toolbar.addAction(self.zoom_out_action)
        self.toolbar.addSeparator()
        self.add_action_group = QActionGroup(self)
        self.add_action_group.setExclusionPolicy(QActionGroup.ExclusiveOptional)
        self.add_crop_action = QAction(create_add_box_icon(Qt.blue),
                                       'Add crop', self.add_action_group)
        self.add_crop_action.setCheckable(True)
        self.toolbar.addAction(self.add_crop_action)
        self.add_hint_action = QAction(create_add_box_icon(Qt.gray),
                                       'Add hint', self.add_action_group)
        self.add_hint_action.setCheckable(True)
        self.toolbar.addAction(self.add_hint_action)
        self.add_exclude_action = QAction(create_add_box_icon(Qt.red),
                                          'Add exclude mask', self.add_action_group)
        self.add_exclude_action.setCheckable(True)
        self.toolbar.addAction(self.add_exclude_action)
        self.add_include_action = QAction(create_add_box_icon(Qt.green),
                                          'Add include mask', self.add_action_group)
        self.add_include_action.setCheckable(True)
        self.toolbar.addAction(self.add_include_action)
        self.delete_marking_action = QAction(QIcon.fromTheme('edit-delete'),
                                            'Delete marking', self)
        self.delete_marking_action.setEnabled(False)
        self.toolbar.addAction(self.delete_marking_action)
        self.add_toggle_marking_action = QAction(toggle_marking_icon(),
            'Change marking type', self)
        self.add_toggle_marking_action.setEnabled(False)
        self.toolbar.addAction(self.add_toggle_marking_action)
        self.add_show_marking_action = QAction(show_markings_icon(),
            'Show markings', self)
        self.add_show_marking_action.setCheckable(True)
        self.add_show_marking_action.setChecked(True)
        self.toolbar.addAction(self.add_show_marking_action)
        self.add_show_labels_action = QAction(show_labels_icon(),
            'Show labels', self)
        self.add_show_labels_action.setCheckable(True)
        self.add_show_labels_action.setChecked(True)
        self.toolbar.addAction(self.add_show_labels_action)
        self.add_show_marking_latent_action = QAction(show_marking_latent_icon(),
            'Show marking in latent space', self)
        self.add_show_marking_latent_action.setCheckable(True)
        self.add_show_marking_latent_action.setChecked(True)
        self.toolbar.addAction(self.add_show_marking_latent_action)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)
        star_widget = QWidget()
        star_layout = QHBoxLayout(star_widget)
        star_layout.setContentsMargins(0, 0, 0, 0)
        star_layout.setSpacing(0)
        self.rating = 0
        self.star_labels = []
        for i in range(6):
            shortcut = QShortcut(QKeySequence(f'Ctrl+{i}'), self)
            shortcut.activated.connect(lambda checked=False, rating=i:
                                       self.set_rating(2*rating, False))
            if i == 0:
                continue
            star_label = QLabel('☆', self)
            star_label.setEnabled(False)
            star_label.setAlignment(Qt.AlignCenter)
            star_label.setStyleSheet('QLabel { font-size: 22px; }')
            star_label.setToolTip(f'Ctrl+{i}')
            star_label.mousePressEvent = lambda event, rating=i: (
                self.set_rating(rating/5.0, True, event))
            self.star_labels.append(star_label)
            star_layout.addWidget(star_label)
        self.image_viewer.rating_changed.connect(self.set_rating)
        self.toolbar.addWidget(star_widget)

        self.image_list = ImageList(self.proxy_image_list_model,
                                    tag_separator, image_list_image_width)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,
                           self.image_list)
        self.image_tags_editor = ImageTagsEditor(
            self.proxy_image_list_model, self.tag_counter_model,
            self.image_tag_list_model, self.image_list, tokenizer,
            tag_separator)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.image_tags_editor)
        self.all_tags_editor = AllTagsEditor(self.tag_counter_model)
        self.tag_counter_model.all_tags_list = (self.all_tags_editor
                                                .all_tags_list)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.all_tags_editor)
        self.auto_captioner = AutoCaptioner(self.image_list_model,
                                            self.image_list)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.auto_captioner)
        self.auto_markings = AutoMarkings(self.image_list_model,
                                          self.image_list, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                           self.auto_markings)
        self.tabifyDockWidget(self.all_tags_editor, self.auto_captioner)
        self.tabifyDockWidget(self.auto_captioner, self.auto_markings)
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
                         Qt.Orientation.Horizontal)
        # Disable some widgets until a directory is loaded.
        self.image_tags_editor.tag_input_box.setDisabled(True)
        self.auto_captioner.start_cancel_button.setDisabled(True)
        self.reload_directory_action = QAction('Reload Directory', parent=self)
        self.reload_directory_action.setDisabled(True)
        self.undo_action = QAction('Undo', parent=self)
        self.redo_action = QAction('Redo', parent=self)
        self.toggle_toolbar_action = QAction('Toolbar', parent=self)
        self.toggle_image_list_action = QAction('Images', parent=self)
        self.toggle_image_tags_editor_action = QAction('Image Tags',
                                                       parent=self)
        self.toggle_all_tags_editor_action = QAction('All Tags', parent=self)
        self.toggle_auto_captioner_action = QAction('Auto-Captioner',
                                                    parent=self)
        self.toggle_auto_markings_action = QAction('Auto-Markings',
                                                    parent=self)
        self.create_menus()

        self.image_list_selection_model = (self.image_list.list_view
                                           .selectionModel())
        self.image_list_model.image_list_selection_model = (
            self.image_list_selection_model)
        self.connect_toolbar_signals()
        self.connect_image_list_signals()
        self.connect_image_tags_editor_signals()
        self.connect_all_tags_editor_signals()
        self.connect_auto_captioner_signals()
        self.connect_auto_markings_signals()
        # Forward any unhandled image changing key presses to the image list.
        key_press_forwarder = KeyPressForwarder(
            parent=self, target=self.image_list.list_view,
            keys_to_forward=(Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp,
                             Qt.Key.Key_PageDown, Qt.Key.Key_Home,
                             Qt.Key.Key_End))
        self.installEventFilter(key_press_forwarder)
        # Remove the Ctrl+Z shortcut from text input boxes to prevent it from
        # conflicting with the undo action.
        ctrl_z = QKeyCombination(Qt.KeyboardModifier.ControlModifier,
                                 key=Qt.Key.Key_Z)
        ctrl_y = QKeyCombination(Qt.KeyboardModifier.ControlModifier,
                                 key=Qt.Key.Key_Y)
        shortcut_remover = ShortcutRemover(parent=self,
                                           shortcuts=(ctrl_z, ctrl_y))
        self.image_list.filter_line_edit.installEventFilter(shortcut_remover)
        self.image_tags_editor.tag_input_box.installEventFilter(
            shortcut_remover)
        self.all_tags_editor.filter_line_edit.installEventFilter(
            shortcut_remover)
        # Set keyboard shortcuts.
        focus_filter_images_box_shortcut = QShortcut(
            QKeySequence('Alt+F'), self)
        focus_filter_images_box_shortcut.activated.connect(
            self.image_list.raise_)
        focus_filter_images_box_shortcut.activated.connect(
            self.image_list.filter_line_edit.setFocus)
        focus_add_tag_box_shortcut = QShortcut(QKeySequence('Alt+A'), self)
        focus_add_tag_box_shortcut.activated.connect(
            self.image_tags_editor.raise_)
        focus_add_tag_box_shortcut.activated.connect(
            self.image_tags_editor.tag_input_box.setFocus)
        focus_image_tags_list_shortcut = QShortcut(QKeySequence('Alt+I'), self)
        focus_image_tags_list_shortcut.activated.connect(
            self.image_tags_editor.raise_)
        focus_image_tags_list_shortcut.activated.connect(
            self.image_tags_editor.image_tags_list.setFocus)
        focus_image_tags_list_shortcut.activated.connect(
            self.image_tags_editor.select_first_tag)
        focus_search_tags_box_shortcut = QShortcut(QKeySequence('Alt+S'), self)
        focus_search_tags_box_shortcut.activated.connect(
            self.all_tags_editor.raise_)
        focus_search_tags_box_shortcut.activated.connect(
            self.all_tags_editor.filter_line_edit.setFocus)
        focus_caption_button_shortcut = QShortcut(QKeySequence('Alt+C'), self)
        focus_caption_button_shortcut.activated.connect(
            self.auto_captioner.raise_)
        focus_caption_button_shortcut.activated.connect(
            self.auto_captioner.start_cancel_button.setFocus)
        go_to_previous_image_shortcut = QShortcut(QKeySequence('Ctrl+Up'),
                                                  self)
        go_to_previous_image_shortcut.activated.connect(
            self.image_list.go_to_previous_image)
        go_to_next_image_shortcut = QShortcut(QKeySequence('Ctrl+Down'), self)
        go_to_next_image_shortcut.activated.connect(
            self.image_list.go_to_next_image)
        jump_to_first_untagged_image_shortcut = QShortcut(
            QKeySequence('Ctrl+J'), self)
        jump_to_first_untagged_image_shortcut.activated.connect(
            self.image_list.jump_to_first_untagged_image)
        self.restore()
        self.image_tags_editor.tag_input_box.setFocus()

    def closeEvent(self, event: QCloseEvent):
        """Save the window geometry and state before closing."""
        settings.setValue('geometry', self.saveGeometry())
        settings.setValue('window_state', self.saveState())
        super().closeEvent(event)

    def set_font_size(self):
        font = self.app.font()
        font_size = settings.value(
            'font_size', defaultValue=DEFAULT_SETTINGS['font_size'], type=int)
        font.setPointSize(font_size)
        self.app.setFont(font)

    def create_central_widget(self):
        central_widget = QStackedWidget()
        # Put the button inside a widget so that it will not fill up the entire
        # space.
        load_directory_widget = QWidget()
        load_directory_button = BigPushButton('Load Directory...')
        load_directory_button.clicked.connect(self.select_and_load_directory)
        QVBoxLayout(load_directory_widget).addWidget(
            load_directory_button, alignment=Qt.AlignmentFlag.AlignCenter)
        central_widget.addWidget(load_directory_widget)
        central_widget.addWidget(self.image_viewer)
        self.setCentralWidget(central_widget)

    @Slot()
    def zoom(self, factor):
        if factor < 0:
            self.zoom_fit_best_action.setChecked(True)
            self.zoom_original_action.setChecked(False)
        elif factor == 1.0:
            self.zoom_fit_best_action.setChecked(False)
            self.zoom_original_action.setChecked(True)
        else:
            self.zoom_fit_best_action.setChecked(False)
            self.zoom_original_action.setChecked(False)

    def load_directory(self, path: Path, select_index: int = 0,
                       save_path_to_settings: bool = False):
        self.directory_path = path.resolve()
        if save_path_to_settings:
            settings.setValue('directory_path', str(self.directory_path))
        self.setWindowTitle(path.name)
        self.image_list_model.load_directory(path)
        self.image_list.filter_line_edit.clear()
        self.all_tags_editor.filter_line_edit.clear()
        # Clear the current index first to make sure that the `currentChanged`
        # signal is emitted even if the image at the index is already selected.
        self.image_list_selection_model.clearCurrentIndex()
        self.image_list.list_view.setCurrentIndex(
            self.proxy_image_list_model.index(select_index, 0))
        self.centralWidget().setCurrentWidget(self.image_viewer)
        self.reload_directory_action.setDisabled(False)
        self.image_tags_editor.tag_input_box.setDisabled(False)
        self.auto_captioner.start_cancel_button.setDisabled(False)

    @Slot()
    def select_and_load_directory(self):
        initial_directory = (str(self.directory_path)
                             if self.directory_path else '')
        load_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption='Select directory to load images from',
            dir=initial_directory)
        if not load_directory_path:
            return
        self.load_directory(Path(load_directory_path),
                            save_path_to_settings=True)

    @Slot()
    def reload_directory(self):
        # Save the filter text and the index of the selected image to restore
        # them after reloading the directory.
        filter_text = self.image_list.filter_line_edit.text()
        select_index_key = ('image_index'
                            if self.proxy_image_list_model.filter is None
                            else 'filtered_image_index')
        select_index = settings.value(select_index_key, type=int) or 0
        self.load_directory(self.directory_path)
        self.image_list.filter_line_edit.setText(filter_text)
        # If the selected image index is out of bounds due to images being
        # deleted, select the last image.
        if select_index >= self.proxy_image_list_model.rowCount():
            select_index = self.proxy_image_list_model.rowCount() - 1
        self.image_list.list_view.setCurrentIndex(
            self.proxy_image_list_model.index(select_index, 0))

    @Slot()
    def export_images_dialog(self):
        export_dialog = ExportDialog(parent=self, image_list=self.image_list)
        export_dialog.exec()
        return

    @Slot()
    def show_settings_dialog(self):
        settings_dialog = SettingsDialog(parent=self)
        settings_dialog.exec()

    @Slot()
    def show_find_and_replace_dialog(self):
        find_and_replace_dialog = FindAndReplaceDialog(
            parent=self, image_list_model=self.image_list_model)
        find_and_replace_dialog.exec()

    @Slot()
    def show_batch_reorder_tags_dialog(self):
        batch_reorder_tags_dialog = BatchReorderTagsDialog(
            parent=self, image_list_model=self.image_list_model,
            tag_counter_model=self.tag_counter_model)
        batch_reorder_tags_dialog.exec()

    @Slot()
    def remove_duplicate_tags(self):
        removed_tag_count = self.image_list_model.remove_duplicate_tags()
        message_box = QMessageBox()
        message_box.setWindowTitle('Remove Duplicate Tags')
        message_box.setIcon(QMessageBox.Icon.Information)
        if not removed_tag_count:
            text = 'No duplicate tags were found.'
        else:
            text = (f'Removed {removed_tag_count} duplicate '
                    f'{pluralize("tag", removed_tag_count)}.')
        message_box.setText(text)
        message_box.exec()

    @Slot()
    def remove_empty_tags(self):
        removed_tag_count = self.image_list_model.remove_empty_tags()
        message_box = QMessageBox()
        message_box.setWindowTitle('Remove Empty Tags')
        message_box.setIcon(QMessageBox.Icon.Information)
        if not removed_tag_count:
            text = 'No empty tags were found.'
        else:
            text = (f'Removed {removed_tag_count} empty '
                    f'{pluralize("tag", removed_tag_count)}.')
        message_box.setText(text)
        message_box.exec()

    def create_menus(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu('File')
        load_directory_action = QAction('Load Directory...', parent=self)
        load_directory_action.setShortcut(QKeySequence('Ctrl+L'))
        load_directory_action.triggered.connect(self.select_and_load_directory)
        file_menu.addAction(load_directory_action)
        self.reload_directory_action.setShortcuts(
            [QKeySequence('Ctrl+Shift+L'), QKeySequence('F5')])
        self.reload_directory_action.triggered.connect(self.reload_directory)
        file_menu.addAction(self.reload_directory_action)
        export_action = QAction('Export...', parent=self)
        export_action.triggered.connect(self.export_images_dialog)
        file_menu.addAction(export_action)
        settings_action = QAction('Settings...', parent=self)
        settings_action.setShortcut(QKeySequence('Ctrl+Alt+S'))
        settings_action.triggered.connect(self.show_settings_dialog)
        file_menu.addAction(settings_action)
        exit_action = QAction('Exit', parent=self)
        exit_action.setShortcut(QKeySequence('Ctrl+W'))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menu_bar.addMenu('Edit')
        self.undo_action.setShortcut(QKeySequence('Ctrl+Z'))
        self.undo_action.triggered.connect(self.image_list_model.undo)
        self.undo_action.setDisabled(True)
        edit_menu.addAction(self.undo_action)
        self.redo_action.setShortcut(QKeySequence('Ctrl+Y'))
        self.redo_action.triggered.connect(self.image_list_model.redo)
        self.redo_action.setDisabled(True)
        edit_menu.addAction(self.redo_action)
        find_and_replace_action = QAction('Find and Replace...', parent=self)
        find_and_replace_action.setShortcut(QKeySequence('Ctrl+R'))
        find_and_replace_action.triggered.connect(
            self.show_find_and_replace_dialog)
        edit_menu.addAction(find_and_replace_action)
        batch_reorder_tags_action = QAction('Batch Reorder Tags...',
                                            parent=self)
        batch_reorder_tags_action.setShortcut(QKeySequence('Ctrl+B'))
        batch_reorder_tags_action.triggered.connect(
            self.show_batch_reorder_tags_dialog)
        edit_menu.addAction(batch_reorder_tags_action)
        remove_duplicate_tags_action = QAction('Remove Duplicate Tags',
                                               parent=self)
        remove_duplicate_tags_action.setShortcut(QKeySequence('Ctrl+D'))
        remove_duplicate_tags_action.triggered.connect(
            self.remove_duplicate_tags)
        edit_menu.addAction(remove_duplicate_tags_action)
        remove_empty_tags_action = QAction('Remove Empty Tags', parent=self)
        remove_empty_tags_action.setShortcut(QKeySequence('Ctrl+E'))
        remove_empty_tags_action.triggered.connect(
            self.remove_empty_tags)
        edit_menu.addAction(remove_empty_tags_action)

        view_menu = menu_bar.addMenu('View')
        self.toggle_toolbar_action.setCheckable(True)
        self.toggle_image_list_action.setCheckable(True)
        self.toggle_image_tags_editor_action.setCheckable(True)
        self.toggle_all_tags_editor_action.setCheckable(True)
        self.toggle_auto_captioner_action.setCheckable(True)
        self.toggle_auto_markings_action.setCheckable(True)
        self.toggle_toolbar_action.triggered.connect(
            lambda is_checked: self.toolbar.setVisible(is_checked))
        self.toggle_image_list_action.triggered.connect(
            lambda is_checked: self.image_list.setVisible(is_checked))
        self.toggle_image_tags_editor_action.triggered.connect(
            lambda is_checked: self.image_tags_editor.setVisible(is_checked))
        self.toggle_all_tags_editor_action.triggered.connect(
            lambda is_checked: self.all_tags_editor.setVisible(is_checked))
        self.toggle_auto_captioner_action.triggered.connect(
            lambda is_checked: self.auto_captioner.setVisible(is_checked))
        self.toggle_auto_markings_action.triggered.connect(
            lambda is_checked: self.auto_markings.setVisible(is_checked))
        view_menu.addAction(self.toggle_toolbar_action)
        view_menu.addAction(self.toggle_image_list_action)
        view_menu.addAction(self.toggle_image_tags_editor_action)
        view_menu.addAction(self.toggle_all_tags_editor_action)
        view_menu.addAction(self.toggle_auto_captioner_action)
        view_menu.addAction(self.toggle_auto_markings_action)

        help_menu = menu_bar.addMenu('Help')
        open_github_repository_action = QAction('GitHub', parent=self)
        open_github_repository_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(GITHUB_REPOSITORY_URL)))
        help_menu.addAction(open_github_repository_action)

    @Slot()
    def update_undo_and_redo_actions(self):
        if self.image_list_model.undo_stack:
            undo_action_name = self.image_list_model.undo_stack[-1].action_name
            self.undo_action.setText(f'Undo "{undo_action_name}"')
            self.undo_action.setDisabled(False)
        else:
            self.undo_action.setText('Undo')
            self.undo_action.setDisabled(True)
        if self.image_list_model.redo_stack:
            redo_action_name = self.image_list_model.redo_stack[-1].action_name
            self.redo_action.setText(f'Redo "{redo_action_name}"')
            self.redo_action.setDisabled(False)
        else:
            self.redo_action.setText('Redo')
            self.redo_action.setDisabled(True)

    @Slot()
    def set_image_list_filter(self):
        filter_ = self.image_list.filter_line_edit.parse_filter_text()
        self.proxy_image_list_model.set_filter(filter_)
        self.proxy_image_list_model.filter_changed.emit()
        if filter_ is None:
            all_tags_list_selection_model = (self.all_tags_editor
                                             .all_tags_list.selectionModel())
            all_tags_list_selection_model.clearSelection()
            # Clear the current index.
            self.all_tags_editor.all_tags_list.setCurrentIndex(QModelIndex())
            # Select the previously selected image in the unfiltered image
            # list.
            select_index = settings.value('image_index', type=int) or 0
            self.image_list.list_view.setCurrentIndex(
                self.proxy_image_list_model.index(select_index, 0))
        else:
            # Select the first image.
            self.image_list.list_view.setCurrentIndex(
                self.proxy_image_list_model.index(0, 0))

    @Slot()
    def save_image_index(self, proxy_image_index: QModelIndex):
        """Save the index of the currently selected image."""
        settings_key = ('image_index'
                        if self.proxy_image_list_model.filter is None
                        else 'filtered_image_index')
        settings.setValue(settings_key, proxy_image_index.row())

    def connect_toolbar_signals(self):
        self.toolbar.visibilityChanged.connect(
            lambda: self.toggle_toolbar_action.setChecked(
                self.toolbar.isVisible()))
        self.image_viewer.zoom.connect(self.zoom)
        self.zoom_fit_best_action.triggered.connect(
            self.image_viewer.zoom_fit)
        self.zoom_in_action.triggered.connect(
            self.image_viewer.zoom_in)
        self.zoom_original_action.triggered.connect(
            self.image_viewer.zoom_original)
        self.zoom_out_action.triggered.connect(
            self.image_viewer.zoom_out)
        self.add_action_group.triggered.connect(
            lambda action: self.image_viewer.add_marking(
                ImageMarking.NONE if not action.isChecked() else
                ImageMarking.CROP if action == self.add_crop_action else
                ImageMarking.HINT if action == self.add_hint_action else
                ImageMarking.EXCLUDE if action == self.add_exclude_action else
                ImageMarking.INCLUDE))
        self.image_viewer.marking.connect(lambda marking:
            self.add_crop_action.setChecked(True) if marking == ImageMarking.CROP else
            self.add_hint_action.setChecked(True) if marking == ImageMarking.HINT else
            self.add_exclude_action.setChecked(True) if marking == ImageMarking.EXCLUDE else
            self.add_include_action.setChecked(True) if marking == ImageMarking.INCLUDE else
            self.add_action_group.checkedAction() and
                self.add_action_group.checkedAction().setChecked(False))
        self.image_viewer.scene.selectionChanged.connect(lambda:
            self.is_running and self.add_toggle_marking_action.setEnabled(
                self.image_viewer.get_selected_type() not in [ImageMarking.NONE,
                                                              ImageMarking.CROP]))
        self.image_viewer.accept_crop_addition.connect(self.add_crop_action.setEnabled)
        self.image_viewer.scene.selectionChanged.connect(lambda:
            self.is_running and self.delete_marking_action.setEnabled(
                self.image_viewer.get_selected_type() != ImageMarking.NONE))
        self.delete_marking_action.triggered.connect(lambda: self.image_viewer.delete_markings())
        self.add_show_marking_action.toggled.connect(self.image_viewer.show_marking)
        self.add_show_marking_action.toggled.connect(self.add_action_group.setEnabled)
        self.add_show_marking_action.toggled.connect(lambda toggled:
                self.add_toggle_marking_action.setEnabled(toggled and
                    self.image_viewer.get_selected_type() != ImageMarking.NONE))
        self.add_show_marking_action.toggled.connect(self.add_show_labels_action.setEnabled)
        self.add_show_marking_action.toggled.connect(self.add_show_marking_latent_action.setEnabled)
        self.add_toggle_marking_action.triggered.connect(lambda: self.image_viewer.change_marking())
        self.add_show_labels_action.toggled.connect(self.image_viewer.show_label)
        self.add_show_marking_latent_action.toggled.connect(self.image_viewer.show_marking_latent)

    @Slot(float)
    def set_rating(self, rating: float, interactive: bool = False,
                   event: QMouseEvent|None = None):
        """Set the rating from 0.0 to 1.0.

        In the future, half-stars '⯪' might be included, but right now it's
        causing display issues."""
        if event is not None and (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier:
            # don't set the image but instead the filter
            is_shift = (event.modifiers() & Qt.ShiftModifier) == Qt.ShiftModifier
            stars = f'stars:{'>=' if is_shift else '='}{round(rating*5)}'
            self.image_list.filter_line_edit.setText(stars)
            return

        if interactive and rating == 2.0/10.0 and self.rating == rating:
            rating = 0.0
        self.rating = rating
        for i, label in enumerate(self.star_labels):
            label.setEnabled(True)
            label.setText('★' if 2*i+1 < 10.0*rating else '☆')
        if interactive:
            self.image_list_model.add_to_undo_stack(
                action_name='Change rating', should_ask_for_confirmation=False)
            self.image_viewer.rating_change(rating)
            self.proxy_image_list_model.set_filter(self.proxy_image_list_model.filter)

    def connect_image_list_signals(self):
        self.image_list.filter_line_edit.textChanged.connect(
            self.set_image_list_filter)
        self.image_list_selection_model.currentChanged.connect(
            self.save_image_index)
        self.image_list_selection_model.currentChanged.connect(
            self.image_list.update_image_index_label)
        self.image_list_selection_model.currentChanged.connect(
            lambda current, previous: self.image_viewer.load_image(current))
        self.image_list_selection_model.currentChanged.connect(
            self.image_tags_editor.load_image_tags)
        self.image_list_model.modelReset.connect(
            lambda: self.tag_counter_model.count_tags(
                self.image_list_model.images))
        self.image_list_model.dataChanged.connect(
            lambda: self.tag_counter_model.count_tags(
                self.image_list_model.images))
        self.image_list_model.dataChanged.connect(
            self.image_tags_editor.reload_image_tags_if_changed)
        self.image_list_model.dataChanged.connect(
            lambda start, end, roles:
                self.image_viewer.load_image(self.image_viewer.proxy_image_index,
                                             False)
                if (start.row() <= self.image_viewer.proxy_image_index.row() <= end.row()) else 0)
        self.image_list_model.update_undo_and_redo_actions_requested.connect(
            self.update_undo_and_redo_actions)
        self.proxy_image_list_model.filter_changed.connect(
            lambda: self.image_list.update_image_index_label(
                self.image_list.list_view.currentIndex()))
        self.proxy_image_list_model.filter_changed.connect(
            lambda: self.tag_counter_model.count_tags_filtered(
                self.proxy_image_list_model.get_list() if
                len(self.proxy_image_list_model.filter or [])>0 else None))
        self.image_list.list_view.directory_reload_requested.connect(
            self.reload_directory)
        self.image_list.list_view.tags_paste_requested.connect(
            self.image_list_model.add_tags)
        # Connecting the signal directly without `isVisible()` causes the menu
        # item to be unchecked when the widget is an inactive tab.
        self.image_list.visibilityChanged.connect(
            lambda: self.toggle_image_list_action.setChecked(
                self.image_list.isVisible()))
        self.image_viewer.crop_changed.connect(self.image_list.list_view.show_crop_size)

    @Slot()
    def update_image_tags(self):
        image_index = self.image_tags_editor.image_index
        image: Image = self.image_list_model.data(image_index,
                                                  Qt.ItemDataRole.UserRole)
        old_tags = image.tags
        new_tags = self.image_tag_list_model.stringList()
        if old_tags == new_tags:
            return
        old_tags_count = len(old_tags)
        new_tags_count = len(new_tags)
        if new_tags_count > old_tags_count:
            self.image_list_model.add_to_undo_stack(
                action_name='Add Tag', should_ask_for_confirmation=False)
        elif new_tags_count == old_tags_count:
            if set(new_tags) == set(old_tags):
                self.image_list_model.add_to_undo_stack(
                    action_name='Reorder Tags',
                    should_ask_for_confirmation=False)
            else:
                self.image_list_model.add_to_undo_stack(
                    action_name='Rename Tag',
                    should_ask_for_confirmation=False)
        elif old_tags_count - new_tags_count == 1:
            self.image_list_model.add_to_undo_stack(
                action_name='Delete Tag', should_ask_for_confirmation=False)
        else:
            self.image_list_model.add_to_undo_stack(
                action_name='Delete Tags', should_ask_for_confirmation=False)
        self.image_list_model.update_image_tags(image_index, new_tags)

    def connect_image_tags_editor_signals(self):
        # `rowsInserted` does not have to be connected because `dataChanged`
        # is emitted when a tag is added.
        self.image_tag_list_model.modelReset.connect(self.update_image_tags)
        self.image_tag_list_model.dataChanged.connect(self.update_image_tags)
        self.image_tag_list_model.rowsMoved.connect(self.update_image_tags)
        self.image_tags_editor.visibilityChanged.connect(
            lambda: self.toggle_image_tags_editor_action.setChecked(
                self.image_tags_editor.isVisible()))
        self.image_tags_editor.tag_input_box.tags_addition_requested.connect(
            self.image_list_model.add_tags)

    @Slot()
    def set_image_list_filter_text(self, selected_tag: str):
        """
        Construct and set the image list filter text from the selected tag in
        the all tags list.
        """
        escaped_selected_tag = (selected_tag.replace('\\', '\\\\')
                                .replace('"', r'\"').replace("'", r"\'"))
        self.image_list.filter_line_edit.setText(
            f'tag:"{escaped_selected_tag}"')

    @Slot(str)
    def add_tag_to_selected_images(self, tag: str):
        selected_image_indices = self.image_list.get_selected_image_indices()
        self.image_list_model.add_tags([tag], selected_image_indices)
        self.image_tags_editor.select_last_tag()

    def connect_all_tags_editor_signals(self):
        self.all_tags_editor.clear_filter_button.clicked.connect(
            self.image_list.filter_line_edit.clear)
        self.tag_counter_model.tags_renaming_requested.connect(
            self.image_list_model.rename_tags)
        self.tag_counter_model.tags_renaming_requested.connect(
            self.image_list.filter_line_edit.clear)
        self.all_tags_editor.all_tags_list.image_list_filter_requested.connect(
            self.set_image_list_filter_text)
        self.all_tags_editor.all_tags_list.tag_addition_requested.connect(
            self.add_tag_to_selected_images)
        self.all_tags_editor.all_tags_list.tags_deletion_requested.connect(
            self.image_list_model.delete_tags)
        self.all_tags_editor.all_tags_list.tags_deletion_requested.connect(
            self.image_list.filter_line_edit.clear)
        self.all_tags_editor.visibilityChanged.connect(
            lambda: self.toggle_all_tags_editor_action.setChecked(
                self.all_tags_editor.isVisible()))

    def connect_auto_captioner_signals(self):
        self.auto_captioner.caption_generated.connect(
            lambda image_index, _, tags:
            self.image_list_model.update_image_tags(image_index, tags))
        self.auto_captioner.caption_generated.connect(
            lambda image_index, *_:
            self.image_tags_editor.reload_image_tags_if_changed(image_index,
                                                                image_index))
        self.auto_captioner.visibilityChanged.connect(
            lambda: self.toggle_auto_captioner_action.setChecked(
                self.auto_captioner.isVisible()))

    def connect_auto_markings_signals(self):
        self.auto_markings.marking_generated.connect(
            lambda image_index, markings:
            self.image_list_model.add_image_markings(image_index, markings))
        self.auto_markings.visibilityChanged.connect(
            lambda: self.toggle_auto_markings_action.setChecked(
                self.auto_markings.isVisible()))

    def restore(self):
        # Restore the window geometry and state.
        if settings.contains('geometry'):
            self.restoreGeometry(settings.value('geometry', type=bytes))
        else:
            self.showMaximized()
        self.restoreState(settings.value('window_state', type=bytes))
        # Get the last index of the last selected image.
        if settings.contains('image_index'):
            image_index = settings.value('image_index', type=int)
        else:
            image_index = 0
        # Load the last loaded directory.
        if settings.contains('directory_path'):
            directory_path = Path(settings.value('directory_path',
                                                      type=str))
            if directory_path.is_dir():
                self.load_directory(directory_path, select_index=image_index)
