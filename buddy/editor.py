"""Schlichter Editor: bewusst keine automatische Codevervollständigung."""
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QPlainTextEdit

class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setAccessibleName("Eigener C-Code")
        self.setPlaceholderText("Hier beginnt deine eigene Lösung …")
