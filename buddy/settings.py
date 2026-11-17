"""Persist preferences only: no API key, consent, task, or source code."""
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QCheckBox, QLabel, QDialogButtonBox, QMessageBox, QPushButton, QComboBox
from .analysis import validate_endpoint, ChatCompletionsTutor, Snapshot
from .controller import TutorController

@dataclass
class Preferences:
    endpoint: str = ""
    model: str = ""
    sound: bool = True
    automatic: bool = False

def settings_path():
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)) / "settings.json"

def load_preferences(path=None):
    try:
        data = json.loads((path or settings_path()).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return Preferences()
        return Preferences(
            endpoint=data.get("endpoint", "") if isinstance(data.get("endpoint", ""), str) else "",
            model=data.get("model", "") if isinstance(data.get("model", ""), str) else "",
            sound=data.get("sound", True) if isinstance(data.get("sound", True), bool) else True,
            automatic=data.get("automatic", True) if isinstance(data.get("automatic", True), bool) else True,
        )
    except (OSError, ValueError):
        return Preferences()

def save_preferences(preferences, path=None):
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(preferences), indent=2), encoding="utf-8")
    temporary.replace(path)

class SettingsDialog(QDialog):
    def __init__(self, preferences, key="", enabled=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI provider & privacy - v0.5")
        self.setMinimumWidth(520)
        layout = QFormLayout(self)
        description = QLabel("Demo mode stays offline. AI mode sends the task, reference code, your code, answers and recent hints to the provider below. Provider charges and privacy policies apply.")
        description.setWordWrap(True)
        layout.addRow(description)
        presets = QComboBox()
        presets.addItems(["Custom provider", "Groq", "Local server (Ollama-compatible)"])
        layout.addRow("Provider preset", presets)
        self.endpoint = QLineEdit(preferences.endpoint)
        self.endpoint.setPlaceholderText("https://your-provider.example/v1")
        self.model = QLineEdit(preferences.model)
        self.model.setPlaceholderText("Model identifier from your provider")
        self.key = QLineEdit(key)
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
        presets.currentIndexChanged.connect(preset)
        self.consent = QCheckBox("Enable AI and allow this transfer for this app session")
        self.consent.setChecked(enabled)
        layout.addRow(self.consent)
        note = QLabel("Use an OpenAI-compatible Chat Completions provider. The base URL usually ends in /v1. Changing the destination requires consent again. Uncheck the box to return to demo mode. Requests already sent cannot be recalled.")
        note.setWordWrap(True)
        layout.addRow(note)
        self.endpoint.textChanged.connect(lambda: self.consent.setChecked(False))
        self.model.textChanged.connect(lambda: self.consent.setChecked(False))
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
        layout.addRow(buttons)

    def test_finished(self, message):
        self.test_status.setText(message)
        self.test_button.setEnabled(True)

    def test_connection(self):
        if not self.consent.isChecked():
            self.test_status.setText("Enable the consent checkbox first. The test sends only a built-in sample, not your exercise.")
            return
        try:
            provider = ChatCompletionsTutor(self.endpoint.text(), self.model.text(), self.key.text())
        except ValueError as error:
            self.test_status.setText(str(error))
            return
        self.test_button.setEnabled(False)
        self.test_status.setText("Testing provider and tutoring response...")
        self.test_controller.request(provider, Snapshot("Print a greeting", '#include <stdio.h>\nint main(void) { puts("Hello"); }', "", reason="start"))

    def done(self, result):
        self.test_controller.shutdown()
        super().done(result)

    def validate(self):
        try:
            if self.consent.isChecked():
                validate_endpoint(self.endpoint.text())
                if not self.model.text().strip():
                    raise ValueError("Enter a model identifier.")
        except ValueError as error:
            QMessageBox.warning(self, "Check provider settings", str(error))
            return
        self.accept()
