from collections import defaultdict
import os
import io
from math import ceil, floor
from pathlib import Path
import shutil
import numpy as np

from PySide6.QtCore import QRect, QSize, Qt, Slot
from PySide6.QtGui import QColorSpace
from PySide6.QtWidgets import (QWidget, QDialog, QFileDialog, QGridLayout,
                               QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QProgressBar, QMessageBox,
                               QVBoxLayout, QHBoxLayout, QAbstractItemView)
from PIL import Image, ImageFilter, ImageCms

from utils.enums import (ExportFilter, Presets, MaskingStrategy, MaskedContent,
                         ExportFormat, ExportFormatDict, IccProfileList,
                         BucketStrategy, CaptionStrategy, HashNewlineHandling)
from utils.settings import DEFAULT_SETTINGS, settings
from utils.image import ImageMarking
from utils.settings_widgets import (SettingsBigCheckBox, SettingsLineEdit,
                                    SettingsSpinBox, SettingsComboBox)
import utils.target_dimension as target_dimension
from utils.grid import Grid
from widgets.image_list import ImageList

try:
    import pillow_jxl
except ModuleNotFoundError:
    pass


class ExportDialog(QDialog):
    def __init__(self, parent, image_list: ImageList):
        """
        Main method to create the export dialog.
        """
        super().__init__(parent)
        self.image_list = image_list
        self.inhibit_statistics_update = True
        self.setWindowTitle('Export')
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        grid_layout = QGridLayout()
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)

        grid_row = 0
        grid_layout.addWidget(QLabel('Image selection'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        preset_combo_box = SettingsComboBox(key='export_filter')
        preset_combo_box.addItems(list(ExportFilter))
        preset_combo_box.currentTextChanged.connect(self.show_statistics)
        grid_layout.addWidget(preset_combo_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Preset'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        preset_combo_box = SettingsComboBox(key='export_preset')
        preset_combo_box.addItems(list(Presets))
        preset_combo_box.currentTextChanged.connect(self.apply_preset)
        grid_layout.addWidget(preset_combo_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Resolution (px)'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        resolution_widget = QWidget()
        resolution_layout = QHBoxLayout()
        resolution_layout.setContentsMargins(0, 0, 0, 0)
        self.resolution_spin_box = SettingsSpinBox(
            key='export_resolution',
            minimum=0, maximum=8192)
        self.resolution_spin_box.setToolTip(
            'Common values:\n'
            '0: disable rescaling\n'
            '512: SD1.5\n'
            '1024: SDXL, SD3, Flux')
        self.resolution_spin_box.valueChanged.connect(self.show_megapixels)
        self.resolution_spin_box.valueChanged.connect(self.show_statistics)
        resolution_layout.addWidget(self.resolution_spin_box,
                                    Qt.AlignmentFlag.AlignLeft)

        resolution_layout.addWidget(QLabel('Image size (megapixel)'),
                                    Qt.AlignmentFlag.AlignRight)
        self.megapixels = QLabel('-')
        resolution_layout.addWidget(self.megapixels,
                                    Qt.AlignmentFlag.AlignLeft)
        resolution_widget.setLayout(resolution_layout)
        grid_layout.addWidget(resolution_widget, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Bucket resolution size (px)'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.bucket_res_size_spin_box = SettingsSpinBox(
            key='export_bucket_res_size',
            minimum=1, maximum=256)
        self.bucket_res_size_spin_box.setToolTip(
            'Ensure that the exported image size is divisable by that number.\n'
            'It should match the setting on the training tool.\n'
            'It might cause minor cropping.')
        self.bucket_res_size_spin_box.valueChanged.connect(self.show_statistics)
        grid_layout.addWidget(self.bucket_res_size_spin_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Latent size (px)'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        latent_widget = QWidget()
        latent_layout = QHBoxLayout()
        latent_layout.setContentsMargins(0, 0, 0, 0)
        self.latent_size_spin_box = SettingsSpinBox(
            key='export_latent_size',
            minimum=1, maximum=256)
        self.latent_size_spin_box.setToolTip(
            'Size of one latent space pixel in image space pixels')
        latent_layout.addWidget(self.latent_size_spin_box,
                                Qt.AlignmentFlag.AlignLeft)
        latent_layout.addWidget(QLabel('Quantize alpha channel'),
                                Qt.AlignmentFlag.AlignRight)
        self.quantize_alpha_check_box = SettingsBigCheckBox(key='export_quantize_alpha')
        self.quantize_alpha_check_box.setToolTip(
            'Align the masks due to include and exclude marking with the\n'
            'latent space pixels.\n'
            'Only available when the output format supports an alpha channel.')
        latent_layout.addWidget(self.quantize_alpha_check_box,
                              Qt.AlignmentFlag.AlignLeft)
        latent_widget.setLayout(latent_layout)
        grid_layout.addWidget(latent_widget, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Masking strategy'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        masking_widget = QWidget()
        masking_layout = QHBoxLayout()
        masking_layout.setContentsMargins(0, 0, 0, 0)
        self.masking_strategy_combo_box = SettingsComboBox(key='export_masking_strategy')
        self.masking_strategy_combo_box.addItems(list(MaskingStrategy))
        self.masking_strategy_combo_box.setToolTip(
            'Ignore the exclude masks, replace the content of the masks or\n'
            'remove it (make it transparent) when supported by the image format.')
        masking_layout.addWidget(self.masking_strategy_combo_box,
                                 Qt.AlignmentFlag.AlignLeft)
        masking_layout.addWidget(QLabel('Masked content'),
                                Qt.AlignmentFlag.AlignRight)
        self.masked_content_combo_box = SettingsComboBox(key='export_masked_content')
        self.masked_content_combo_box.addItems(list(MaskedContent))
        masking_layout.addWidget(self.masked_content_combo_box,
                              Qt.AlignmentFlag.AlignLeft)
        masking_widget.setLayout(masking_layout)
        grid_layout.addWidget(masking_widget, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Preferred sizes'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.preferred_sizes_line_edit = SettingsLineEdit(
            key='export_preferred_sizes')
        self.preferred_sizes_line_edit.setMinimumWidth(600)
        self.preferred_sizes_line_edit.setToolTip(
            'Comma separated list of preferred sizes and aspect ratios.\n'
            "The inverse aspect ratio is automatically derived and doesn't need to be included.")
        grid_layout.addWidget(self.preferred_sizes_line_edit, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Allow upscaling'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.upscaling_check_box = SettingsBigCheckBox(key='export_upscaling')
        self.upscaling_check_box.setToolTip(
            'Scale too small images to the requested size.\n'
            'This should be avoided as it lowers the image quality.')
        self.upscaling_check_box.stateChanged.connect(self.show_statistics)
        grid_layout.addWidget(self.upscaling_check_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Bucket fitting strategy'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        bucket_strategy_combo_box = SettingsComboBox(
            key='export_bucket_strategy')
        bucket_strategy_combo_box.addItems(list(BucketStrategy))
        bucket_strategy_combo_box.setToolTip(
            'crop: center crop\n'
            'scale: asymmetric scaling\n'
            'crop and scale: use both to minimize each effect')
        grid_layout.addWidget(bucket_strategy_combo_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Output format'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        format_widget = QWidget()
        format_layout = QHBoxLayout()
        format_layout.setContentsMargins(0, 0, 0, 0)
        self.format_combo_box = SettingsComboBox(key='export_format')
        supported_extensions = set(Image.registered_extensions().keys())
        supported_formats = [
            format for format in ExportFormat
            if any(ext in supported_extensions for ext in format.value.split(' - ')[0].split(','))
        ]
        self.format_combo_box.addItems(supported_formats)
        self.format_combo_box.currentTextChanged.connect(self.format_change)
        format_layout.addWidget(self.format_combo_box,
                              Qt.AlignmentFlag.AlignLeft)
        format_layout.addWidget(QLabel('Quality'),
                              Qt.AlignmentFlag.AlignRight)
        self.quality_spin_box = SettingsSpinBox(
            key='export_quality',
            minimum=0, maximum=100)
        self.quality_spin_box.setToolTip(
            'Only for JPEG and WebP.\n'
            '0 is worst and 100 is best.\n'
            'For JPEG numbers above 95 should be avoided')
        self.quality_spin_box.valueChanged.connect(self.quality_change)
        format_layout.addWidget(self.quality_spin_box,
                              Qt.AlignmentFlag.AlignLeft)
        format_widget.setLayout(format_layout)
        grid_layout.addWidget(format_widget, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)
        # ensure correct enable/disable and background color of the quality
        current_format = settings.value('export_format', type=str)
        current_quality = settings.value('export_quality', type=int)
        self.format_change(current_format, False)
        self.quality_change(current_quality)

        grid_row += 1
        grid_layout.addWidget(QLabel('Output color space'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        color_space_combo_box = SettingsComboBox(key='export_color_space')
        color_space_combo_box.addItem("feed through (don't touch)")
        color_space_combo_box.addItem('sRGB (implicit, without profile)')
        color_space_combo_box.addItems([IccProfileList[e.name] for e in QColorSpace.NamedColorSpace])
        color_space_combo_box.setToolTip(
            'Color space of the exported images.\n'
            'Most likely the trainer expects sRGB!\n'
            '\n'
            'Use "feed through" to keep the color space as it is.\n'
            'Use "sRGB (implicit, without profile)" to save in sRGB but don\'t embed the ICC profile to save 8k file size.')
        grid_layout.addWidget(color_space_combo_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Caption'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        caption_algorithm_combo_box = SettingsComboBox(key='export_caption_algorithm')
        caption_algorithm_combo_box.addItems(list(CaptionStrategy))
        caption_algorithm_combo_box.setToolTip(
            'Define how the tags should be exported:\n'
            'tag list - just like the tag text files\n'
            'only first tag, only last tag - only this one tag\n'
            'enumeration - natural language list with commas\n'
            'prefixed enumeration - first tag directly followed by enumeration')
        grid_layout.addWidget(caption_algorithm_combo_box, grid_row, 1,
                                           Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Fiter hashtag (#) tags'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        caption_hashtag_widget = QWidget()
        caption_hashtag_layout = QHBoxLayout()
        caption_hashtag_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_hashtag_check_box = SettingsBigCheckBox(key='export_filter_hashtag')
        self.filter_hashtag_check_box.setToolTip(
            'Do not export tags that start with a hashtag (#)')
        caption_hashtag_layout.addWidget(self.filter_hashtag_check_box,
                                         Qt.AlignmentFlag.AlignLeft)
        self.separate_newline_combo_box = SettingsComboBox(key='export_separate_newline')
        self.separate_newline_combo_box.addItems(list(HashNewlineHandling))
        self.separate_newline_combo_box.setToolTip(
            'Create a multi-caption file where each line contains a caption for\n'
            'the image. The tags are split by the tag "#newline" and the\n'
            'captioning algorith is used for each group. Only for prefixed\n'
            'enumeration the first tag is used repeatedly for each group.')
        caption_hashtag_layout.addWidget(QLabel('Handle #newline'),
                                           Qt.AlignmentFlag.AlignRight)
        caption_hashtag_layout.addWidget(self.separate_newline_combo_box,
                                         Qt.AlignmentFlag.AlignLeft)
        caption_hashtag_widget.setLayout(caption_hashtag_layout)
        grid_layout.addWidget(caption_hashtag_widget, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Export directory'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.export_directory_line_edit = SettingsLineEdit(
            key='export_directory_path')
        self.export_directory_line_edit.setMinimumWidth(600)
        self.export_directory_line_edit.setClearButtonEnabled(True)
        grid_layout.addWidget(self.export_directory_line_edit, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        export_directory_button = QPushButton('Select Directory...')
        export_directory_button.clicked.connect(self.set_export_directory_path)
        grid_layout.addWidget(export_directory_button, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Keep input directory structure'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        keep_dir_structure_check_box = SettingsBigCheckBox(
            key='export_keep_dir_structure')
        keep_dir_structure_check_box.setToolTip(
            'Keep the subdirectory structure or export\n'
            'all images in the same export directory')
        grid_layout.addWidget(keep_dir_structure_check_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Statistics'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.statistics_table = QTableWidget(0, 5, self)
        self.statistics_table.setHorizontalHeaderLabels(
            ['Width', 'Height', 'Count', 'Aspect ratio', 'Size utilization'])
        self.statistics_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.statistics_table.setMinimumWidth(600)
        self.statistics_table.setMinimumHeight(100)
        self.statistics_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.statistics_table.itemDoubleClicked.connect(self.set_filter)
        grid_layout.addWidget(self.statistics_table, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        self.layout.addLayout(grid_layout)

        self.export_button = QPushButton('Export')
        self.export_button.clicked.connect(self.do_export)
        self.export_button.setEnabled(False)
        self.layout.addWidget(self.export_button)

        image_list = self.get_image_list()
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(len(image_list))
        self.progress_bar.hide()
        self.layout.addWidget(self.progress_bar)

        # update display
        self.apply_preset(preset_combo_box.currentText(), False)
        self.show_megapixels()
        self.inhibit_statistics_update = False
        self.show_statistics()

    @Slot()
    def apply_preset(self, value: str, do_value_change: bool = True):
        """
        Slot to call when a new preset was selected to help the user to set
        important settings to a consistent state.
        """
        inhibit_statistics_update_current = self.inhibit_statistics_update
        preset = Presets[value]
        if value == 'manual':
            self.resolution_spin_box.setEnabled(True)
            self.bucket_res_size_spin_box.setEnabled(True)
            self.latent_size_spin_box.setEnabled(True)
        else:
            self.inhibit_statistics_update = True
            if do_value_change:
                self.resolution_spin_box.setValue(preset[0])
                self.bucket_res_size_spin_box.setValue(preset[1])
                self.latent_size_spin_box.setValue(preset[2])
            self.resolution_spin_box.setEnabled(False)
            self.bucket_res_size_spin_box.setEnabled(False)
            self.latent_size_spin_box.setEnabled(False)
        self.preferred_sizes_line_edit.setText(preset[3]) if do_value_change else 0
        self.inhibit_statistics_update = inhibit_statistics_update_current
        self.show_statistics()

    @Slot()
    def show_megapixels(self):
        """
        Slot to call when the resolution was changes to update the megapixel
        display.
        """
        resolution = self.resolution_spin_box.value()
        if resolution > 0:
            megapixels = resolution * resolution / 1024 / 1024
            self.megapixels.setText(f'{megapixels:.3f}')
        else:
            self.megapixels.setText('-')

    @Slot()
    def format_change(self, export_format: ExportFormat, do_value_change: bool = True):
        """
        Slot to call when the export format was changed.
        """
        replace_mask_item = self.masking_strategy_combo_box.model().item(2)
        if export_format == ExportFormat.JPG:
            self.quality_spin_box.setValue(75) if do_value_change else 0
            self.quality_spin_box.setEnabled(True)
            self.quantize_alpha_check_box.setEnabled(False)
            if self.masking_strategy_combo_box.currentIndex() == 2:
                self.masking_strategy_combo_box.setCurrentIndex(1)
            replace_mask_item.setFlags(replace_mask_item.flags() & ~Qt.ItemIsEnabled)
        if export_format == ExportFormat.JPGXL:
            self.quality_spin_box.setValue(100) if do_value_change else 0
            self.quality_spin_box.setEnabled(True)
            self.quantize_alpha_check_box.setEnabled(True)
            replace_mask_item.setFlags(replace_mask_item.flags() | Qt.ItemIsEnabled)
        elif export_format == ExportFormat.PNG:
            self.quality_spin_box.setValue(100) if do_value_change else 0
            self.quality_spin_box.setEnabled(False)
            self.quantize_alpha_check_box.setEnabled(True)
            replace_mask_item.setFlags(replace_mask_item.flags() | Qt.ItemIsEnabled)
        elif export_format == ExportFormat.WEBP:
            self.quality_spin_box.setValue(80) if do_value_change else 0
            self.quality_spin_box.setEnabled(True)
            self.quantize_alpha_check_box.setEnabled(True)
            replace_mask_item.setFlags(replace_mask_item.flags() | Qt.ItemIsEnabled)

    @Slot()
    def quality_change(self, quality: str):
        """
        Slot to call when the export quality setting was changed.
        """
        if (self.format_combo_box.currentText() == ExportFormat.JPG) and int(quality) > 95:
            self.quality_spin_box.setStyleSheet('background: orange')
        else:
            self.quality_spin_box.setStyleSheet('')

    @Slot()
    def show_statistics(self):
        """
        Update the statistics table content.
        """
        if self.inhibit_statistics_update:
            return

        resolution = settings.value('export_resolution', type=int)

        image_list = self.get_image_list()
        image_dimensions = defaultdict(int)
        for this_image in image_list:
            if this_image.crop is not None:
                this_image.target_dimension = target_dimension.get(
                    this_image.crop.size())
            else:
                this_image.target_dimension = target_dimension.get(
                    QSize(*this_image.dimensions))
            image_dimensions[this_image.target_dimension.toTuple()] += 1
        self.image_list.proxy_image_list_model.invalidate()

        sorted_dimensions = sorted(
                image_dimensions.items(),
                key=lambda x: x[0][0] / x[0][1]  # Sort by width/height ratio
            )
        self.export_button.setEnabled(len(image_list) > 0)

        self.statistics_table.setRowCount(0) # clear old data
        for dimensions, count in sorted_dimensions:
            width, height = dimensions
            aspect_ratio = width / height
            rowPosition = self.statistics_table.rowCount()
            ar = target_dimension.get_noteable_aspect_ratio(width, height)
            notable_aspect_ratio = f' ({ar[0]}:{ar[1]})' if ar is not None else ''
            utilization = (width * height)**0.5 / resolution if resolution > 0 else 1

            self.statistics_table.insertRow(rowPosition)
            self.statistics_table.setItem(rowPosition, 0, QTableWidgetItem(str(width)))
            self.statistics_table.setItem(rowPosition, 1, QTableWidgetItem(str(height)))
            self.statistics_table.setItem(rowPosition, 2, QTableWidgetItem(str(count)))
            self.statistics_table.setItem(rowPosition, 3, QTableWidgetItem(f'{aspect_ratio:.3f}{notable_aspect_ratio}'))
            self.statistics_table.setItem(rowPosition, 4, QTableWidgetItem(f'{100*utilization:.1f}%'))

    @Slot()
    def set_filter(self, selected_table_item: QTableWidgetItem):
        row = selected_table_item.row()
        width = self.statistics_table.model().index(row, 0).data()
        height = self.statistics_table.model().index(row, 1).data()
        add_filter = f'target:{width}:{height}'
        text = self.image_list.filter_line_edit.text().strip()
        if text != '':
            text = text if text.startswith('(') else f'({text})'
            self.image_list.filter_line_edit.setText(f'{add_filter} AND {text}')
        else:
            self.image_list.filter_line_edit.setText(add_filter)
        self.close()

    @Slot()
    def set_export_directory_path(self):
        """
        Set the path of the directory to export to.
        """
        export_directory_path = settings.value(
            'export_directory_path',
            defaultValue=DEFAULT_SETTINGS['export_directory_path'], type=str)
        if export_directory_path:
            initial_directory_path = export_directory_path
        elif settings.contains('directory_path'):
            initial_directory_path = settings.value('directory_path', type=str)
        else:
            initial_directory_path = ''
        export_directory_path = QFileDialog.getExistingDirectory(
            parent=self, caption='Select directory for image export',
            dir=initial_directory_path)
        if export_directory_path:
            self.export_directory_line_edit.setText(export_directory_path)

    @Slot()
    def do_export(self):
        """
        Export all images with the configured settings.
        """
        directory_path = settings.value('directory_path', type=str)
        export_directory_path = Path(settings.value('export_directory_path', type=str))
        export_keep_dir_structure = settings.value('export_keep_dir_structure', type=bool)
        no_overwrite = True
        only_missing = True
        refresh_tags = False

        try:
            if os.path.exists(export_directory_path):
                if os.path.isfile(export_directory_path):
                    QMessageBox.critical(
                        self,
                        'Path error',
                        'The export directory path points to a file and not to a directory'
                    )
                    return
                if os.listdir(export_directory_path):
                    msgBox = QMessageBox()
                    msgBox.setIcon(QMessageBox.Warning)
                    msgBox.setWindowTitle('Path warning')
                    msgBox.setText('The export directory path is not empty')
                    refresh_button = msgBox.addButton('Refresh', QMessageBox.ApplyRole)
                    refresh_button.setToolTip('Export only missing images, but update all captions')
                    overwrite_button = msgBox.addButton('Overwrite', QMessageBox.DestructiveRole)
                    overwrite_button.setToolTip('Overwrite all existing files')
                    rename_button = msgBox.addButton('Rename', QMessageBox.YesRole)
                    rename_button.setToolTip('Export with a new name')
                    only_missing_button = msgBox.addButton('Only missing', QMessageBox.AcceptRole)
                    only_missing_button.setToolTip('Export only missing images')
                    msgBox.addButton(QMessageBox.Cancel)
                    msgBox.setDefaultButton(refresh_button)
                    button = msgBox.exec_()
                    if button == QMessageBox.Cancel:
                        return
                    if msgBox.clickedButton() == refresh_button:
                        no_overwrite = False
                        refresh_tags = True
                    if msgBox.clickedButton() == overwrite_button:
                        no_overwrite = False
                        only_missing = False
                    if msgBox.clickedButton() == rename_button:
                        only_missing = False
            else:
                button = QMessageBox.critical(
                    self,
                    'Path error',
                    'The export directory path does not exist. Create it?',
                    QMessageBox.Ok, QMessageBox.Cancel)
                if button == QMessageBox.Cancel:
                    return
                os.makedirs(export_directory_path)
        except Exception as e:
            QMessageBox.critical(self, 'Path error', f'Error: {e}')
            return

        self.progress_bar.show()

        tag_separator = settings.value('tag_separator', type=str)
        if settings.value('insert_space_after_tag_separator', type=bool):
            tag_separator += ' '
        caption_algorithm = settings.value('export_caption_algorithm', type=str)
        separate_newline = settings.value('export_separate_newline', type=str)
        filter_hashtag = settings.value('export_filter_hashtag', type=bool)
        quantize_alpha = settings.value('export_quantize_alpha', type=bool)
        masking_strategy = settings.value('export_masking_strategy', type=str)
        masked_content = settings.value('export_masked_content', type=str)
        export_format = settings.value('export_format', type=str)
        quality = settings.value('export_quality', type=int)
        color_space = settings.value('export_color_space', type=str)
        save_profile = True
        if color_space == 'sRGB (implicit, without profile)':
            color_space = 'sRGB'
            save_profile = False

        if masking_strategy == MaskingStrategy.MASK_FILE:
            export_mask_directory_path = export_directory_path / 'mask'
            export_directory_path = export_directory_path / 'image'
        else:
            export_mask_directory_path = Path()

        image_list = self.get_image_list()
        self.progress_bar.setMaximum(len(image_list))
        for image_index, image_entry in enumerate(image_list):
            self.progress_bar.setValue(image_index)
            if export_keep_dir_structure:
                relative_path = image_entry.path.relative_to(directory_path)
                export_path = export_directory_path / relative_path
                export_mask_path = export_mask_directory_path / relative_path
            else:
                export_path = export_directory_path / image_entry.path.name
                export_mask_path = export_mask_directory_path / image_entry.path.name
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path = export_path.with_suffix(export_format.split(' ', 1)[0])
            if masking_strategy == MaskingStrategy.MASK_FILE:
                export_mask_path.parent.mkdir(parents=True, exist_ok=True)
                export_mask_path = export_mask_path.with_suffix(export_format.split(' ', 1)[0])
                mask_exists = export_mask_path.exists()
            else:
                mask_exists = False

            image_exists = export_path.exists()
            if (image_exists or mask_exists) and only_missing and not refresh_tags:
                continue

            if no_overwrite:
                stem = export_path.stem
                counter = 0
                while (image_exists or mask_exists):
                    export_path = export_path.parent / f'{stem}_{counter}{export_path.suffix}'
                    image_exists = export_path.exists()
                    if masking_strategy == MaskingStrategy.MASK_FILE:
                        export_mask_path = export_mask_path.parent / f'{stem}_{counter}{export_mask_path.suffix}'
                        mask_exists = export_mask_path.exists()
                    counter += 1

            # write the tag file first
            if filter_hashtag:
                tags = [tag for tag in image_entry.tags if tag[0] != '#' or
                        (separate_newline != HashNewlineHandling.IGNORE and
                         tag == '#newline')]
            else:
                tags = image_entry.tags.copy()

            if len(tags) == 0:
                tags = ['']

            if separate_newline:
                tag_groups = []
                temp_list = []
                for tag in tags:
                    if tag == '#newline':
                        if temp_list:
                            tag_groups.append(temp_list)
                            temp_list = []
                    else:
                        temp_list.append(tag)
                if temp_list:
                    tag_groups.append(temp_list)
            else:
                tag_groups = [tags]

            this_caption_algorithm = caption_algorithm
            if caption_algorithm == CaptionStrategy.PREFIX_ENUMERATION:
                prefix = tag_groups[0].pop(0) + ' '
                if len(tag_groups[0]) == 0:
                    tag_groups.pop(0)
                this_caption_algorithm = CaptionStrategy.ENUMERATION
            else:
                prefix = ''

            all_tags = []
            for tags in tag_groups:
                match this_caption_algorithm:
                    case  CaptionStrategy.TAG_LIST:
                        tag_string = tag_separator.join(tags)
                    case  CaptionStrategy.FIRST:
                        tag_string = tags[0]
                    case  CaptionStrategy.LAST:
                        tag_string = tags[-1]
                    case  CaptionStrategy.ENUMERATION:
                        if len(tags) == 1:
                            tag_string = tags[0]
                        elif len(tags) == 2:
                            tag_string = ' and '.join(tags)
                        else:
                            tag_string = ', '.join(tags[:-1]) + ', and ' + tags[-1]
                        tag_string = prefix + tag_string
                if tag_string != '':
                    all_tags.append(tag_string)

            try:
                if separate_newline != HashNewlineHandling.MULTIFILE:
                    multifile_count = None
                    export_path.with_suffix('.txt').write_text(
                        '\n'.join(all_tags), encoding='utf-8', errors='replace')
                else:
                    multifile_count = len(all_tags) or None
                    for index, this_tags in enumerate(all_tags):
                        suffix = '.txt' if index == 0 else f'.{index}.txt'
                        export_path.with_suffix(suffix).write_text(
                            this_tags, encoding='utf-8', errors='replace')

            except OSError:
                error_message_box = QMessageBox()
                error_message_box.setWindowTitle('Error')
                error_message_box.setIcon(QMessageBox.Icon.Critical)
                error_message_box.setText(f'Failed to save tags for {image_entry.path}.')
                error_message_box.exec()

            if  (image_exists or mask_exists) and only_missing:
                # tags were refreshed, export_path was changed when we should
                # rename and not overwrite, so we can skip the image writing
                continue

            # then handle the image
            image_file = Image.open(image_entry.path)
            export_can_alpha = export_format != ExportFormat.JPG
            export_mask = masking_strategy != MaskingStrategy.IGNORE
            # Preserve alpha if present:
            if image_file.mode in ('RGBA', 'LA', 'PA') and export_mask:  # Check for alpha channels
                image_file = image_file.convert('RGBA')
            else:
                image_file = image_file.convert('RGB')  # Otherwise, convert to RGB

            # 1. pass: add includes
            for marking in image_entry.markings:
                if marking.type == ImageMarking.INCLUDE and export_mask:
                    if image_file.mode == 'RGB':
                        image_file = image_file.convert('RGBA')
                        # completely transparent
                        alpha = Image.new('L', image_file.size, 0)
                    else:
                        alpha = image_file.getchannel('A')
                    if not quantize_alpha:
                        alpha.paste(255, marking.rect.adjusted(0,0,1,1).getCoords())
                    image_file.putalpha(alpha)

            # 2. pass: remove excludes
            for marking in image_entry.markings:
                if marking.type == ImageMarking.EXCLUDE and export_mask:
                    if image_file.mode == 'RGB':
                        image_file = image_file.convert('RGBA')
                        # completely opaque
                        alpha = Image.new('L', image_file.size, 255)
                    else:
                        alpha = image_file.getchannel('A')
                    if not quantize_alpha:
                        alpha.paste(0, marking.rect.adjusted(0,0,1,1).getCoords())
                    image_file.putalpha(alpha)

            if image_entry.crop is None:
                grid = Grid(QRect(0, 0, *image_file.size))
            else:
                grid = Grid(image_entry.crop)
            visible = grid.visible
            cropped_image = image_file.crop(visible.adjusted(0,0,1,1).getCoords())
            if not grid.is_visible_equal_screen_size():
                # resize with the best method available
                resized_image = cropped_image.resize(grid.target.toTuple(), Image.LANCZOS)
                # followed by a slight sharpening as it should be done
                sharpened_image = resized_image.filter(
                    ImageFilter.UnsharpMask(radius = 0.5, percent = 50, threshold = 0))
            else:
                sharpened_image = cropped_image

            # crop to the desired size
            current_width, current_height = sharpened_image.size
            crop_width = floor((current_width - image_entry.target_dimension.width()) / 2)
            crop_height = floor((current_height - image_entry.target_dimension.height()) / 2)
            cropped_image = sharpened_image.crop((crop_width, crop_height,
                                                 crop_width + image_entry.target_dimension.width(),
                                                 crop_height + image_entry.target_dimension.height()))

            if export_mask:
                if cropped_image.mode == 'RGB':
                    cropped_image = cropped_image.convert('RGBA')
                alpha = cropped_image.getchannel('A')
                if quantize_alpha:
                    for marking in image_entry.markings:
                        if marking.type == ImageMarking.INCLUDE:
                            rect = QRect(grid.map(marking.rect.topLeft(), ceil),
                                         grid.map(marking.rect.adjusted(0,0,1,1).bottomRight(), floor))
                            alpha.paste(255, rect.getCoords())
                    for marking in image_entry.markings:
                        if marking.type == ImageMarking.EXCLUDE:
                            rect = QRect(grid.map(marking.rect.topLeft(), floor),
                                         grid.map(marking.rect.adjusted(0,0,1,1).bottomRight(), ceil))
                            alpha.paste(0, rect.getCoords())

                replacement = None
                if masked_content in [MaskedContent.BLUR, MaskedContent.BLUR_NOISE]:
                    replacement = cropped_image.filter(ImageFilter.GaussianBlur(10))
                elif masked_content in [MaskedContent.GREY, MaskedContent.GREY_NOISE]:
                    # 126 is an 18% gray, i.e. the neutral gray, for sRGB.
                    # Anyway, it's masked, so there's no need to go into detail
                    # about different color spaces.
                    replacement = Image.new('RGB', cropped_image.size, (126, 126, 126))
                elif masked_content == MaskedContent.BLACK:
                    replacement = Image.new('RGB', cropped_image.size, (0, 0, 0))
                elif masked_content == MaskedContent.WHITE:
                    replacement = Image.new('RGB', cropped_image.size, (255, 255, 255))

                if masked_content in [MaskedContent.BLUR_NOISE, MaskedContent.GREY_NOISE]:
                    np_image = np.array(replacement)
                    # Add random noise with a minimal blur
                    noise = np.random.normal(0, 30, np_image.shape).astype(np.int8)
                    noisy_image = np_image + noise
                    noisy_image = np.clip(noisy_image, 0, 255).astype(np.uint8)
                    replacement = Image.fromarray(noisy_image).filter(ImageFilter.GaussianBlur(1))

                if replacement:
                    cropped_image = Image.composite(cropped_image, replacement, alpha)

                cropped_image.putalpha(alpha)

            if not export_can_alpha or masking_strategy in [MaskingStrategy.REPLACE,
                                                            MaskingStrategy.MASK_FILE]:
                # remove alpha
                export_image = cropped_image.convert('RGB')
            else:
                export_image = cropped_image

            lossless = quality > 99

            if color_space == "feed through (don't touch)":
                export_image.save(export_path, format=ExportFormatDict[export_format],
                                   quality=quality, lossless=lossless,
                                   icc_profile=export_image.info.get('icc_profile') )
            else:
                source_profile_raw = image_file.info.get('icc_profile')
                if source_profile_raw is None: # assume sRGB
                    source_profile_raw = QColorSpace(QColorSpace.SRgb).iccProfile()
                source_profile = ImageCms.ImageCmsProfile(io.BytesIO(source_profile_raw))
                target_profile_raw = QColorSpace(getattr(QColorSpace, IccProfileList(color_space).name)).iccProfile()
                target_profile = ImageCms.ImageCmsProfile(io.BytesIO(target_profile_raw))
                final_image = ImageCms.profileToProfile(export_image, source_profile, target_profile)
                if save_profile:
                    final_image.save(export_path, format=ExportFormatDict[export_format],
                                     quality=quality, lossless=lossless,
                                     icc_profile=target_profile.tobytes())
                else:
                    final_image.save(export_path, format=ExportFormatDict[export_format],
                                     quality=quality, lossless=lossless,
                                     icc_profile=None)
            if masking_strategy == MaskingStrategy.MASK_FILE:
                alpha_channel = cropped_image.getchannel('A')
                alpha_channel.save(export_mask_path, format=ExportFormatDict[export_format],
                                   quality=quality, lossless=lossless,
                                   icc_profile=None)

            if multifile_count is not None:
                for index in range(1, multifile_count):
                    suffix = f'.{index}{export_path.suffix}'
                    shutil.copy(export_path, export_path.with_suffix(suffix))
                    if masking_strategy == MaskingStrategy.MASK_FILE:
                        shutil.copy(export_mask_path, export_mask_path.with_suffix(suffix))
        self.close()

    def get_image_list(self):
        image_list_view = self.image_list.list_view
        if settings.value('export_filter') == ExportFilter.FILTERED:
            image_list = []
            for row in range(image_list_view.proxy_image_list_model.sourceModel().rowCount()):
                source_index = image_list_view.proxy_image_list_model.sourceModel().index(row, 0)
                proxy_index = image_list_view.proxy_image_list_model.mapFromSource(source_index)
                if proxy_index.isValid():
                    image_list.append(source_index.data(Qt.ItemDataRole.UserRole))
        elif settings.value('export_filter') == ExportFilter.SELECTED:
            image_list = [image_index.data(Qt.ItemDataRole.UserRole)
                          for image_index in image_list_view.get_selected_image_indices()]
        else: # ExportFilter.NONE
            images = image_list_view.proxy_image_list_model.sourceModel()
            image_list = [images.index(image_index).data(Qt.ItemDataRole.UserRole)
                          for image_index in range(images.rowCount())]

        return image_list
