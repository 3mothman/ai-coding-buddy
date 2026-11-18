"""Generate a complete read-aloud clip before playback; never open a microphone."""
import asyncio
import io
import wave
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, QTimer
from .audio_io import PlaybackBuffer, PCMResampler


async def synthesize(key, model, voice, text, on_chunk=None):
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
                                    if on_chunk:
                                        on_chunk(data.data)
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
    chunk = Signal(int, bytes)


class Job(QRunnable):
    def __init__(self, token, args):
        super().__init__()
        self.token, self.args = token, args
        self.signals = Result()

    def run(self):
        try:
            self.signals.ready.emit(self.token, asyncio.run(synthesize(*self.args, on_chunk=lambda data: self.signals.chunk.emit(self.token, data))), "")
        except Exception as error:
            self.signals.ready.emit(self.token, b"", str(error))


class NaturalSpeech(QObject):
    speaking = Signal(bool)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.token = 0
        self.jobs = {}
        self.stream = None
        self.queue = PlaybackBuffer(24000 * 2 * 180)
        self.resampler = None
        self.done = False
        self.started = False
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._pump)

    def stop(self):
        self.token += 1
        self.timer.stop()
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.queue.clear()
        self.started = False
        self.speaking.emit(False)

    def say(self, key, model, voice, text):
        self.stop()
        self.done = False
        token = self.token
        job = Job(token, (key, model, voice, text))
        self.jobs[token] = job
        job.signals.ready.connect(self._ready)
        job.signals.chunk.connect(self._chunk)
        self.status.emit("Waiting for the first Gemini audio chunks...")
        QThreadPool.globalInstance().start(job)

    def _chunk(self, token, data):
        if token != self.token:
            return
        try:
            if self.stream is None:
                import sounddevice as sd
                device = sd.query_devices(kind="output")
                rate = int(device["default_samplerate"])
                self.resampler = PCMResampler(24000, rate)
                self.queue.maximum = rate * 2 * 180
                self.rate = rate
                self.stream = sd.RawOutputStream(channels=1, dtype="int16", samplerate=rate,
                    callback=self._play, blocksize=max(240, rate // 50))
                self.timer.start()
            converted = self.resampler.convert(data)
            if converted and not self.queue.put(converted):
                raise RuntimeError("buffer full")
        except Exception:
            self.stop()
            self.status.emit("Audio output failed. Check the Windows output device and press Repeat.")

    def _play(self, output, frames, timing, status):
        output[:] = self.queue.take(frames * 2)

    def _pump(self):
        if not self.stream:
            return
        # Start after 400 ms, not after the entire explanation has arrived.
        if not self.started and (self.queue.pending >= int(self.rate * 2 * 0.4) or self.done):
            self.stream.start()
            self.started = True
            self.speaking.emit(True)
            self.status.emit("Reading aloud — Gemini audio is streaming.")
        elif self.started and self.done and not self.queue.pending:
            # Drain device latency before closing the output.
            self.timer.stop()
            token = self.token
            QTimer.singleShot(250, lambda: self._finish(token))

    def _finish(self, token):
        if token == self.token:
            self.stop()
            self.status.emit("Reading finished.")

    def _ready(self, token, data, error):
        self.jobs.pop(token, None)
        if token != self.token:
            return
        if error:
            self.stop()
            self.status.emit(error)
            return
        if self.resampler:
            tail = self.resampler.convert(b"", final=True)
            if tail:
                self.queue.put(tail)
        self.done = True
