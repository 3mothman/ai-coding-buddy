"""Optional native Qt speech with an English voice and a text-only fallback."""
from PySide6.QtCore import QObject, QLocale, Signal

class SpeechService(QObject):
    unavailable = Signal(str)
    speaking = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = None
        self.enabled = True
        self.last_message = ""
        self.reason = "Speech is unavailable. Text hints still work."
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            engines = [name for name in QTextToSpeech.availableEngines() if name != "mock"]
            if not engines:
                return
            self.engine = QTextToSpeech(engines[0], self)
            self.engine.errorOccurred.connect(self._error)
            self.engine.stateChanged.connect(lambda state: self.speaking.emit(state == QTextToSpeech.State.Speaking))
            english = [voice for voice in self.engine.availableVoices() if voice.locale().language() == QLocale.Language.English]
            if english:
                self.engine.setVoice(english[0])
            else:
                locales = [locale for locale in self.engine.availableLocales() if locale.language() == QLocale.Language.English]
                if not locales:
                    self.engine = None
                    self.reason = "No English speech voice is installed. Install one in Windows speech settings."
                    return
                self.engine.setLocale(locales[0])
            if self.engine.state() == QTextToSpeech.State.Error:
                self.engine = None
        except (ImportError, RuntimeError):
            self.engine = None

    def voices(self):
        if self.engine is None:
            return []
        return [v for v in self.engine.availableVoices() if v.locale().language() == QLocale.Language.English]

    def set_rate(self, rate):
        if self.engine is not None:
            self.engine.setRate(rate)

    @property
    def available(self):
        return self.engine is not None

    def _error(self, *_):
        self.enabled = False
        self.reason = "Speech playback failed. Text hints still work."
        self.unavailable.emit(self.reason)

    def set_enabled(self, enabled):
        self.enabled = enabled
        if not enabled:
            self.stop()

    def say(self, message):
        self.last_message = message
        if self.enabled and self.engine is not None:
            self.engine.stop()
            self.engine.say(message)

    def repeat(self):
        self.say(self.last_message)

    def stop(self):
        if self.engine is not None:
            self.engine.stop()
