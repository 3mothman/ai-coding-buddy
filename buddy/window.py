"""Startansicht und Lernansicht; Dateizugriff nur auf ausdrückliche Aktion."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QFileDialog, QMessageBox,
)
from .character import BuddyCharacter
from .editor import CodeEditor
from .session import LearningSession, read_reference

STYLE = """
QWidget { background: #101b2b; color: #edf3fa; font-family: 'Segoe UI'; font-size: 14px; }
QLabel#title { font-size: 30px; font-weight: 700; }
QLabel#subtitle { color: #a7b8ce; }
QPlainTextEdit { background: #0b1422; border: 1px solid #32445b; border-radius: 9px; padding: 12px; selection-background-color: #275c70; }
QPushButton { background: #23364e; border: 1px solid #36516f; border-radius: 8px; padding: 10px 17px; }
QPushButton:hover { background: #304963; }
QPushButton#primary { background: #72e5ca; color: #102838; font-weight: 700; }
QPushButton:disabled { background: #283441; color: #8793a1; }
QLabel#bubble { background: #21344b; border-radius: 14px; padding: 18px; }
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.session = LearningSession()
        self.setWindowTitle("AI Coding Buddy")
        self.resize(1080, 740)
        self.setMinimumSize(780, 580)
        self.setStyleSheet(STYLE)
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self.build_start()
        self.build_learning()
        action = QAction("Code speichern", self)
        action.setShortcut(QKeySequence.StandardKey.Save)
        action.triggered.connect(self.save_code)
        self.addAction(action)
        self.statusBar().showMessage("Phase 1 · Lokal · Keine KI-Verbindung")

    def label(self, text, name=None):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        if name:
            label.setObjectName(name)
        return label

    def build_start(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)
        layout.addWidget(self.label("AI Coding Buddy", "title"))
        layout.addWidget(self.label("Verstehen. Selbst schreiben. Schritt für Schritt.", "subtitle"))
        intro = QHBoxLayout()
        character = BuddyCharacter()
        character.setFixedSize(220, 230)
        intro.addWidget(character)
        intro.addWidget(self.label("Hallo! Ich bin dein Coding Buddy. Füge deine Referenzlösung ein – danach startest du mit einem leeren Editor.\n\nGrundversion: Meine Begrüßung ist ein festes Beispiel. Ich analysiere deinen Code noch nicht.", "bubble"), 1)
        layout.addLayout(intro)
        layout.addWidget(self.label("Aufgabenstellung (optional)"))
        self.task_input = QPlainTextEdit()
        self.task_input.setAccessibleName("Aufgabenstellung")
        self.task_input.setPlaceholderText("Was soll dein C-Programm lösen?")
        self.task_input.setMaximumHeight(85)
        layout.addWidget(self.task_input)
        layout.addWidget(self.label("Vollständige Referenzlösung"))
        self.reference_input = CodeEditor()
        self.reference_input.setAccessibleName("Referenzlösung")
        self.reference_input.setPlaceholderText("C-Lösung hier einfügen oder Datei importieren …")
        layout.addWidget(self.reference_input, 1)
        buttons = QHBoxLayout()
        import_button = QPushButton("Datei importieren …")
        import_button.clicked.connect(self.import_code)
        buttons.addWidget(import_button)
        buttons.addStretch()
        self.start_button = QPushButton("Start Learning")
        self.start_button.setObjectName("primary")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_learning)
        self.reference_input.textChanged.connect(
            lambda: self.start_button.setEnabled(bool(self.reference_input.toPlainText().strip())))
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)
        self.pages.addWidget(page)

    def build_learning(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(self.label("Deine Lösung. Dein nächster Schritt.", "title"))
        self.task_label = self.label("", "subtitle")
        layout.addWidget(self.task_label)
        toolbar = QHBoxLayout()
        for title, callback in [
            ("Neue Übung", self.new_exercise),
            ("Speichern …", self.save_code),
            ("Rückgängig", lambda: self.editor.undo()),
            ("Wiederholen", lambda: self.editor.redo()),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        content = QHBoxLayout()
        self.editor = CodeEditor()
        content.addWidget(self.editor, 3)
        sidebar = QWidget()
        sidebar.setMaximumWidth(300)
        right = QVBoxLayout(sidebar)
        right.addWidget(BuddyCharacter())
        right.addWidget(self.label("Du bist dran! Überlege zuerst, welche Bausteine deine Lösung braucht. Schreibe den ersten Schritt selbst.", "bubble"))
        right.addWidget(self.label("Beispielhinweis · Phase 1\nKI-Analyse, automatische Hinweise und Stimme folgen in späteren Phasen.", "subtitle"))
        right.addStretch()
        content.addWidget(sidebar, 1)
        layout.addLayout(content, 1)
        self.pages.addWidget(page)

    def import_code(self):
        path, _ = QFileDialog.getOpenFileName(self, "Referenzlösung importieren", "", "C- und Textdateien (*.c *.txt)")
        if not path:
            return
        try:
            text = read_reference(path)
        except (OSError, UnicodeError, ValueError) as error:
            QMessageBox.warning(self, "Import nicht möglich", str(error))
            return
        self.reference_input.setPlainText(text)

    def start_learning(self):
        reference = self.reference_input.toPlainText()
        if not reference.strip():
            return
        self.session = LearningSession(self.task_input.toPlainText().strip(), reference)
        self.task_label.setText(self.session.task or "Schreibe die Lösung eigenständig nach.")
        self.editor.clear()
        self.editor.document().setModified(False)
        self.pages.setCurrentIndex(1)
        self.editor.setFocus()

    def save_code(self):
        if self.pages.currentIndex() != 1:
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Eigenen Code speichern", "meine_loesung.c", "C-Dateien (*.c);;Textdateien (*.txt)")
        if not path:
            return False
        try:
            Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(self, "Speichern nicht möglich", str(error))
            return False
        self.editor.document().setModified(False)
        self.statusBar().showMessage("Eigener Code gespeichert. Referenzlösung bleibt im Arbeitsspeicher.")
        return True

    def may_discard(self):
        if not self.editor.document().isModified():
            return True
        answer = QMessageBox.question(
            self, "Ungespeicherter Code", "Möchtest du deinen Code vorher speichern?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_code()
        return answer == QMessageBox.StandardButton.Discard

    def new_exercise(self):
        if self.may_discard():
            self.session = LearningSession()
            self.editor.clear()
            self.editor.document().setModified(False)
            self.pages.setCurrentIndex(0)

    def closeEvent(self, event):
        if self.may_discard():
            event.accept()
        else:
            event.ignore()
