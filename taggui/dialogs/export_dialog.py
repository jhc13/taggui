from enum import Enum
from collections import defaultdict
import os
import io
from math import floor
from pathlib import Path
import shutil

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColorSpace
from PySide6.QtWidgets import (QWidget, QDialog, QFileDialog, QGridLayout,
                               QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QProgressBar, QMessageBox,
                               QVBoxLayout, QHBoxLayout, QSizePolicy,
                               QAbstractItemView)
from PIL import Image, ImageFilter, ImageCms

from utils.settings import DEFAULT_SETTINGS, settings
from utils.settings_widgets import (SettingsBigCheckBox, SettingsLineEdit,
                                    SettingsSpinBox, SettingsComboBox)
import utils.target_dimension as target_dimension
from widgets.image_list import ImageList

try:
    import pillow_jxl
except ModuleNotFoundError:
    pass

class ExportFilter(str, Enum):
    NONE = 'All images'
    FILTERED = 'Filtered images'
    SELECTED = 'Selected images'

Presets = {
    'manual': (0, 0, '1:1, 2:1, 3:2, 4:3, 16:9, 21:9'),
    'Direct feed through': (0, 1, '1:1, 2:1, 3:2, 4:3, 16:9, 21:9'),
    'SD1': (512, 64, '512:512, 640:320, 576:384, 512:384, 640:384, 768:320'),
    'SDXL, SD3, Flux': (1024, 64, '1024:1024, 1408:704, 1216:832, 1152:896, 1344:768, 1536:640')
}

class ExportFormat(str, Enum):
    JPG = '.jpg - JPEG'
    JPGXL = '.jxl - JPEG XL'
    PNG = '.png - PNG'
    WEBP = '.webp - WEBP'

ExportFormatDict = {
    ExportFormat.JPG: 'jpeg',
    ExportFormat.JPGXL: 'jxl',
    ExportFormat.PNG: 'png',
    ExportFormat.WEBP: 'webp'
}

class IccProfileList(str, Enum):
    SRgb = 'sRGB'
    SRgbLinear = 'sRGB (linear gamma)'
    AdobeRgb = 'AdobeRGB'
    DisplayP3 = 'DisplayP3'
    ProPhotoRgb = 'ProPhotoRGB'
    Bt2020 = 'BT.2020'
    Bt2100Pq = 'BT.2100(PQ)'
    Bt2100Hlg = 'BT.2100 (HLG)'

