"""Two simple views coordinating independent editor, tutor, speech and animation."""
from collections import Counter
from pathlib import Path
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QFileDialog, QMessageBox, QCheckBox,
    QLineEdit, QScrollArea, QDialog,
)
from .character import BuddyCharacter
from .editor import CodeEditor
from .session import LearningSession, read_reference
from .analysis import Snapshot, DemoTutor, ChatCompletionsTutor, concepts, issue_signature
from .controller import TutorController
from .settings import SettingsDialog, load_preferences, save_preferences
from .speech import SpeechService

STYLE = """
QWidget { background: #101b2b; color: #edf3fa; font-family: 'Segoe UI'; font-size: 14px; }
QLabel#title { font-size: 27px; font-weight: 700; }
QLabel#subtitle { color: #a7b8ce; }
QPlainTextEdit, QLineEdit { background: #0b1422; border: 1px solid #32445b; border-radius: 8px; padding: 8px; selection-background-color: #275c70; }
QPushButton { background: #23364e; border: 1px solid #36516f; border-radius: 8px; padding: 8px 12px; }
QPushButton:hover { background: #304963; }
QPushButton#primary { background: #72e5ca; color: #102838; font-weight: 700; }
QPushButton:disabled, QPushButton#primary:disabled { background: #283441; color: #8793a1; }
QLabel#bubble { background: #21344b; border-radius: 12px; padding: 14px; }
QCheckBox { spacing: 8px; }
QScrollArea { border: none; }
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.preferences = load_preferences()
        self.session = LearningSession()
        self.provider = DemoTutor()
        self.api_key = ""
        self.ai_enabled = False
        self.history = []
        self.recent_code = []
        self.plan = []
        self.level = 1
        self.last_message_time = -1000.0
        self.last_auto_code = None
        self.seen_concepts = set()
        self.issue_counts = Counter()
        self.last_issue = ""
        self.current_question = ""
        self.last_reason = ""
        self.controller = TutorController(self)
        self.controller.result.connect(self.receive_feedback)
        self.controller.failure.connect(self.receive_error)
        self.controller.busy_changed.connect(self.set_busy)
        self.speech = SpeechService(self)
        self.speech.set_enabled(self.preferences.sound)
        self.speech.unavailable.connect(self.speech_error)
        self.pause_timer = QTimer(self)
        self.pause_timer.setSingleShot(True)
        self.pause_timer.setInterval(25000)
        self.pause_timer.timeout.connect(self.idle_hint)
        self.progress_timer = QTimer(self)
        self.progress_timer.setSingleShot(True)
        self.progress_timer.setInterval(2000)
        self.progress_timer.timeout.connect(self.observe_progress)
        self.setWindowTitle("AI Coding Buddy")
        self.resize(1160, 820)
        self.setMinimumSize(850, 650)
        self.setStyleSheet(STYLE)
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self.build_start()
        self.build_learning()
        self.editor.textChanged.connect(self.code_changed)
        action = QAction("Save code", self)
        action.setShortcut(QKeySequence.StandardKey.Save)
        action.triggered.connect(self.save_code)
        self.addAction(action)
        self.update_mode()
        if not self.speech.available:
            self.speech_note.setText(self.speech.reason)

    def label(self, text, name=None):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        if name:
            label.setObjectName(name)
        return label

    def button(self, text, callback, layout):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def build_start(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)
        header = QHBoxLayout()
        header.addWidget(self.label("AI Coding Buddy", "title"), 1)
        self.button("AI settings", self.open_settings, header)
        layout.addLayout(header)
        layout.addWidget(self.label("Understand it. Write it yourself. One step at a time.", "subtitle"))
        intro = QHBoxLayout()
        robot = BuddyCharacter()
        robot.setFixedSize(210, 200)
        intro.addWidget(robot)
        intro.addWidget(self.label("Bring a reference solution. Start with a blank editor. Your buddy offers questions and small hints while you do the thinking.\n\nTry the offline demo, or connect your own AI provider in settings.", "bubble"), 1)
        layout.addLayout(intro)
        layout.addWidget(self.label("Task description (optional)"))
        self.task_input = QPlainTextEdit()
        self.task_input.setAccessibleName("Task description")
        self.task_input.setPlaceholderText("What should your C program do?")
        self.task_input.setMaximumHeight(80)
        layout.addWidget(self.task_input)
        layout.addWidget(self.label("Complete reference solution"))
        self.reference_input = CodeEditor()
        self.reference_input.setAccessibleName("Reference solution")
        self.reference_input.setPlaceholderText("Paste a C solution or import a .c / .txt file...")
        layout.addWidget(self.reference_input, 1)
        buttons = QHBoxLayout()
        self.button("Import file...", self.import_code, buttons)
        buttons.addStretch()
        self.start_button = self.button("Start Learning", self.start_learning, buttons)
        self.start_button.setObjectName("primary")
        self.start_button.setEnabled(False)
        self.reference_input.textChanged.connect(lambda: self.start_button.setEnabled(bool(self.reference_input.toPlainText().strip())))
        layout.addLayout(buttons)
        self.pages.addWidget(page)

    def build_learning(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(self.label("Your solution. Your next step.", "title"))
        self.task_label = self.label("", "subtitle")
        self.task_label.setMaximumHeight(65)
        layout.addWidget(self.task_label)
        toolbar = QHBoxLayout()
        for title, callback in [
            ("New exercise", self.new_exercise), ("Save...", self.save_code),
            ("Undo", lambda: self.editor.undo()), ("Redo", lambda: self.editor.redo()),
            ("AI settings", self.open_settings),
        ]:
            self.button(title, callback, toolbar)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        content = QHBoxLayout()
        self.editor = CodeEditor()
        content.addWidget(self.editor, 3)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(305)
        scroll.setMaximumWidth(370)
        sidebar = QWidget()
        right = QVBoxLayout(sidebar)
        self.character = BuddyCharacter()
        self.speech.speaking.connect(self.character.set_talking)
        right.addWidget(self.character)
        self.mode_label = self.label("", "subtitle")
        right.addWidget(self.mode_label)
        self.bubble = self.label("Ready when you are.", "bubble")
        right.addWidget(self.bubble)
        self.snippet = CodeEditor()
        self.snippet.setReadOnly(True)
        self.snippet.setMaximumHeight(155)
        self.snippet.hide()
        right.addWidget(self.snippet)
        self.hint_label = self.label("Hint level 1 of 4", "subtitle")
        right.addWidget(self.hint_label)
        row = QHBoxLayout()
        self.button("Help", self.request_help, row)
        self.button("More help", self.more_help, row)
        self.repeat_button = self.button("Repeat", self.speech.repeat, row)
        self.repeat_button.setEnabled(self.speech.available)
        right.addLayout(row)
        self.example_button = self.button("Show a small example", lambda: self.ask("example"), right)
        self.example_button.setEnabled(False)
        self.button("Check understanding", lambda: self.ask("question"), right)
        self.answer = QLineEdit()
        self.answer.setPlaceholderText("Your answer to the buddy's question")
        self.answer.setMaxLength(2000)
        self.answer.setAccessibleName("Answer to understanding question")
        self.answer.textChanged.connect(lambda: self.controller.invalidate())
        self.answer.returnPressed.connect(self.submit_answer)
        self.answer.hide()
        right.addWidget(self.answer)
        self.answer_button = self.button("Submit answer", self.submit_answer, right)
        self.answer_button.hide()
        self.button("Review my solution", lambda: self.ask("review"), right)
        self.auto_box = QCheckBox("Automatic hints")
        self.auto_box.setChecked(self.preferences.automatic)
        self.auto_box.toggled.connect(self.toggle_automatic)
        right.addWidget(self.auto_box)
        self.sound_box = QCheckBox("Sound")
        self.sound_box.setChecked(self.preferences.sound and self.speech.available)
        self.sound_box.setEnabled(self.speech.available)
        self.sound_box.toggled.connect(self.toggle_sound)
        right.addWidget(self.sound_box)
        self.speech_note = self.label("", "subtitle")
        right.addWidget(self.speech_note)
        self.review_label = self.label("", "subtitle")
        right.addWidget(self.review_label)
        right.addStretch()
        scroll.setWidget(sidebar)
        content.addWidget(scroll, 1)
        layout.addLayout(content, 1)
        self.pages.addWidget(page)

    def update_mode(self):
        mode = f"AI mode · {self.preferences.model}" if self.ai_enabled else "Demo mode · local rules, not AI"
        self.mode_label.setText(mode)
        self.statusBar().showMessage(mode)

    def persist_preferences(self):
        try:
            save_preferences(self.preferences)
        except OSError:
            self.statusBar().showMessage("Preferences could not be saved. They still apply for this session.")

    def open_settings(self):
        dialog = SettingsDialog(self.preferences, self.api_key, self.ai_enabled, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.controller.invalidate()
        self.speech.stop()
        self.preferences.endpoint = dialog.endpoint.text().strip()
        self.preferences.model = dialog.model.text().strip()
        self.api_key = dialog.key.text().strip()
        self.ai_enabled = dialog.consent.isChecked()
        self.provider = ChatCompletionsTutor(self.preferences.endpoint, self.preferences.model, self.api_key) if self.ai_enabled else DemoTutor()
        self.plan = []
        self.history = []
        self.recent_code = []
        self.current_question = ""
        self.answer.hide()
        self.answer_button.hide()
        self.review_label.clear()
        self.snippet.hide()
        self.persist_preferences()
        self.update_mode()
        if self.pages.currentIndex() == 1:
            self.show_message("Provider settings updated. Ask for a hint when you are ready.", "neutral")
            if self.auto_box.isChecked():
                self.pause_timer.start()

    def import_code(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import reference solution", "", "C and text files (*.c *.txt)")
        if path:
            try:
                self.reference_input.setPlainText(read_reference(path))
            except (OSError, UnicodeError, ValueError) as error:
                QMessageBox.warning(self, "Import failed", str(error))

    def start_learning(self):
        reference = self.reference_input.toPlainText()
        if not reference.strip():
            return
        self.controller.invalidate()
        self.session = LearningSession(self.task_input.toPlainText().strip(), reference)
        self.task_label.setText(self.session.task or "Reconstruct the solution in your own way.")
        self.task_label.setToolTip(self.session.task)
        self.editor.clear()
        self.editor.document().setModified(False)
        self.history, self.plan = [], []
        self.recent_code = []
        self.level = 1
        self.seen_concepts = set()
        self.issue_counts.clear()
        self.last_issue = ""
        self.last_auto_code = None
        self.current_question = ""
        self.answer.clear()
        self.answer.hide()
        self.answer_button.hide()
        self.review_label.clear()
        self.snippet.hide()
        self.example_button.setEnabled(False)
        self.hint_label.setText("Hint level 1 of 4")
        self.pages.setCurrentIndex(1)
        self.editor.setFocus()
        self.show_message("Let's begin! What are the inputs and the expected output?", "neutral")
        self.ask("start")

    def code_changed(self):
        self.controller.invalidate()
        self.speech.stop()
        self.snippet.hide()
        self.review_label.clear()
        self.current_question = ""
        self.answer.hide()
        self.answer_button.hide()
        if self.pages.currentIndex() == 1:
            self.character.set_state("neutral")
            self.progress_timer.start()
            if self.auto_box.isChecked():
                self.pause_timer.start()

    def observe_progress(self):
        code = self.editor.toPlainText()
        if not self.recent_code or self.recent_code[-1] != code:
            self.recent_code = (self.recent_code + [code])[-3:]
        found = set(concepts(code))
        new = found - self.seen_concepts
        self.seen_concepts |= found
        signature = issue_signature(code)
        if signature and signature != self.last_issue:
            self.issue_counts[signature] += 1
        self.last_issue = signature
        if new:
            self.level = 1
            self.example_button.setEnabled(False)
            self.hint_label.setText("Hint level 1 of 4")
        if new and not signature and self.auto_box.isChecked() and time.monotonic() - self.last_message_time >= 45:
            self.ask("progress")

    def idle_hint(self):
        if not self.auto_box.isChecked() or self.pages.currentIndex() != 1:
            return
        code = self.editor.toPlainText()
        if code == self.last_auto_code or self.current_question:
            return
        remaining = 45 - (time.monotonic() - self.last_message_time)
        if remaining > 0:
            self.pause_timer.start(int(remaining * 1000) + 10)
            return
        self.last_auto_code = code
        reason = "question" if len(self.history) > 0 and len(self.history) % 4 == 0 and code.strip() else "idle"
        self.ask(reason)

    def request_help(self):
        self.ask("help")

    def more_help(self):
        self.level = min(4, self.level + 1)
        self.ask("help")

    def submit_answer(self):
        if self.current_question and self.answer.text().strip():
            self.ask("answer")

    def ask(self, reason):
        if self.pages.currentIndex() != 1:
            return
        if reason == "example" and self.level < 4:
            return
        self.hint_label.setText(f"Hint level {self.level} of 4")
        self.example_button.setEnabled(self.level == 4)
        self.last_reason = reason
        self.last_message_time = time.monotonic()
        signature = issue_signature(self.editor.toPlainText())
        snap = Snapshot(
            self.session.task, self.session.reference, self.editor.toPlainText(),
            5 if reason == "example" else self.level, reason,
            self.answer.text().strip() if reason == "answer" else "",
            self.current_question, tuple(self.history[-6:]), tuple(self.plan),
            self.issue_counts[signature] >= 2 if signature else False,
            tuple(self.recent_code),
        )
        self.controller.request(self.provider, snap)

    def receive_feedback(self, feedback):
        self.plan = feedback.plan or self.plan
        self.history.append(feedback.message)
        self.history = self.history[-12:]
        combined = feedback.message + ("\n\n" + feedback.question if feedback.question else "")
        self.show_message(combined, feedback.state)
        self.snippet.setPlainText(feedback.snippet)
        self.snippet.setVisible(bool(feedback.snippet))
        self.current_question = feedback.question
        self.answer.clear()
        self.answer.setVisible(bool(feedback.question))
        self.answer_button.setVisible(bool(feedback.question))
        if self.last_reason == "review":
            status = "AI review: looks complete (not compiled or tested)." if feedback.complete else "Review: keep exploring and checking edge cases."
            if not self.ai_enabled:
                status = "Demo review: correctness has not been assessed."
            self.review_label.setText(status + "\n" + feedback.summary + ("\nConcepts: " + ", ".join(feedback.concepts) if feedback.concepts else ""))
            if feedback.complete:
                self.character.set_state("happy")
                self.pause_timer.stop()

    def receive_error(self, message):
        self.show_message(message + " You can retry Help or switch to demo in AI settings.", "surprised")

    def set_busy(self, busy):
        if busy:
            self.character.set_state("thinking")
            self.statusBar().showMessage("Thinking... You can keep writing. Outdated replies will be ignored.")
        else:
            self.update_mode()

    def show_message(self, message, state):
        self.bubble.setText(message)
        self.character.set_state(state)
        self.last_message_time = time.monotonic()
        self.speech.say(message)

    def toggle_automatic(self, enabled):
        self.preferences.automatic = enabled
        self.controller.invalidate()
        if enabled and self.pages.currentIndex() == 1:
            self.last_auto_code = None
            self.pause_timer.start()
        else:
            self.pause_timer.stop()
        self.persist_preferences()

    def toggle_sound(self, enabled):
        self.preferences.sound = enabled
        self.speech.set_enabled(enabled)
        self.persist_preferences()

    def speech_error(self, message):
        self.speech_note.setText(message)
        self.sound_box.setChecked(False)

    def save_code(self):
        if self.pages.currentIndex() != 1:
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Save your code", "my_solution.c", "C files (*.c);;Text files (*.txt)")
        if not path:
            return False
        try:
            Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(self, "Save failed", str(error))
            return False
        self.editor.document().setModified(False)
        self.statusBar().showMessage("Your code was saved. The reference remains in memory.")
        return True

    def may_discard(self):
        if not self.editor.document().isModified():
            return True
        answer = QMessageBox.question(self, "Unsaved code", "Would you like to save your code first?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_code()
        return answer == QMessageBox.StandardButton.Discard

    def new_exercise(self):
        if self.may_discard():
            self.controller.invalidate()
            self.pause_timer.stop()
            self.progress_timer.stop()
            self.speech.stop()
            self.pages.setCurrentIndex(0)
            self.session = LearningSession()
            self.editor.clear()
            self.editor.document().setModified(False)

    def closeEvent(self, event):
        if self.may_discard():
            self.controller.shutdown()
            self.pause_timer.stop()
            self.progress_timer.stop()
            self.speech.stop()
            event.accept()
        else:
            event.ignore()
