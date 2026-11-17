"""Persist preferences only: no API key, consent, task, or source code."""
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QCheckBox, QLabel, QDialogButtonBox, QMessageBox, QPushButton, QComboBox, QSpinBox, QScrollArea, QVBoxLayout, QWidget
from .analysis import validate_endpoint, ChatCompletionsTutor, Snapshot
from .controller import TutorController
from .gemini_analysis import GeminiTutor, DEFAULT_FLASH, DEFAULT_LIVE

@dataclass
class Preferences:
    endpoint: str = ""
    model: str = ""
    sound: bool = True
    automatic: bool = False
    provider: str = "compatible"
    live_model: str = DEFAULT_LIVE
    live_voice: str = "Aoede"
    language: str = "English"
    inactivity: int = 25
    cooldown: int = 45
    headphones: bool = True

def settings_path():
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)) / "settings.json"

def load_preferences(path=None):
    try:
        data = json.loads((path or settings_path()).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return Preferences()
        defaults = Preferences()
        from dataclasses import fields
        values = {}
        for field in fields(defaults):
            default = getattr(defaults, field.name)
            value = data.get(field.name, default)
            values[field.name] = value if type(value) is type(default) else default
        values["inactivity"] = max(5, min(300, values["inactivity"]))
        values["cooldown"] = max(15, min(600, values["cooldown"]))
        if values["provider"] not in {"compatible", "gemini"}:
            values["provider"] = "compatible"
        if values["language"] not in {"English", "German"}:
            values["language"] = "English"
        return Preferences(**values)
    except (OSError, ValueError):
        return Preferences()

def save_preferences(preferences, path=None):
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(preferences), indent=2), encoding="utf-8")
    temporary.replace(path)

