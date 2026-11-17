"""Two simple views coordinating independent editor, tutor, speech and animation."""
from collections import Counter
from pathlib import Path
import time
from difflib import SequenceMatcher
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QFileDialog, QMessageBox, QCheckBox,
    QLineEdit, QScrollArea, QDialog, QComboBox, QSlider,
)
from .character import BuddyCharacter
from .editor import CodeEditor
from .session import LearningSession, read_reference
from .analysis import Snapshot, DemoTutor, ChatCompletionsTutor, concepts, issue_signature
from .orchestration import LearningOrchestrator
from .gemini_analysis import GeminiTutor
from .live_voice import LiveVoice
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
        self.last_checked_code = ""
        self.requested_code = ""
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
        self._displayed_objective = ""
        self.last_reason = ""
        self.voice = LiveVoice(self)
        self.voice_consent = False
        self.voice_tool_id = None
        self.voice_tool_question = ""
        self._preparing = False
        self._deferred_reason = None
        self._transcript_rows = []
        self._partial_transcripts = {}
        self.controller = LearningOrchestrator(self)
        self.controller.state_changed.connect(self.update_live_context)
        self.controller.policy.inactivity = self.preferences.inactivity
        self.controller.policy.cooldown = self.preferences.cooldown
        self.voice.tool_question.connect(self.voice_question)
        self.voice.tool_cancelled.connect(self.voice_tool_cancelled)
        self.voice.transcript.connect(self.receive_transcript)
        self.voice.connected.connect(self.voice_connected)
        self.voice.status.connect(lambda message: self.statusBar().showMessage(message))
        self.voice.failure.connect(self.voice_failure)
        self.voice.speaking.connect(self.live_speaking)
        self.voice.listening.connect(lambda active: self.controller.voice_activity(listening=active))
        self.controller.result.connect(self.receive_feedback)
        self.controller.failure.connect(self.receive_error)
        self.controller.busy_changed.connect(self.set_busy)
        self.speech = SpeechService(self)
        self.speech.set_enabled(self.preferences.sound)
        self.speech.unavailable.connect(self.speech_error)
        self.speech.speaking.connect(lambda active: self.controller.voice_activity(speaking=active))
        self.pause_timer = QTimer(self)
        self.pause_timer.setSingleShot(True)
        self.pause_timer.setInterval(self.preferences.inactivity * 1000)
        self.pause_timer.timeout.connect(self.idle_hint)
        self.progress_timer = QTimer(self)
        self.progress_timer.setSingleShot(True)
        self.progress_timer.setInterval(2000)
        self.progress_timer.timeout.connect(self.observe_progress)
        self.setWindowTitle("AI Coding Buddy - v0.8.4")
        self.resize(1160, 820)
        self.setMinimumSize(850, 650)
        self.setStyleSheet(STYLE)
        self.pages = QStackedWidget()
        self.setCentralWidget(self.pages)
        self.build_start()
        self.build_learning()
        self.editor.textChanged.connect(self.code_changed)
        self.reference_input.textChanged.connect(self.reference_changed)
        self.task_input.textChanged.connect(self.reference_changed)
        self.deferred_timer = QTimer(self)
        self.deferred_timer.setSingleShot(True)
        self.deferred_timer.setInterval(500)
        self.deferred_timer.timeout.connect(self.run_deferred)
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
        self.preparation_status = self.label("", "subtitle")
        layout.addWidget(self.preparation_status)
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
        left_panel = QWidget()
        left_panel.setMaximumWidth(230)
        left = QVBoxLayout(left_panel)
        left.addWidget(self.label("OBJECTIVE", "subtitle"))
        self.objective_label = self.label("Start your exercise to see the current goal.", "bubble")
        left.addWidget(self.objective_label)
        left.addStretch()
        self.talk_button = self.button("Hold to talk", lambda: None, left)
        self.talk_button.setEnabled(False)
        self.talk_button.pressed.connect(self.begin_talking)
        self.talk_button.released.connect(self.end_talking)
        left.addWidget(self.label("Start Live voice, then hold this button while speaking.", "subtitle"))
        content.addWidget(left_panel)
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
        self.lesson_heading = self.label("Let's learn together", "subtitle")
        right.addWidget(self.lesson_heading)
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
        self.repeat_button = self.button("Repeat", self.repeat_message, row)
        self.repeat_button.setEnabled(self.speech.available)
        right.addLayout(row)
        self.example_button = self.button("Show a small example", lambda: self.ask("example"), right)
        self.example_button.setEnabled(False)
        self.check_button = self.button("Check my code", lambda: self.ask("check"), right)
        self.check_button.setObjectName("primary")
        self.check_button.setToolTip("Check your current work and get one small next step.")
        self.button("Ask me a question", lambda: self.ask("question"), right)
        self.answer = QLineEdit()
        self.answer.setPlaceholderText("Your answer to the buddy's question")
        self.answer.setMaxLength(2000)
        self.answer.setAccessibleName("Answer to understanding question")
        self.answer.textEdited.connect(self.answer_edited)
        self.answer.returnPressed.connect(self.submit_answer)
        self.answer.hide()
        right.addWidget(self.answer)
        self.answer_button = self.button("Submit answer", self.submit_answer, right)
        self.answer_button.hide()
        self.button("Review my solution", lambda: self.ask("review"), right)
        self.auto_box = QCheckBox("Automatic hints")
        self.auto_box.setChecked(False)
        self.preferences.automatic = False
        self.auto_box.toggled.connect(self.toggle_automatic)
        right.addWidget(self.auto_box)
        self.sound_box = QCheckBox("Sound")
        self.sound_box.setChecked(self.preferences.sound and self.speech.available)
        self.sound_box.setEnabled(self.speech.available)
        self.sound_box.toggled.connect(self.toggle_sound)
        self.live_button = self.button("Start Live voice", self.toggle_live, right)
        self.mute_button = self.button("Mute microphone", self.toggle_microphone, right)
        self.mute_button.setCheckable(True)
        self.mute_button.hide()
        self.live_status = self.label("Live voice requires Gemini and audio consent in AI settings.", "subtitle")
        right.addWidget(self.live_status)
        self.transcript_view = QPlainTextEdit()
        self.transcript_view.setReadOnly(True)
        self.transcript_view.setAccessibleName("Live conversation transcript")
        self.transcript_view.setMaximumHeight(130)
        self.transcript_view.hide()
        right.addWidget(self.transcript_view)
        right.addWidget(self.sound_box)
        self.speech_note = self.label("", "subtitle")
        right.addWidget(self.speech_note)
        self.voice_choice = QComboBox()
        self.voice_choice.setAccessibleName("English voice")
        for voice in self.speech.voices():
            self.voice_choice.addItem(voice.name(), voice)
        self.voice_choice.currentIndexChanged.connect(self.choose_voice)
        right.addWidget(self.label("Voice"))
        right.addWidget(self.voice_choice)
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(-50, 30)
        self.speed.setValue(-10)
        self.speed.setAccessibleName("Speech speed")
        self.speed.valueChanged.connect(lambda value: self.speech.set_rate(value / 100))
        self.speech.set_rate(-0.1)
        right.addWidget(self.label("Speech speed: slower to faster"))
        right.addWidget(self.speed)
        self.preview_button = self.button("Preview voice", lambda: self.speech.say("Let's build this program together, one step at a time."), right)
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
        if hasattr(self, "live_button"):
            gemini = isinstance(self.provider, GeminiTutor)
            self.live_button.setEnabled(gemini and self.voice_consent)
            self.voice_choice.setEnabled(not gemini)
            self.speed.setEnabled(not gemini)
            self.preview_button.setEnabled(not gemini)
            self.repeat_button.setEnabled(self.speech.available or self.voice.is_connected)
            self.sound_box.setEnabled(True if gemini else self.speech.available)
            if gemini:
                self.speech.stop()
                self.speech_note.setText("Gemini Live voice is connected." if self.voice.is_connected else "Start Live voice to hear the tutor. Text hints remain visible while audio is prepared.")

    def persist_preferences(self):
        try:
            save_preferences(self.preferences)
        except OSError:
            self.statusBar().showMessage("Preferences could not be saved. They still apply for this session.")

    def open_settings(self):
        dialog = SettingsDialog(self.preferences, self.api_key, self.ai_enabled, self, live_enabled=self.voice_consent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.stop_live()
        backend_changed = (
            self.preferences.provider != ("gemini" if dialog.presets.currentIndex() == 3 else "compatible")
            or self.preferences.model != dialog.model.text().strip()
            or self.api_key != dialog.key.text().strip())
        if backend_changed:
            self.controller.reset()
        else:
            self.controller.invalidate()
        self.speech.stop()
        self.preferences.provider = "gemini" if dialog.presets.currentIndex() == 3 else "compatible"
        self.preferences.live_model = dialog.live_model.text().strip()
        self.preferences.live_voice = dialog.live_voice.currentText()
        self.preferences.language = dialog.language.currentText()
        self.preferences.headphones = dialog.headphones.isChecked()
        self.preferences.inactivity = dialog.inactivity.value()
        self.preferences.cooldown = dialog.cooldown.value()
        self.controller.policy.inactivity = self.preferences.inactivity
        self.controller.policy.cooldown = self.preferences.cooldown
        self.pause_timer.setInterval(self.preferences.inactivity * 1000)
        self.voice_consent = dialog.voice_consent.isChecked() and self.preferences.provider == "gemini"
        self.preferences.endpoint = dialog.endpoint.text().strip()
        self.preferences.model = dialog.model.text().strip()
        self.api_key = dialog.key.text().strip()
        self.ai_enabled = dialog.consent.isChecked()
        self.provider = dialog.make_provider() if self.ai_enabled else DemoTutor()
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
        self.stop_live()
        self.controller.reset()
        self.session = LearningSession(self.task_input.toPlainText().strip(), reference)
        self.task_label.setText(self.session.task or "Reconstruct the solution in your own way.")
        self.task_label.setToolTip(self.session.task)
        self.objective_label.setText("Preparing your first step...")
        self.editor.clear()
        self.editor.document().setModified(False)
        self.history, self.plan = [], []
        self._transcript_rows = []
        self._partial_transcripts = {}
        self.transcript_view.clear()
        self.transcript_view.hide()
        self.recent_code = []
        self.last_checked_code = ""
        self.requested_code = ""
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
        if isinstance(self.provider, GeminiTutor):
            self._preparing = True
            self.start_button.setEnabled(False)
            self.preparation_status.setText("Understanding the task and reference before practice...")
            self.statusBar().showMessage("Understanding the task and reference before practice...")
            self.last_reason = "prepare"
            self.controller.request(self.provider, Snapshot(self.session.task, self.session.reference, "", reason="prepare", language=self.preferences.language))
            return
        self.pages.setCurrentIndex(1)
        self.editor.setFocus()
        self.show_message("I'm reading your reference. We'll build this together, one concept at a time.", "neutral")
        self.ask("start")

    def reference_changed(self):
        if self._preparing:
            self._preparing = False
            self.controller.invalidate()
            self.preparation_status.setText("Task changed. Start Learning again to analyze this version.")
            self.start_button.setEnabled(bool(self.reference_input.toPlainText().strip()))
            self.statusBar().showMessage("Task changed. Start Learning again to analyze this version.")

    def code_changed(self):
        self.editor.set_analysis_range(0, 0)
        self.controller.edited(self.editor.toPlainText())
        if self.voice_tool_id:
            self.voice.respond_tool(self.voice_tool_id, "The code changed. Ask again about the current version.", self.controller.revision, stale=True)
            self.voice_tool_id = None
        self.update_live_context()
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
        if new and not isinstance(self.provider, GeminiTutor):
            self.level = 1
            self.example_button.setEnabled(False)
            self.hint_label.setText("Hint level 1 of 4")
        # Structural keywords are not evidence of correctness. Only check actual work.
        if (isinstance(self.provider, GeminiTutor) and self.auto_box.isChecked()
                and code.rstrip().endswith((";", "}"))
                and self.controller.policy.can_analyze(time.monotonic(), self.controller.last_edit,
                                                       self.controller.revision, minimum_idle=1.8)):
            self.last_auto_code = code
            self.ask("auto")

    def idle_hint(self):
        if not self.auto_box.isChecked() or self.pages.currentIndex() != 1:
            return
        code = self.editor.toPlainText()
        if code == self.last_auto_code or self.current_question:
            return
        remaining = self.preferences.cooldown - (time.monotonic() - self.last_message_time)
        if remaining > 0:
            self.pause_timer.start(int(remaining * 1000) + 10)
            return
        if isinstance(self.provider, GeminiTutor):
            if not self.controller.policy.can_analyze(time.monotonic(), self.controller.last_edit, self.controller.revision):
                self.pause_timer.start(1000)
                return
            self.last_auto_code = code
            self.ask("auto")
        else:
            self.last_auto_code = code
            self.ask("check")

    def request_help(self):
        self.ask("help")

    def answer_edited(self):
        self.controller.invalidate()
        self.update_live_context()

    def more_help(self):
        self.level = min(4, self.level + 1)
        self.ask("help")

    def submit_answer(self):
        if self.current_question and self.answer.text().strip():
            self.ask("answer")

    def ask(self, reason):
        if self.pages.currentIndex() != 1:
            return
        if isinstance(self.provider, GeminiTutor) and not self.controller.memory.reference:
            self.show_message("Start a new exercise so Gemini can analyze the reference first.", "thinking")
            return
        policy = self.controller.policy
        if reason not in {"voice_question", "auto"} and (policy.speaking or policy.listening or time.monotonic() - policy.last_voice_activity < 2):
            self._deferred_reason = reason
            self.deferred_timer.start()
            self.statusBar().showMessage("I'll check this after the conversation pauses.")
            return
        if reason == "example" and self.level < 4:
            return
        self.hint_label.setText(f"Hint level {self.level} of 4")
        self.example_button.setEnabled(self.level == 4)
        self.last_reason = reason
        self.last_message_time = time.monotonic()
        signature = issue_signature(self.editor.toPlainText())
        current_code = self.editor.toPlainText()
        changes = []
        for tag, _, _, begin, end in SequenceMatcher(None, self.last_checked_code.splitlines(), current_code.splitlines()).get_opcodes():
            if tag != "equal":
                changes.extend(range(begin + 1, max(begin + 2, end + 1)))
        self.requested_code = current_code
        snap = Snapshot(
            self.session.task, self.session.reference, self.editor.toPlainText(),
            5 if reason == "example" else self.level, reason,
            self.answer.text().strip() if reason == "answer" else "",
            self.current_question, tuple(self.history[-6:]), tuple(self.plan),
            self.issue_counts[signature] >= 2 if signature else False,
            tuple(self.recent_code),
            self.editor.textCursor().blockNumber() + 1,
            self.last_checked_code, tuple(changes),
            "Teach the current concept: meaning, purpose, symbols, then one action. After a correct step teach the next one. Do not repeat completed headers.",
            voice_question=self.voice_tool_question if reason == "voice_question" else "",
            language=self.preferences.language,
        )
        self.controller.request(self.provider, snap)

    def receive_feedback(self, feedback):
        if self._preparing:
            self._preparing = False
            self.start_button.setEnabled(True)
            self.preparation_status.clear()
            self.pages.setCurrentIndex(1)
            self.editor.setFocus()
        if feedback.action == "stay_silent":
            return
        if feedback.structured:
            diagnosis = feedback.structured["analysis"]
            self.editor.set_analysis_range(diagnosis["line_start"], diagnosis["line_end"], diagnosis["issue"])
            objective = feedback.structured["student_progress"]["current_objective"]
            if self._displayed_objective and objective != self._displayed_objective:
                self.level = 1
                self.example_button.setEnabled(False)
                self.hint_label.setText("Hint level 1 of 4")
            self._displayed_objective = objective
        self.lesson_heading.setText(feedback.lesson_title or "Your current step")
        current = self.controller.memory.objective
        objectives = (self.controller.memory.reference or {}).get("objectives", [])
        title = next((step["title"] for step in objectives if step["id"] == current), feedback.lesson_title)
        self.objective_label.setText(title or "Work on your current step.")
        self.last_checked_code = self.requested_code
        self.plan = feedback.plan or self.plan
        self.history.append(feedback.message)
        self.history = self.history[-12:]
        combined = feedback.message + ("\n\n" + feedback.question if feedback.question and feedback.question != feedback.message else "")
        if self.voice.is_connected and self.sound_box.isChecked() and feedback.should_speak:
            if self.voice_tool_id:
                self.voice.respond_tool(self.voice_tool_id, combined, self.controller.revision)
                self.voice_tool_id = None
            else:
                self.voice.teach(combined, self.controller.revision)
            self.bubble.setText(combined)
            self.character.set_state(feedback.state)
        else:
            if self.voice_tool_id:
                self.voice.respond_tool(self.voice_tool_id, "Voice was stopped. Please use the text hint.", self.controller.revision, stale=True)
                self.voice_tool_id = None
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
        if self._preparing:
            self._preparing = False
            self.start_button.setEnabled(True)
            self.preparation_status.setText(message + " Press Start Learning to retry.")
        if self.voice_tool_id:
            self.voice.respond_tool(self.voice_tool_id, "Analysis failed. Ask the learner to retry.", self.controller.revision, stale=True)
            self.voice_tool_id = None
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
        if not isinstance(self.provider, GeminiTutor):
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
        self.speech.set_enabled(enabled and not isinstance(self.provider, GeminiTutor))
        if not enabled and self.voice.running:
            self.stop_live()
        self.persist_preferences()

    def run_deferred(self):
        policy = self.controller.policy
        if policy.speaking or policy.listening or time.monotonic() - policy.last_voice_activity < 2:
            self.deferred_timer.start()
            return
        reason, self._deferred_reason = self._deferred_reason, None
        if reason:
            self.ask(reason)

    def update_live_context(self):
        memory = self.controller.memory
        reference = memory.reference or {}
        self.voice.update_context({
            "assignment": self.session.task,
            "reference_summary": reference.get("reference_summary", ""),
            "code": self.editor.toPlainText()[:40000] if hasattr(self, "editor") else "",
            "completed": memory.completed, "objective": memory.objective,
            "summary": memory.summary, "recent_conversation": list(memory.conversation)[-6:],
        }, self.controller.revision)

    def toggle_live(self):
        if self.voice.running:
            self.stop_live()
            return
        if not isinstance(self.provider, GeminiTutor) or not self.voice_consent:
            self.live_status.setText("Enable Gemini and microphone consent in AI settings first.")
            return
        if not self.controller.memory.reference:
            self.live_status.setText("Analyze the reference by starting this exercise again first.")
            return
        self.speech.stop()
        self.speech.set_enabled(False)
        self.sound_box.setChecked(True)
        self.update_live_context()
        self.live_button.setText("Stop Live voice")
        self.live_status.setText("Connecting... microphone will start after connection.")
        self.voice.start(self.provider.api_key, self.preferences.live_model,
                         self.preferences.live_voice, self.preferences.language, self.preferences.headphones)

    def stop_live(self):
        self.voice.stop()
        self.voice_tool_id = None
        self.controller.voice_activity(speaking=False, listening=False)
        if hasattr(self, "live_button"):
            self.live_button.setText("Start Live voice")
            self.mute_button.hide()

    def begin_talking(self):
        if self.voice.is_connected:
            self.voice.mute(False)
            self.talk_button.setText("Listening — release to send")

    def end_talking(self):
        self.voice.mute(True)
        self.talk_button.setText("Hold to talk")

    def voice_connected(self, connected):
        self.talk_button.setEnabled(connected)
        self.end_talking()
        self.update_mode()
        if connected and self.history and self.sound_box.isChecked():
            self.voice.teach(self.history[-1], self.controller.revision)
        self.live_status.setText("Live voice ready. Hold the talk button to speak." if connected else "Live voice disconnected. Text tutoring is available.")
        self.mute_button.setVisible(False)
        self.transcript_view.setVisible(connected or bool(self._transcript_rows))
        self.repeat_button.setEnabled(connected or self.speech.available)
        if not self.voice.running:
            self.live_button.setText("Start Live voice")

    def toggle_microphone(self):
        muted = self.mute_button.isChecked()
        self.voice.mute(muted)
        self.mute_button.setText("Unmute microphone" if muted else "Mute microphone")
        self.live_status.setText("Microphone muted." if muted else "Microphone on.")

    def live_speaking(self, active):
        self.controller.voice_activity(speaking=active)
        self.character.set_talking(active)

    def voice_failure(self, message):
        self.live_status.setText(message + " Text tutoring still works.")
        self.live_button.setText("Start Live voice")

    def voice_question(self, call_id, question):
        if self.voice_tool_id:
            self.voice.respond_tool(self.voice_tool_id, "A newer question replaced this one.", self.controller.revision, stale=True)
        self.voice_tool_id = call_id
        self.voice_tool_question = question
        self.controller.memory.remember("user", question)
        self.ask("voice_question")

    def voice_tool_cancelled(self, call_id):
        if self.voice_tool_id == call_id:
            self.voice_tool_id = None
            self.controller.invalidate()

    def receive_transcript(self, role, text, final, interrupted):
        prefix = "You" if role == "user" else "AI Buddy"
        if interrupted:
            # Received transcription can lead playback; do not claim the tail was heard.
            text = "[Interrupted; received text may include an unplayed ending] " + text
        elif role == "assistant" and not final:
            prefix += " (playing; partial)"
        self._partial_transcripts[role] = prefix + ": " + text
        if final:
            self._transcript_rows.append(self._partial_transcripts.pop(role))
            self._transcript_rows = self._transcript_rows[-20:]
            self.controller.memory.remember(role, text)
            self.update_live_context()
        self.transcript_view.setPlainText("\n".join(self._transcript_rows + list(self._partial_transcripts.values())))
        self.transcript_view.verticalScrollBar().setValue(self.transcript_view.verticalScrollBar().maximum())
        if role == "assistant":
            self.bubble.setText(text)

    def repeat_message(self):
        if self.voice.is_connected:
            self.voice.teach(self.bubble.text(), self.controller.revision)
        elif not isinstance(self.provider, GeminiTutor):
            self.speech.repeat()

    def choose_voice(self, index):
        voice = self.voice_choice.itemData(index)
        if voice is not None and self.speech.engine is not None:
            self.speech.stop()
            self.speech.engine.setVoice(voice)

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
            self.stop_live()
            self.controller.reset()
            self.pause_timer.stop()
            self.progress_timer.stop()
            self.speech.stop()
            self.pages.setCurrentIndex(0)
            self.session = LearningSession()
            self.editor.clear()
            self.editor.document().setModified(False)

    def closeEvent(self, event):
        if self.may_discard():
            self.stop_live()
            self.deferred_timer.stop()
            self.controller.shutdown()
            self.pause_timer.stop()
            self.progress_timer.stop()
            self.speech.stop()
            event.accept()
        else:
            event.ignore()
