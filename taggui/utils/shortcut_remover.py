from PySide6.QtCore import QEvent, QKeyCombination, QObject
from PySide6.QtGui import QKeyEvent


class ShortcutRemover(QObject):
    """Event filter that removes keyboard shortcuts from a widget."""

    def __init__(self, parent, shortcuts: tuple[QKeyCombination, ...]):
        # A parent is required to avoid garbage collection.
        super().__init__(parent)
        self.shortcuts = shortcuts

    def eventFilter(self, _, event: QEvent) -> bool:
        if event.type() != QEvent.ShortcutOverride:
            return False
        event: QKeyEvent
        for shortcut in self.shortcuts:
            if event.keyCombination() == shortcut:
                return True
        return False
