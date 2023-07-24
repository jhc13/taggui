from PySide6.QtWidgets import QMessageBox


def pluralize(word: str, count: int):
    if count == 1:
        return word
    return f'{word}s'


def get_confirmation_dialog_reply(title: str,
                                  question: str) -> QMessageBox.StandardButton:
    """Display a confirmation dialog and return the user's reply."""
    confirmation_dialog = QMessageBox()
    confirmation_dialog.setWindowTitle(title)
    confirmation_dialog.setIcon(QMessageBox.Icon.Question)
    confirmation_dialog.setText(question)
    confirmation_dialog.setStandardButtons(QMessageBox.StandardButton.Yes
                                           | QMessageBox.StandardButton.Cancel)
    confirmation_dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
    return confirmation_dialog.exec()
