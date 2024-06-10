import git
import sys
from pathlib import Path

from PySide6.QtWidgets import QMessageBox


def get_resource_path(unbundled_resource_path: Path) -> Path:
    """
    Get the path to a resource, ensuring that it is valid even when the program
    is bundled with PyInstaller.
    """
    # PyInstaller stores the path to its temporary directory in `sys._MEIPASS`.
    base_path = getattr(sys, '_MEIPASS', Path(__file__).parent.parent.parent)
    resource_path = (Path(base_path) / unbundled_resource_path).resolve()
    return resource_path


def pluralize(word: str, count: int) -> str:
    if count == 1:
        return word
    return f'{word}s'


def list_with_and(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f'{items[0]} and {items[1]}'
    return ', '.join(items[:-1]) + f', and {items[-1]}'


def get_confirmation_dialog_reply(title: str, question: str) -> int:
    """Display a confirmation dialog and return the user's reply."""
    confirmation_dialog = QMessageBox()
    confirmation_dialog.setWindowTitle(title)
    confirmation_dialog.setIcon(QMessageBox.Icon.Question)
    confirmation_dialog.setText(question)
    confirmation_dialog.setStandardButtons(QMessageBox.StandardButton.Yes
                                           | QMessageBox.StandardButton.Cancel)
    confirmation_dialog.setDefaultButton(QMessageBox.StandardButton.Yes)
    return confirmation_dialog.exec()

def get_repo_infos(path: str) -> dict[str, str]:
    repo = git.Repo(path, search_parent_directories=True)
    app_origin = repo.remotes.origin.url
    app_revision = repo.head.commit.hexsha
    ret = { "app_origin": app_origin, "app_revision": app_revision }
    return ret
