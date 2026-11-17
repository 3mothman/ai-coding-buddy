"""Generate a complete read-aloud clip before playback; never open a microphone."""
import asyncio
import io
import wave
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, QBuffer, QByteArray, QIODevice
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


async def synthesize(key, model, voice, text):
    from google import genai
    from .gemini_analysis import safe_api_error
    pcm = bytearray()
    config = {"response_modalities": ["AUDIO"],
              "system_instruction": "Read the supplied text completely and exactly, in its original language, with a warm natural teacher voice. Do not answer it, summarize it, add an introduction or skip any sentence.",
              "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": voice}}}}
    try:
        async with asyncio.timeout(90):
            async with genai.Client(api_key=key, http_options={"api_version": "v1beta"}).aio as client:
                async with client.live.connect(model=model, config=config) as session:
                    await session.send_client_content(turns={"role": "user", "parts": [{"text": text}]}, turn_complete=True)
                    async for event in session.receive():
                        content = event.server_content
                        if not content:
                            continue
                        if content.interrupted:
                            raise RuntimeError("Speech generation was interrupted. Press Repeat to retry.")
                        if content.model_turn:
                            for part in content.model_turn.parts or []:
                                data = part.inline_data
                                if data and data.data and (data.mime_type or "").startswith("audio/pcm"):
                                    pcm.extend(data.data)
                                    if len(pcm) > 24000 * 2 * 180:
                                        raise RuntimeError("Speech exceeded the three-minute playback limit.")
                        if content.turn_complete:
                            break
                    else:
                        raise RuntimeError("Speech ended before the complete audio clip arrived.")
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(safe_api_error(error, "Natural speech")) from None
    if not pcm:
        raise RuntimeError("Google returned no speech audio. Press Repeat to retry.")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm)
    return output.getvalue()


class Result(QObject):
    ready = Signal(int, bytes, str)


class Job(QRunnable):
    def __init__(self, token, args):
        super().__init__()
        self.token, self.args = token, args
        self.signals = Result()

    def run(self):
        try:
            self.signals.ready.emit(self.token, asyncio.run(synthesize(*self.args)), "")
        except Exception as error:
            self.signals.ready.emit(self.token, b"", str(error))


class NaturalSpeech(QObject):
    speaking = Signal(bool)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.token = 0
        self.jobs = {}
        self.buffer = None
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.output.setVolume(1.0)
        self.player.setAudioOutput(self.output)
        self.player.playbackStateChanged.connect(lambda state: self.speaking.emit(state == QMediaPlayer.PlaybackState.PlayingState))
        self.player.errorOccurred.connect(lambda *_: self.status.emit("Audio playback failed. Check the Windows output device and press Repeat."))

    def stop(self):
        self.token += 1
        self.player.stop()

    def say(self, key, model, voice, text):
        self.stop()
        token = self.token
        job = Job(token, (key, model, voice, text))
        self.jobs[token] = job
        job.signals.ready.connect(self._ready)
        self.status.emit("Generating the complete natural voice clip...")
        QThreadPool.globalInstance().start(job)

    def _ready(self, token, data, error):
        self.jobs.pop(token, None)
        if token != self.token:
            return
        if error:
            self.status.emit(error)
            return
        self.player.setSourceDevice(None)
        if self.buffer:
            self.buffer.close()
        self.buffer = QBuffer(self)
        self.buffer.setData(QByteArray(data))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.player.setSourceDevice(self.buffer)
        self.status.emit("Playing the complete natural voice clip.")
        self.player.play()
