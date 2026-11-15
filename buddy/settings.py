"""Persist preferences only: no API key, consent, task, or source code."""
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QCheckBox, QLabel, QDialogButtonBox, QMessageBox
from .analysis import validate_endpoint

@dataclass
class Preferences:
    endpoint: str = ""
    model: str = ""
    sound: bool = True
    automatic: bool = True

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
        self.setWindowTitle("AI provider & privacy")
        self.setMinimumWidth(520)
        layout = QFormLayout(self)
        description = QLabel("Demo mode stays offline. AI mode sends the task, reference code, your code, answers and recent hints to the provider below. Provider charges and privacy policies apply.")
        description.setWordWrap(True)
        layout.addRow(description)
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
        self.consent = QCheckBox("Enable AI and allow this transfer for this app session")
        self.consent.setChecked(enabled)
        layout.addRow(self.consent)
        note = QLabel("Use an OpenAI-compatible Chat Completions provider. The base URL usually ends in /v1. Changing the destination requires consent again. Uncheck the box to return to demo mode. Requests already sent cannot be recalled.")
        note.setWordWrap(True)
        layout.addRow(note)
        self.endpoint.textChanged.connect(lambda: self.consent.setChecked(False))
        self.model.textChanged.connect(lambda: self.consent.setChecked(False))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

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
