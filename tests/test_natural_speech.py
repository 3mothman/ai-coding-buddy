import asyncio
from contextlib import asynccontextmanager
import io
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import wave
from buddy.natural_speech import synthesize, NaturalSpeech
from unittest.mock import Mock


class NaturalSpeechTests(unittest.TestCase):
    def generate(self, interrupted=False):
        calls = []
        class Session:
            async def send_client_content(self, **kwargs):
                calls.append(kwargs)
            async def receive(self):
                for pcm, done in [(b'\x01\x00' * 100, False), (b'\x02\x00' * 200, True)]:
                    yield NS(server_content=NS(interrupted=interrupted, turn_complete=done,
                        model_turn=NS(parts=[NS(inline_data=NS(data=pcm, mime_type='audio/pcm;rate=24000'))])))
        @asynccontextmanager
        async def connect(**kwargs):
            self.assertNotIn('tools', kwargs['config'])
            yield Session()
        @asynccontextmanager
        async def client():
            yield NS(live=NS(connect=connect))
        with patch('google.genai.Client', return_value=NS(aio=client())):
            data = asyncio.run(synthesize('test-key', 'live-model', 'Aoede', 'Read both sentences. Finish the second one.'))
        self.assertEqual(len(calls), 1)
        return data

    def test_all_audio_chunks_are_buffered_into_complete_wave(self):
        with wave.open(io.BytesIO(self.generate()), 'rb') as wav:
            self.assertEqual(wav.getnframes(), 300)
            self.assertEqual(wav.getframerate(), 24000)
            self.assertEqual(wav.readframes(300), b'\x01\x00' * 100 + b'\x02\x00' * 200)

    def test_playback_starts_before_generation_finishes(self):
        speech = NS(stream=Mock(), started=False, done=False,
            queue=NS(pending=24000), rate=24000, speaking=Mock(), status=Mock())
        NaturalSpeech._pump(speech)
        speech.stream.start.assert_called_once()
        self.assertTrue(speech.started)
        self.assertFalse(speech.done)

    def test_short_buffer_waits_for_more_audio(self):
        speech = NS(stream=Mock(), started=False, done=False,
            queue=NS(pending=1000), rate=24000, speaking=Mock(), status=Mock())
        NaturalSpeech._pump(speech)
        speech.stream.start.assert_not_called()

    def test_interrupted_generation_is_not_played_as_complete(self):
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            self.generate(interrupted=True)