class BucketStrategy(str, Enum):
    CROP = 'crop'
    SCALE = 'scale'
    CROP_SCALE = 'crop and scale'

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
        self.resolution_spin_box = SettingsSpinBox(
            key='export_resolution',
            minimum=0, maximum=8192)
        self.resolution_spin_box.setToolTip(
            'Common values:\n'
            '0: disable rescaling\n'
            '512: SD1.5\n'
            '1024: SDXL, SD3, Flux')
        self.resolution_spin_box.textChanged.connect(self.show_megapixels)
        self.resolution_spin_box.textChanged.connect(self.show_statistics)
        grid_layout.addWidget(self.resolution_spin_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Image size (megapixel)'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.megapixels = QLabel('-')
        grid_layout.addWidget(self.megapixels, grid_row, 1,
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
        self.bucket_res_size_spin_box.textChanged.connect(self.show_statistics)
        grid_layout.addWidget(self.bucket_res_size_spin_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Preferred sizes'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.preferred_sizes_line_edit = SettingsLineEdit(
            key='export_preferred_sizes')
        self.preferred_sizes_line_edit.setMinimumWidth(500)
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
            'scale: assymetric scaling\n'
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
        self.quality_spin_box.textChanged.connect(self.quality_change)
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
        grid_layout.addWidget(QLabel('Export directory'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.export_directory_line_edit = SettingsLineEdit(
            key='export_directory_path')
        self.export_directory_line_edit.setMinimumWidth(500)
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
        self.statistics_table.setMinimumWidth(500)
        self.statistics_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.statistics_table.itemDoubleClicked.connect(self.set_filter)
        grid_layout.addWidget(self.statistics_table, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        self.layout.addLayout(grid_layout)

        self.export_button = QPushButton('Export')
        self.export_button.clicked.connect(self.do_export)
        self.export_button.setEnabled(False)
        self.layout.addWidget(self.export_button)

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
        else:
            self.inhibit_statistics_update = True
            self.resolution_spin_box.setValue(preset[0]) if do_value_change else 0
            self.resolution_spin_box.setEnabled(False)
            self.bucket_res_size_spin_box.setValue(preset[1]) if do_value_change else 0
            self.bucket_res_size_spin_box.setEnabled(False)
            self.inhibit_statistics_update = inhibit_statistics_update_current
            self.show_statistics()
        self.preferred_sizes_line_edit.setText(preset[2]) if do_value_change else 0

    @Slot()
    def show_megapixels(self):
        """
        Slot to call when the resolution was changes to update the megapixel
        display.
        """
        resolution = self.resolution_spin_box.value()
        if resolution > 0:
            megapixels = resolution * resolution / 1024 / 1024
            self.megapixels.setText(f"{megapixels:.3f}")
        else:
            self.megapixels.setText('-')

    @Slot()
    def format_change(self, export_format: ExportFormat, do_value_change: bool = True):
        """
        Slot to call when the export format was changed.
        """
        if export_format == ExportFormat.JPG:
            self.quality_spin_box.setValue(75) if do_value_change else 0
            self.quality_spin_box.setEnabled(True)
        if export_format == ExportFormat.JPGXL:
            self.quality_spin_box.setValue(100) if do_value_change else 0
            self.quality_spin_box.setEnabled(True)
        elif export_format == ExportFormat.PNG:
            self.quality_spin_box.setValue(100) if do_value_change else 0
            self.quality_spin_box.setEnabled(False)
        elif export_format == ExportFormat.WEBP:
            self.quality_spin_box.setValue(80) if do_value_change else 0
            self.quality_spin_box.setEnabled(True)

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
        upscaling = settings.value('export_upscaling', type=int)
        bucket_res = settings.value('export_bucket_res_size', type=int)

        # notable aspect ratios
        aspect_ratios = [
            (1, 1, 1),
            (2, 1, 2/1),
            (3, 2, 3/2),
            (4, 3, 4/3),
            (16, 9, 16/9),
            (21, 9, 21/9),
        ]
        aspect_ratios = target_dimension.prepare(aspect_ratios)

        image_list = self.get_image_list()
        image_dimensions = defaultdict(int)
        for this_image in image_list:
            this_image.target_dimensions = target_dimension.get(
                this_image.dimensions)
            image_dimensions[this_image.target_dimensions] += 1
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
            notable_aspect_ratio = ''
            for ar in aspect_ratios:
                if abs(ar[2] - aspect_ratio) < 1e-3:
                    notable_aspect_ratio = f" ({ar[0]}:{ar[1]})"
                elif abs(1/ar[2] - aspect_ratio) < 1e-3:
                    notable_aspect_ratio = f" ({ar[1]}:{ar[0]})"
            utilization = (width * height)**0.5 / resolution if resolution > 0 else 1

            self.statistics_table.insertRow(rowPosition)
            self.statistics_table.setItem(rowPosition, 0, QTableWidgetItem(str(width)))
            self.statistics_table.setItem(rowPosition, 1, QTableWidgetItem(str(height)))
            self.statistics_table.setItem(rowPosition, 2, QTableWidgetItem(str(count)))
            self.statistics_table.setItem(rowPosition, 3, QTableWidgetItem(f"{aspect_ratio:.3f}{notable_aspect_ratio}"))
            self.statistics_table.setItem(rowPosition, 4, QTableWidgetItem(f"{100*utilization:.1f}%"))

    @Slot()
    def set_filter(self, selected_table_item):
        row = selected_table_item.row()
        width = self.statistics_table.model().index(row, 0).data()
        height = self.statistics_table.model().index(row, 1).data()
        filter = f'target:{width}:{height}'
        text = self.image_list.filter_line_edit.text()
        if text != '':
            self.image_list.filter_line_edit.setText(f'{filter} AND ({text})')
        else:
            self.image_list.filter_line_edit.setText(filter)
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
            initial_directory_path = settings.value('directory_path')
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

        image_list = self.get_image_list()
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(len(image_list))
        self.layout.addWidget(self.progress_bar)

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
                overwrite_button = msgBox.addButton('Overwrite', QMessageBox.DestructiveRole)
                rename_button = msgBox.addButton('Rename', QMessageBox.YesRole)
                only_missing_button = msgBox.addButton('Only missing', QMessageBox.AcceptRole)
                msgBox.addButton(QMessageBox.Cancel)
                msgBox.setDefaultButton(QMessageBox.Cancel)
                button = msgBox.exec_()
                if button == QMessageBox.Cancel:
                    return
                if msgBox.clickedButton() == overwrite_button:
                    no_overwrite = False
                    only_missing = False
                if msgBox.clickedButton() == rename_button:
                    only_missing = False
        else:
            QMessageBox.critical(
                self,
                'Path error',
                'The export directory path does not exist'
            )
            return

        resolution = settings.value('export_resolution', type=int)
        upscaling = settings.value('export_upscaling', type=int)
        bucket_res = settings.value('export_bucket_res_size', type=int)
        export_format = settings.value('export_format', type=str)
        quality = settings.value('export_quality', type=int)
        color_space = settings.value('export_color_space', type=str)
        save_profile = True
        if color_space == 'sRGB (implicit, without profile)':
            color_space = 'sRGB'
            save_profile = False
        bucket_strategy = settings.value('export_bucket_strategy', type=str)

        for image_index, image_entry in enumerate(self.get_image_list()):
            self.progress_bar.setValue(image_index)
            if export_keep_dir_structure:
                relative_path = image_entry.path.relative_to(directory_path)
                export_path = export_directory_path / relative_path
                export_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                export_path = export_directory_path / image_entry.path.name
            export_path = export_path.with_suffix(export_format.split(' ', 1)[0])

            if export_path.exists() and only_missing:
                continue

            if no_overwrite:
                stem = export_path.stem
                counter = 0
                while export_path.exists():
                    export_path = export_path.parent / f"{stem}_{counter}{export_path.suffix}"
                    counter += 1

            # copy the tag file first
            if image_entry.path.with_suffix('.txt').exists():
                shutil.copyfile(str(image_entry.path.with_suffix('.txt')), str(export_path.with_suffix('.txt')))

            # then handle the image
            image_file = Image.open(image_entry.path)
            # Preserve alpha if present:
            if image_file.mode in ("RGBA", "LA", "PA") and not export_format == ExportFormat.JPG:  # Check for alpha channels
                image_file = image_file.convert("RGBA")
            else:
                image_file = image_file.convert("RGB")  # Otherwise, convert to RGB

            new_width, new_height = image_entry.target_dimensions
            current_width, current_height = image_file.size
            if bucket_strategy == BucketStrategy.CROP or bucket_strategy == BucketStrategy.CROP_SCALE:
                if current_height * new_width / current_width < new_height: # too wide
                    new_width = floor(current_width * new_height / current_height)
                else: # too high
                    new_height = floor(current_height * new_width / current_width)
            if bucket_strategy == BucketStrategy.CROP_SCALE:
                new_width = floor((image_entry.target_dimensions[0] + new_width)/2)
                new_height = floor((image_entry.target_dimensions[1] + new_height)/2)
            if image_file.size[0] != new_width or image_file.size[1] != new_height:
                # resize with the best method available
                resized_image = image_file.resize((new_width, new_height), Image.LANCZOS)
                # followed by a slight sharpening as it should be done
                sharpend_image = resized_image.filter(ImageFilter.UnsharpMask(radius = 0.5, percent = 50, threshold = 0))
            else:
                sharpend_image = image_file

            # crop to the desired size
            current_width, current_height = sharpend_image.size
            crop_width = floor((current_width - image_entry.target_dimensions[0]) / 2)
            crop_height = floor((current_height - image_entry.target_dimensions[1]) / 2)
            cropped_image = sharpend_image.crop((crop_width, crop_height, current_width - crop_width, current_height - crop_height))
            lossless = quality > 99

            if color_space == "feed through (don't touch)":
                cropped_image.save(export_path, format=ExportFormatDict[export_format], quality=quality, icc_profile=cropped_image.info.get('icc_profile'), lossless=lossless)
            else:
                source_profile_raw = image_file.info.get('icc_profile')
                if source_profile_raw is None: # assume sRGB
                    source_profile_raw = QColorSpace(QColorSpace.SRgb).iccProfile()
                source_profile = ImageCms.ImageCmsProfile(io.BytesIO(source_profile_raw))
                target_profile_raw = QColorSpace(getattr(QColorSpace, IccProfileList(color_space).name)).iccProfile()
                target_profile = ImageCms.ImageCmsProfile(io.BytesIO(target_profile_raw))
                final_image = ImageCms.profileToProfile(cropped_image, source_profile, target_profile)
                if save_profile:
                    final_image.save(export_path, format=ExportFormatDict[export_format], quality=quality, icc_profile=target_profile.tobytes(), lossless=lossless)
                else:
                    final_image.save(export_path, format=ExportFormatDict[export_format], quality=quality, icc_profile=None, lossless=lossless)
        self.close()

    def get_image_list(self):
        image_list_view = self.image_list.list_view
        if settings.value('export_filter') == ExportFilter.FILTERED:
            images = image_list_view.proxy_image_list_model.sourceModel()
            image_list = []
            for row in range(image_list_view.proxy_image_list_model.sourceModel().rowCount()):
                source_index = image_list_view.proxy_image_list_model.sourceModel().index(row, 0)
                proxy_index = image_list_view.proxy_image_list_model.mapFromSource(source_index)
                if proxy_index.isValid():
                    image_list.append(source_index.data(Qt.ItemDataRole.UserRole))
        elif settings.value('export_filter') == ExportFilter.SELECTED:
            images = image_list_view.proxy_image_list_model.sourceModel()
            image_list = [image_index.data(Qt.ItemDataRole.UserRole) for image_index in image_list_view.get_selected_image_indices()]
        else: # ExportFilter.NONE
            images = image_list_view.proxy_image_list_model.sourceModel()
            image_list = [images.index(image_index).data(Qt.ItemDataRole.UserRole) for image_index in range(images.rowCount())]

        return image_list
