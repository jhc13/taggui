from enum import Enum
from collections import defaultdict
import os
import io
import re
from math import floor, sqrt
from pathlib import Path
import shutil

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColorSpace
from PySide6.QtWidgets import (QWidget, QDialog, QFileDialog, QGridLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
                               QTableWidget, QTableWidgetItem, QSizePolicy,
                               QMessageBox)
from PIL import Image, ImageFilter, ImageCms

from utils.settings import DEFAULT_SETTINGS, get_settings
from utils.settings_widgets import (SettingsBigCheckBox, SettingsLineEdit,
                                    SettingsSpinBox, SettingsComboBox)
from models.image_list_model import ImageListModel

Presets = {
    'manual': (0, 0, '1:1, 2:1, 3:2, 4:3, 16:9, 21:9'),
    'Direct feed through': (0, 1, '1:1, 2:1, 3:2, 4:3, 16:9, 21:9'),
    'SD1': (512, 64, '512:512, 640:320, 576:384, 512:384, 640:384, 768:320'),
    'SDXL, SD3, Flux': (1024, 64, '1024:1024, 1408:704, 1216:832, 1152:896, 1344:768, 1536:640')
}

class ExportFormat(str, Enum):
    JPG = '.jpg - JPEG'
    PNG = '.png - PNG'
    WEBP = '.webp - WEBP'

ExportFormatDict = {
    ExportFormat.JPG: 'jpeg',
    ExportFormat.PNG: 'png',
    ExportFormat.WEBP: 'webp'
}

class IccProfileList(str, Enum):
    SRgb = 'sRGB'
    SRgbLinear = 'sRGB (linear gamma)'
    AdobeRgb = 'AdobeRGB'
    DisplayP3 = 'DisplayP3'
    ProPhotoRgb = 'ProPhotoRGB'
    # since PySide6.8:
    Bt2020 = 'BT.2020'
    Bt2100Pq = 'BT.2100(PQ)'
    Bt2100Hlg = 'BT.2100 (HLG)'

class BucketStrategy(str, Enum):
    CROP = 'crop'
    SCALE = 'scale'
    CROP_SCALE = 'crop and scale'

