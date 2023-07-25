# TagGUI

Cross-platform desktop application for quickly tagging images, aimed towards
creators of image datasets for generative AI.
Written in Python using PySide6.

## Features

- Keyboard-friendly interface for fast tagging
- Tag autocomplete based on your most used tags
- Integrated token counter
- Searchable list of all used tags
- Filter images by tag
- Rename or delete all instances of a tag
- Automatic dark mode based on system settings

## Installation

The easiest way to use the application is to download the latest release from
the [releases page](https://www.github.com/jhc13/taggui/releases).
Choose the appropriate executable file for your operating system.
The file can be run directly without any additional dependencies.

Alternatively, you can install manually by cloning this repository and
installing the dependencies in `requirements.txt`.
Run `taggui/run_gui.py` to start the program.
Python 3.11 is recommended, but Python 3.10 should also work.

## Usage

Load the directory containing your images by clicking the `Load Directory`
button in the center of the window (or `File` -> `Load Directory`).
Tags are loaded from `.txt` files in the directory with the same names as the
images.
Any changes you make to the tags are also automatically saved to these `.txt`
files.

You can change the settings in `File` -> `Settings`.
Panes can be resized, undocked, and moved around.

## Controls

### Images pane

- Previous / next image: `Up` / `Down` arrow keys
- First / last image: `Home` / `End`

### Image Tags pane

- Add a tag: Type the tag into the `Add Tag` box and press `Enter`
- Add the first tag suggested by autocomplete: Press `Ctrl`+`Enter`
- Delete a tag: Select the tag and press `Delete`
- Rename a tag: Double-click the tag, or select the tag and press `F2`
- Reorder tags: Drag and drop the tags
- Select multiple tags: Hold `Ctrl` or `Shift` while selecting the tags
- Previous / next image: `Up` / `Down` arrow keys while in the `Add Tag` box

### All Tags pane

- Show all images containing a tag: Select the tag
- Go back to showing all images: Click the `Clear Image Filter` button
- Delete all instances of a tag: Select the tag and press `Delete`
- Rename all instances of a tag: Double-click the tag, or select the tag and
  press `F2`
