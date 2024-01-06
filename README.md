# TagGUI

<img src='images/icon.png' alt='TagGUI icon' width='128'>

Cross-platform desktop application for quickly adding and editing image tags,
aimed towards creators of image datasets for generative AI models like Stable
Diffusion.

<img src='images/screenshot-v1.9.0.png' alt='TagGUI screenshot' width='100%'>

## Features

- Keyboard-friendly interface for fast tagging
- Tag autocomplete based on your own most-used tags
- Integrated Stable Diffusion token counter
- Batch tag operations for renaming, deleting, and sorting tags
- Advanced image list filtering
- Automatic caption generation using LLaVA and BLIP-2

## Installation

The easiest way to use the application is to download the latest release from
the [releases page](https://www.github.com/jhc13/taggui/releases).
Choose the appropriate file for your operating system, extract it wherever you
want, and run the executable file inside.
You may have to install [7-Zip](https://www.7-zip.org/download.html) to
extract the files if you don't have it on your system.
No additional dependencies are required.

- macOS users: There is no macOS release because it requires a device running
  the OS, and I do not have one. You can still install and run the program
  manually (see below).
- Linux users: You may need to install `libxcb-cursor0`.
  See [this Stack Overflow answer](https://stackoverflow.com/a/75941575).

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
Panes can be resized, undocked, moved around, or placed on top of each
other to create a tabbed interface.

## Automatic Captioning

In addition to manual tagging, you can automatically generate captions for your
images inside TagGUI.
GPU generation requires a compatible NVIDIA GPU, and CPU generation is also
supported.

To use the feature, select the images you want to caption in the image list,
select the captioning model you want to use in the Auto-Captioner pane, and
click the `Run Auto-Captioner` button.
You can select a single image to get a caption for that image, or multiple
images to batch generate captions for all of them.
It can take up to several minutes to download and load a model when you first
use it, but subsequent generations will be much faster.

You can use the `Prompt` box to set the instructions given to the captioning
model.
You can also put some text inside the `Start caption with` box to make the
model generate captions that start with that text.
Additional generation parameters such as the minimum number of tokens and the
repetition penalty can be viewed and changed by clicking the
`Show Advanced Settings` button.
If you want to know more about what each parameter does, you can read the
[Hugging Face documentation](https://huggingface.co/docs/transformers/main/en/main_classes/text_generation#transformers.GenerationConfig).

## Advanced Image List Filtering

The basic functionality of filtering for images that contain a certain tag is
available by clicking on the tag in the `All Tags` pane.
In addition to this, you can construct more complex filters in
the `Filter Images` box at the top of the `Images` pane.

<details>
<summary>
Click here to see the full documentation for the filter syntax.
</summary>

### Filter criteria

These are the prefixes you can use to specify the filter criteria you want to
apply:

- `tag:`: Images that have the filter term as a tag
    - `tag:cat` will match images with the tag `cat`.
- `caption`: Images that contain the filter term in the caption
    - The caption is the list of tags as a single string, as it appears in the
      `.txt` file.
    - `caption:cat` will match images that have `cat` anywhere in the
      caption. For example, images with the tag `orange cat` or the
      tag `catastrophe`.
- `name`: Images that contain the filter term in the file name
    - `name:cat` will match images such as `cat-1.jpg` or `large_cat.png`.
- `path`: Images that contain the filter term in the full file path
    - `path:cat` will match images such as `C:\Users\cats\dog.jpg` or
      `/home/dogs/cat.jpg`.
- You can also use a filter term with no prefix to filter for images that
  contain the term in either the caption or the file path.
    - `cat` will match images containing `cat` in the caption or file path.

The following are prefixes for numeric filters. The operators `=` (`==` also
works), `!=`, `<`, `>`, `<=`, and `>=` are used to specify the type of
comparison.

- `tags`: Images that have the specified number of tags
    - `tags:=13` will match images that have exactly 13 tags.
    - `tags:!=7` will match images that do not have exactly 7 tags (images with
      less than 7 tags or more than 7 tags).
- `chars`: Images that have the specified number of characters in the caption
    - `chars:<100` will match images that have less than 100 characters in the
      caption.
    - `chars:>=30` will match images that have 30 or more characters in the
      caption.
- `tokens`: Images that have the specified number of tokens in the caption
    - `tokens:>75` will match images that have more than 75 tokens in the
      caption.
    - `tokens:<=50` will match images that have 50 or fewer tokens in the
      caption.

### Spaces and quotes

If the filter term contains spaces, you must enclose it in quotes (either
single or double quotes).
For example, to find images with the tag `orange cat`, you must
use `tag:"orange cat"` or `tag:'orange cat'`.
If you have both spaces and quotes in the filter term, you can escape the
quotes with backslashes.
For example, you can use `tag:"orange \"cat\""` for the tag `orange "cat"`.
An alternative is to use different types of quotes for the outer and inner
quotes, like so: `tag:'orange "cat"'`.

### Combining filters

Logical operators can be used to combine multiple filters:

- `NOT`: Images that do not match the filter
    - `NOT tag:cat` will match images that do not have the tag `cat`.
- `AND`: Images that match both filters before and after the operator
    - `tag:cat AND tag:orange` will match images that have both the tag `cat`
      and the tag `orange`.
- `OR`: Images that match either filter before or after the operator
    - `tag:cat OR tag:dog` will match images that have either the tag `cat` or
      the tag `dog`, or both.

The lowercase versions of these operators will also work: `not`, `and`,
and `or`.

The operator precedence is `NOT` > `AND` > `OR`, so by default, `NOT` will be
evaluated first, then `AND`, then `OR`.
You can use parentheses to change this order.
For example, in `tag:cat AND (tag:orange OR tag:white)`, the `OR` will be
evaluated first, matching images that have the tag `cat` and either the
tag `orange` or the tag `white`.
You can nest parentheses and operators to create arbitrarily complex filters.
</details>

## Controls

- Previous / next image: `Up` / `Down` arrow keys
- Jump to first untagged image: `Ctrl`+`J`
- Focus the `Filter Images` box: `Alt`+`F`
- Focus the image list: `Alt`+`L`
- Focus the `Add Tag` box: `Alt`+`A`
- Focus the `Search Tags` box: `Alt`+`S`
- Focus the `Run Auto-Captioner` button: `Alt`+`C`

### Images pane

- First / last image: `Home` / `End`
- Select multiple images: Hold `Ctrl` or `Shift` and click the images
- ⭐ Select all images: `Ctrl`+`A`
- Right-clicking on an image will bring up the context menu, which includes
  actions such as copying and pasting tags and moving or copying selected
  images to another directory.

### Image Tags pane

- Add a tag: Type the tag into the `Add Tag` box and press `Enter`
- ⭐ Add the first tag suggested by autocomplete: `Ctrl`+`Enter`
- Add a tag to multiple images: Select the images in the image list add
  the tag
- Delete a tag: Select the tag and press `Delete`
- Rename a tag: Double-click the tag, or select the tag and press `F2`
- Reorder tags: Drag and drop the tags
- Select multiple tags: Hold `Ctrl` or `Shift` and click the tags

### All Tags pane

- Show all images containing a tag: Select the tag
- Go back to showing all images: Click the `Clear Image Filter` button
- Delete all instances of a tag: Select the tag and press `Delete`
- Rename all instances of a tag: Double-click the tag, or select the tag and
  press `F2`
