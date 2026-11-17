"""Bounded RAM-only PCM streams. No microphone recordings or per-chunk devices."""
from queue import Queue, Empty, Full
import threading
import time


class PlaybackBuffer:
    def __init__(self, maximum_bytes=48000 * 12):
        self.maximum = maximum_bytes
        self._data = bytearray()
        self._lock = threading.Lock()
        self.discarded = 0

    def put(self, data):
        with self._lock:
            if len(self._data) + len(data) > self.maximum:
                # Do not play delayed stale speech after a slow consumer.
                self._data.clear()
                self.discarded += 1
                return False
            self._data.extend(data)
            return True

    def take(self, size):
        with self._lock:
            data = bytes(self._data[:size])
            del self._data[:size]
        return data + bytes(size - len(data))

    def clear(self):
        with self._lock:
            self._data.clear()

    @property
    def pending(self):
        with self._lock:
            return len(self._data)


class PCMResampler:
    def __init__(self, input_rate, output_rate):
        import soxr
        self.stream = soxr.ResampleStream(input_rate, output_rate, 1, dtype="int16", quality="HQ")

    def convert(self, pcm, final=False):
        import numpy as np
        if len(pcm) % 2:
            raise ValueError("PCM data must contain whole 16-bit samples")
        samples = np.frombuffer(pcm, dtype="<i2")
        return self.stream.resample_chunk(samples, last=final).astype("<i2", copy=False).tobytes()

    def clear(self):
        self.stream.clear()


class AudioDeviceError(RuntimeError):
    """Safe, fixed device message without any provider response content."""


class DuplexAudio:
    """Default-device capture/playback, opened once per Live connection.

    Headphone mode permits full duplex. Speaker-safe mode gates capture while
    playing speech. This is echo avoidance, not acoustic echo cancellation.
    """
    def __init__(self, headphones=True, device_in=None, device_out=None):
        self.headphones = headphones
        self.device_in, self.device_out = device_in, device_out
        self.capture = Queue(maxsize=12)
        self.output = PlaybackBuffer()
        self.input_stream = self.output_stream = None
        self.muted = False
        self.last_played = -1e9
        self.capture_dropped = 0
        self.callback_status = False
        self.input_resampler = self.output_resampler = None
        self.output_rate = 24000
        self._closed = False

    def open(self):
        import sounddevice as sd
        try:
            input_device = sd.query_devices(self.device_in, "input")
            output_device = sd.query_devices(self.device_out, "output")
            input_rate = int(input_device["default_samplerate"])
            try:
                sd.check_output_settings(device=self.device_out, channels=1, dtype="int16", samplerate=24000)
                self.output_rate = 24000
            except sd.PortAudioError:
                self.output_rate = int(output_device["default_samplerate"])
            self.input_resampler = PCMResampler(input_rate, 16000)
            self.output_resampler = PCMResampler(24000, self.output_rate)
            self.output.maximum = self.output_rate * 2 * 12
            self.input_stream = sd.RawInputStream(
                device=self.device_in, channels=1, dtype="int16", samplerate=input_rate,
                blocksize=max(160, input_rate // 50), callback=self._capture)
            self.output_stream = sd.RawOutputStream(
                device=self.device_out, channels=1, dtype="int16", samplerate=self.output_rate,
                blocksize=max(240, self.output_rate // 50), callback=self._play)
            self.output_stream.start()
            self.input_stream.start()
        except Exception:
            self.close()
            raise AudioDeviceError("Could not open the microphone or speakers. Check Windows microphone permissions and default audio devices.") from None

    def _capture(self, indata, frames, timing, status):
        self.callback_status |= bool(status)
        if self.muted or (not self.headphones and (self.output.pending or time.monotonic() - self.last_played < 0.35)):
            return
        try:
            self.capture.put_nowait(bytes(indata))
        except Full:
            self.capture_dropped += 1

    def _play(self, outdata, frames, timing, status):
        self.callback_status |= bool(status)
        if self.output.pending:
            self.last_played = time.monotonic()
        outdata[:] = self.output.take(frames * 2)

    def microphone_chunk(self):
        try:
            raw = self.capture.get_nowait()
        except Empty:
            return b""
        return self.input_resampler.convert(raw)

    def play(self, pcm):
        if self._closed:
            return
        converted = self.output_resampler.convert(pcm)
        if converted and not self.output.put(converted):
            raise AudioDeviceError("Speech playback fell behind. Queued speech was cleared; restart Live voice.")

    def flush_playback(self):
        if not self._closed:
            tail = self.output_resampler.convert(b"", final=True)
            if tail:
                self.output.put(tail)
            self.output_resampler = PCMResampler(24000, self.output_rate)

    @property
    def playing(self):
        return bool(self.output.pending or time.monotonic() - self.last_played < 0.15)

    def interrupt(self):
        self.output.clear()
        if self.output_resampler:
            self.output_resampler.clear()

    def clear_capture(self):
        while True:
            try:
                self.capture.get_nowait()
            except Empty:
                break

    def close(self):
        self._closed = True
        self.output.clear()
        for stream in (self.input_stream, self.output_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self.clear_capture()