class SettingsDialog(QDialog):
    def __init__(self, preferences, key="", enabled=False, parent=None, live_enabled=False):
        super().__init__(parent)
        self.setWindowTitle("AI provider & privacy - v0.8.6")
        self.setMinimumWidth(520)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QFormLayout(body)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.resize(650, 720)
        description = QLabel("Demo mode stays offline. AI mode sends the task, reference code, your code, answers and recent hints to the provider below. Provider charges and privacy policies apply.")
        description.setWordWrap(True)
        layout.addRow(description)
        self.presets = presets = QComboBox()
        presets.addItems(["Custom provider", "Groq", "Local server (Ollama-compatible)", "Gemini (official Google SDK)"])
        layout.addRow("Provider preset", presets)
        self.endpoint = QLineEdit(preferences.endpoint)
        self.endpoint.setPlaceholderText("https://your-provider.example/v1")
        self.model = QLineEdit(preferences.model)
        self.model.setPlaceholderText("Model identifier from your provider")
        self.key = QLineEdit(key or (os.getenv("GEMINI_API_KEY", "") if preferences.provider == "gemini" else ""))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Kept in memory only; optional for a local server")
        layout.addRow("API base URL", self.endpoint)
        layout.addRow("Model", self.model)
        layout.addRow("API key", self.key)
        def preset(index):
            if index == 1:
                self.endpoint.setText("https://api.groq.com/openai/v1")
                self.model.setText("openai/gpt-oss-120b")
            elif index == 2:
                self.endpoint.setText("http://localhost:11434/v1")
                self.model.clear()
                self.model.setPlaceholderText("Exact name of a model installed in your local server")
                self.key.clear()
            elif index == 3:
                self.endpoint.setText("https://generativelanguage.googleapis.com")
                self.model.setText(DEFAULT_FLASH)
                self.key.clear()
                self.key.setText(os.getenv("GEMINI_API_KEY", ""))
            self.endpoint.setEnabled(index != 3)
            self.gemini_options.setVisible(index == 3)
            self.provider_note.setText("Gemini uses the official Google SDK. No Chat Completions URL is required. Your task, code and learning context go to Google only after consent." if index == 3 else "Use a Chat Completions-compatible provider. The base URL usually ends in /v1. Uncheck consent to return to demo mode.")
        presets.currentIndexChanged.connect(preset)
        self.consent = QCheckBox("Enable AI and allow this transfer for this app session")
        self.consent.setChecked(enabled)
        layout.addRow(self.consent)
        self.provider_note = note = QLabel("Use an OpenAI-compatible Chat Completions provider. The base URL usually ends in /v1. Changing the destination requires consent again. Uncheck the box to return to demo mode. Requests already sent cannot be recalled.")
        note.setWordWrap(True)
        layout.addRow(note)
        self.endpoint.textChanged.connect(lambda: self.consent.setChecked(False))
        self.model.textChanged.connect(lambda: self.consent.setChecked(False))
        self.gemini_options = QWidget()
        gemini_form = QFormLayout(self.gemini_options)
        gemini_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.live_model = QLineEdit(preferences.live_model)
        self.live_voice = QComboBox()
        self.live_voice.addItems(["Aoede", "Kore", "Puck", "Charon", "Fenrir", "Leda", "Orus", "Zephyr"])
        self.live_voice.setCurrentText(preferences.live_voice)
        self.language = QComboBox()
        self.language.addItems(["English", "German"])
        self.language.setCurrentText(preferences.language)
        self.headphones = QCheckBox("Headphone mode (full duplex)")
        self.headphones.setChecked(preferences.headphones)
        self.voice_consent = QCheckBox("Allow microphone/audio transfer to Google")
        self.voice_consent.setChecked(live_enabled)
        voice_note = QLabel("Start Live voice from the learning view after saving. Stopping or muting stops microphone transmission. Speaker-safe mode gates capture during playback; it is not acoustic echo cancellation.")
        voice_note.setWordWrap(True)
        gemini_form.addRow("Live audio model", self.live_model)
        gemini_form.addRow("Live voice", self.live_voice)
        gemini_form.addRow("Teaching language", self.language)
        gemini_form.addRow(self.headphones)
        gemini_form.addRow(self.voice_consent)
        gemini_form.addRow(voice_note)
        layout.addRow(self.gemini_options)
        self.inactivity = QSpinBox()
        self.inactivity.setRange(5, 300)
        self.inactivity.setValue(preferences.inactivity)
        self.inactivity.setSuffix(" seconds")
        self.cooldown = QSpinBox()
        self.cooldown.setRange(15, 600)
        self.cooldown.setValue(preferences.cooldown)
        self.cooldown.setSuffix(" seconds")
        layout.addRow("Pause before considering help", self.inactivity)
        layout.addRow("Unsolicited hint cooldown", self.cooldown)
        self.test_controller = TutorController(self)
        self.test_controller.result.connect(lambda _: self.test_finished("Connection and tutoring response passed."))
        self.test_controller.failure.connect(self.test_finished)
        self.test_button = QPushButton("Test connection (sample exercise only)")
        self.test_button.clicked.connect(self.test_connection)
        layout.addRow(self.test_button)
        self.test_status = QLabel("")
        self.test_status.setWordWrap(True)
        layout.addRow(self.test_status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        presets.blockSignals(True)
        presets.setCurrentIndex(3 if preferences.provider == "gemini" else 0)
        presets.blockSignals(False)
        self.endpoint.setEnabled(preferences.provider != "gemini")
        self.gemini_options.setVisible(preferences.provider == "gemini")
        if preferences.provider == "gemini":
            self.provider_note.setText("Gemini uses the official Google SDK. No Chat Completions URL is required. Your task, code and learning context go to Google only after consent.")
            self.endpoint.setText("https://generativelanguage.googleapis.com")
        def revoke():
            self.consent.setChecked(False)
            self.voice_consent.setChecked(False)
            self.test_controller.invalidate()
            self.test_button.setEnabled(True)
            self.test_status.clear()
        self.endpoint.textChanged.connect(revoke)
        self.model.textChanged.connect(revoke)
        self.key.textChanged.connect(revoke)
        self.live_model.textChanged.connect(lambda: self.voice_consent.setChecked(False))

    def test_finished(self, message):
        self.test_status.setText(message)
        self.test_button.setEnabled(True)

    def test_connection(self):
        if not self.consent.isChecked():
            self.test_status.setText("Enable the consent checkbox first. The test sends only a built-in sample, not your exercise.")
            return
        try:
            provider = self.make_provider()
        except ValueError as error:
            self.test_status.setText(str(error))
            return
        self.test_button.setEnabled(False)
        self.test_status.setText("Testing provider and tutoring response...")
        self.test_controller.request(provider, Snapshot("Print a greeting", '#include <stdio.h>\nint main(void) { puts("Hello"); }', "", reason="prepare" if self.presets.currentIndex() == 3 else "start"))

    def done(self, result):
        self.test_controller.shutdown()
        super().done(result)

    def make_provider(self):
        if self.presets.currentIndex() == 3:
            return GeminiTutor(self.model.text(), self.key.text())
        return ChatCompletionsTutor(self.endpoint.text(), self.model.text(), self.key.text())

    def validate(self):
        try:
            if self.consent.isChecked():
                self.make_provider()
                if self.voice_consent.isChecked() and not self.live_model.text().strip():
                    raise ValueError("Enter a Live model identifier.")
        except ValueError as error:
            QMessageBox.warning(self, "Check provider settings", str(error))
            return
        self.accept()
