from PySide6.QtCore import QEvent, QItemSelectionModel, Qt
from PySide6.QtWidgets import QFrame, QPlainTextEdit, QStyledItemDelegate


class TextEditItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        # Add some left padding.
        option.rect.adjust(4, 0, 0, 0)
        super().paint(painter, option, index)

    def createEditor(self, parent, option, index):
        editor = QPlainTextEdit(parent)
        editor.setFrameStyle(QFrame.Shape.NoFrame)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor.setStyleSheet('padding-left: 3px;')
        editor.index = index
        return editor

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(size.height() + 8)
        return size

    def eventFilter(self, editor, event: QEvent):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Return:
            self.commitData.emit(editor)
            self.closeEditor.emit(editor)
            self.parent().setCurrentIndex(
                self.parent().model().index(editor.index.row(), 0))
            self.parent().selectionModel().select(
                self.parent().model().index(editor.index.row(), 0),
                QItemSelectionModel.SelectionFlag.ClearAndSelect)
            self.parent().setFocus()
            return True
        # This is required to prevent crashing when the user clicks on another
        # tag in the All Tags list.
        if event.type() == QEvent.FocusOut:
            self.commitData.emit(editor)
            self.closeEditor.emit(editor)
            return True
        return False