class ExportDialog(QDialog):
    def __init__(self, parent, image_list_model: ImageListModel):
        """
        Main method to create the export dialog.
        """
        super().__init__(parent)
        self.image_list_model = image_list_model
        self.settings = get_settings()
        self.inhibit_statistics_update = True
        self.resolution_cache: dict[tuple, tuple] = {}
        self.setWindowTitle('Export')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        grid_layout = QGridLayout()
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)

        grid_row = 0
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
            key='export_resolution', default=DEFAULT_SETTINGS['export_resolution'],
            minimum=0, maximum=8192)
        self.resolution_spin_box.setToolTip('Common values:\n'
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
            key='export_bucket_res_size', default=DEFAULT_SETTINGS['export_bucket_res_size'],
            minimum=1, maximum=256)
        self.bucket_res_size_spin_box.setToolTip('Ensure that the exported image size is divisable by that number.\n'
                                                 'It should match the setting on the training tool.\n'
                                                 'It might cause minor cropping.')
        self.bucket_res_size_spin_box.textChanged.connect(self.show_statistics)
        grid_layout.addWidget(self.bucket_res_size_spin_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Preferred sizes'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.preferred_sizes_line_edit = SettingsLineEdit(
            key='export_preferred_sizes',
            default=DEFAULT_SETTINGS['export_preferred_sizes'])
        self.preferred_sizes_line_edit.setMinimumWidth(500)
        self.preferred_sizes_line_edit.setToolTip('Comma separated list of preferred sizes and aspect ratios.\n'
                                                  "The inverse aspect ratio is automatically derived and doesn't need to be included.")
        grid_layout.addWidget(self.preferred_sizes_line_edit, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Allow upscaling'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.upscaling_check_box = SettingsBigCheckBox(
            key='export_upscaling',
            default=DEFAULT_SETTINGS['export_upscaling'])
        self.upscaling_check_box.setToolTip('Scale too small images to the requested size.\n'
                                    'This should be avoided as it lowers the image quality.')
        self.upscaling_check_box.stateChanged.connect(self.show_statistics)
        grid_layout.addWidget(self.upscaling_check_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Bucket fitting strategy'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        bucket_strategy_combo_box = SettingsComboBox(key='export_bucket_strategy')
        bucket_strategy_combo_box.addItems(list(BucketStrategy))
        bucket_strategy_combo_box.setToolTip('crop: center crop\n'
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
        current_format = self.settings.value('export_format', type=str)
        current_quality = self.settings.value('export_quality', type=str)
        self.format_combo_box = SettingsComboBox(key='export_format')
        self.format_combo_box.addItems(list(ExportFormat))
        self.format_combo_box.currentTextChanged.connect(self.format_change)
        format_layout.addWidget(self.format_combo_box,
                              Qt.AlignmentFlag.AlignLeft)
        format_layout.addWidget(QLabel('Quality'),
                              Qt.AlignmentFlag.AlignRight)
        self.quality_spin_box = SettingsSpinBox(
            key='export_quality', default=DEFAULT_SETTINGS['export_quality'],
            minimum=0, maximum=100)
        self.quality_spin_box.setToolTip('Only for JPEG and WebP.\n'
                                         '0 is worst and 100 is best.\n'
                                         'For JPEG numbers above 95 should be avoided')
        self.quality_spin_box.textChanged.connect(self.quality_change)
        format_layout.addWidget(self.quality_spin_box,
                              Qt.AlignmentFlag.AlignLeft)
        format_widget.setLayout(format_layout)
        grid_layout.addWidget(format_widget, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)
        # ensure correct enable/disable and background color of the quality
        self.format_change(current_format, False)
        self.quality_change(current_quality)

        grid_row += 1
        grid_layout.addWidget(QLabel('Output color space'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        color_space_combo_box = SettingsComboBox(key='export_color_space')
        color_space_combo_box.addItem("feed through (don't touch)")
        color_space_combo_box.addItem('sRGB (implicit, without profile)')
        color_space_combo_box.addItems([IccProfileList[e.name] for e in QColorSpace.NamedColorSpace])
        color_space_combo_box.setToolTip('Color space of the exported images.\n'
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
            key='export_directory_path',
            default=DEFAULT_SETTINGS['export_directory_path'])
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
            key='export_keep_dir_structure',
            default=DEFAULT_SETTINGS['export_keep_dir_structure'])
        keep_dir_structure_check_box.setToolTip('Keep the subdirectory structure or export\n'
                                                'all images in the same export directory')
        grid_layout.addWidget(keep_dir_structure_check_box, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        grid_row += 1
        grid_layout.addWidget(QLabel('Statistics'), grid_row, 0,
                              Qt.AlignmentFlag.AlignRight)
        self.statistics_table = QTableWidget(0, 5, self)
        self.statistics_table.setHorizontalHeaderLabels(['Width', 'Height', 'Count', 'Aspect ratio', 'Size utilization'])
        self.statistics_table.setMinimumWidth(500)
        grid_layout.addWidget(self.statistics_table, grid_row, 1,
                              Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(grid_layout)
        export_button = QPushButton('Export')
        export_button.clicked.connect(self.do_export)
        layout.addWidget(export_button)

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
            self.inhibit_statistics_update = False
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

        self.resolution_cache = {}
        resolution = self.resolution_spin_box.value()
        upscaling = self.upscaling_check_box.isChecked()
        bucket_res = self.bucket_res_size_spin_box.value()

        # notable aspect ratios
        aspect_ratios = [
            (1, 1, 1),
            (2, 1, 2/1),
            (3, 2, 3/2),
            (4, 3, 4/3),
            (16, 9, 16/9),
            (21, 9, 21/9),
        ]
        self.preferred_sizes = []
        for res_str in re.split(r'\s*,\s*', self.settings.value('export_preferred_sizes')):
            try:
                size_str = res_str.split(':')
                width = max(int(size_str[0]), int(size_str[1]))
                height = min(int(size_str[0]), int(size_str[1]))
                self.preferred_sizes.append((width, height))
                if not width == height:
                    self.preferred_sizes.append((height, width))
                # add exact aspect ratio of the preferred size to label it similar to the perfect one
                aspect_ratio = width / height
                for ar in aspect_ratios:
                    if abs(ar[2] - aspect_ratio) < 0.15:
                        aspect_ratios.append((ar[0], ar[1], aspect_ratio))
                        break
            except ValueError:
                # Handle cases where the resolution string is not in the correct format
                print(f"Warning: Invalid resolution format: {res_str}. Skipping.")
                continue # Skip to the next resolution if there's an error

        image_dimensions = defaultdict(int)
        for image_index in range(self.image_list_model.rowCount()):
            this_image = self.image_list_model.index(image_index).data(Qt.ItemDataRole.UserRole)
            this_image.target_dimensions = self.target_dimensions(this_image.dimensions, resolution, upscaling, bucket_res)
            image_dimensions[this_image.target_dimensions] += 1

        sorted_dimensions = sorted(
                image_dimensions.items(),
                key=lambda x: x[0][0] / x[0][1]  # Sort by width/height ratio
            )

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

    def target_dimensions(self, dimensions: tuple[int, int], resolution: int, upscaling: bool, bucket_res: int):
        """
        Determine the dimensions of an image it should have when it is exported.

        Note: this gives the optimal answer and thus can be slower than the Kohya
        bucket algorithm.

        Parameters
        ----------
        dimensions : tuple[int, int]
            The width and height of the image
        resolution : int
            The target resolution of the AI model. The target image pixels
            will not exceed the square of this number
        upscaling : bool
            Is upscaling of images allowed?
        bucket_res : int
            The resolution of the buckets
        """
        width, height = dimensions
        if resolution == 0:
            # no rescale in this case, only cropping
            return ((width // bucket_res)*bucket_res, (height // bucket_res)*bucket_res)

        if width < bucket_res or height < bucket_res:
            # it doesn't make sense to use such a small image. But we shouldn't
            # patronize the user
            return dimensions

        if dimensions in self.resolution_cache:
            return self.resolution_cache[dimensions]

        preferred_sizes_bonus = 0.4 # reduce the loss by this factor

        max_pixels = resolution * resolution
        opt_width = resolution * sqrt(width/height)
        opt_height = resolution * sqrt(height/width)
        if not upscaling:
            opt_width = min(width, opt_width)
            opt_height = min(height, opt_height)

        # test 1, guaranteed to find a solution: shrink and crop
        # 1.1: exact width
        candidate_width = (opt_width // bucket_res) * bucket_res
        candidate_height = ((height * candidate_width / width) // bucket_res) * bucket_res
        loss = ((height * candidate_width / width) - candidate_height) * candidate_width
        if (candidate_width, candidate_height) in self.preferred_sizes:
            loss *= preferred_sizes_bonus
        # 1.2: exact height
        test_height = (opt_height // bucket_res) * bucket_res
        test_width = ((width * test_height / height) // bucket_res) * bucket_res
        test_loss = ((width * test_height / height) - test_width) * test_height
        if (test_height, test_width) in self.preferred_sizes:
            test_loss *= preferred_sizes_bonus
        if test_loss < loss:
            candidate_width = test_width
            candidate_height = test_height
            loss = test_loss

        # test 2, going bigger might still fit in the size budget due to cropping
        # 2.1: exact width
        for delta in range(1, 10):
            test_width = (opt_width // bucket_res + delta) * bucket_res
            test_height = ((height * test_width / width) // bucket_res) * bucket_res
            if test_width * test_height > max_pixels:
                break
            if (test_width > width or test_height > height) and not upscaling:
                break
            test_loss = ((height * test_width / width) - test_height) * test_width
            if (test_height, test_width) in self.preferred_sizes:
                test_loss *= preferred_sizes_bonus
            if test_loss < loss:
                candidate_width = test_width
                candidate_height = test_height
                loss = test_loss
        # 2.2: exact height
        for delta in range(1, 10):
            test_height = (opt_height // bucket_res + delta) * bucket_res
            test_width = ((width * test_height / height) // bucket_res) * bucket_res
            if test_width * test_height > max_pixels:
                break
            if (test_width > width or test_height > height) and not upscaling:
                break
            test_loss = ((width * test_height / height) - test_width) * test_height
            if (test_height, test_width) in self.preferred_sizes:
                test_loss *= preferred_sizes_bonus
            if test_loss < loss:
                candidate_width = test_width
                candidate_height = test_height
                loss = test_loss

        return int(candidate_width), int(candidate_height)

    @Slot()
    def set_export_directory_path(self):
        """
        Set the path of the directory to export to.
        """
        export_directory_path = self.settings.value(
            'export_directory_path',
            defaultValue=DEFAULT_SETTINGS['export_directory_path'], type=str)
        if export_directory_path:
            initial_directory_path = export_directory_path
        elif self.settings.contains('directory_path'):
            initial_directory_path = self.settings.value('directory_path')
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
        directory_path = self.settings.value('directory_path', type=str)
        export_directory_path = Path(self.settings.value('export_directory_path', type=str))
        export_keep_dir_structure = self.settings.value('export_keep_dir_structure', type=bool)
        no_overwrite = True
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
                overwrite_button = msgBox.addButton('Overwrite', QMessageBox.YesRole)
                rename_button = msgBox.addButton('Rename', QMessageBox.NoRole)
                msgBox.addButton(QMessageBox.Cancel)
                msgBox.setDefaultButton(QMessageBox.Cancel)
                button = msgBox.exec_()
                if button == QMessageBox.Cancel:
                    return
                if msgBox.clickedButton() == overwrite_button:
                    no_overwrite = False
        else:
            QMessageBox.critical(
                self,
                'Path error',
                'The export directory path does not exist'
            )
            return

        resolution = self.resolution_spin_box.value()
        upscaling = self.upscaling_check_box.isChecked()
        bucket_res = self.bucket_res_size_spin_box.value()
        export_format = self.format_combo_box.currentText()
        quality = self.quality_spin_box.value()
        color_space = self.settings.value('export_color_space', type=str)
        save_profile = True
        if color_space == 'sRGB (implicit, without profile)':
            color_space = 'sRGB'
            save_profile = False
        bucket_strategy = self.settings.value('export_bucket_strategy', type=str)

        for image_index in range(self.image_list_model.rowCount()):
            image_entry = self.image_list_model.index(image_index).data(Qt.ItemDataRole.UserRole)
            if export_keep_dir_structure:
                relative_path = image_entry.path.relative_to(directory_path)
                export_path = export_directory_path / relative_path
                export_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                export_path = export_directory_path / image_entry.path.name
            export_path = export_path.with_suffix(export_format.split(' ', 1)[0])

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
                sharpend_image = resized_image.filter(ImageFilter.UnsharpMask(radius = 0.5, percent = 100, threshold = 3))
            else:
                sharpend_image = image_file

            # crop to the desired size
            current_width, current_height = sharpend_image.size
            crop_width = floor((current_width - image_entry.target_dimensions[0]) / 2)
            crop_height = floor((current_height - image_entry.target_dimensions[1]) / 2)
            cropped_image = sharpend_image.crop((crop_width, crop_height, current_width - crop_width, current_height - crop_height))

            if color_space == "feed through (don't touch)":
                cropped_image.save(export_path, format=ExportFormatDict[export_format], quality=quality, icc_profile=cropped_image.info.get('icc_profile'))
            else:
                source_profile_raw = image_file.info.get('icc_profile')
                if source_profile_raw is None: # assume sRGB
                    source_profile_raw = QColorSpace(QColorSpace.SRgb).iccProfile()
                source_profile = ImageCms.ImageCmsProfile(io.BytesIO(source_profile_raw))
                target_profile_raw = QColorSpace(getattr(QColorSpace, IccProfileList(color_space).name)).iccProfile()
                target_profile = ImageCms.ImageCmsProfile(io.BytesIO(target_profile_raw))
                final_image = ImageCms.profileToProfile(cropped_image, source_profile, target_profile)
                if save_profile:
                    final_image.save(export_path, format=ExportFormatDict[export_format], quality=quality, icc_profile=target_profile.tobytes())
                else:
                    final_image.save(export_path, format=ExportFormatDict[export_format], quality=quality, icc_profile=None)
        self.close()
