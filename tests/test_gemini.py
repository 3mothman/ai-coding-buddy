"""Offline SDK-contract and integration tests. No real key, audio recording or paid calls."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
import json
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from google.genai import types
from PySide6.QtWidgets import QApplication

from buddy.analysis import Feedback, Snapshot, TutorError
from buddy.audio_io import PCMResampler, PlaybackBuffer, DuplexAudio
from buddy.gemini_analysis import GeminiTutor, validate_result, AnalysisResult, DEFAULT_FLASH, decode_response, safe_api_error
from buddy.live_voice import LiveVoice, TranscriptAccumulator, live_config
from buddy.orchestration import AssistancePolicy, LearningOrchestrator
from buddy.settings import Preferences, SettingsDialog
from buddy.window import MainWindow

class LessonVoiceTests(unittest.TestCase):
    def test_auto_start_requires_sound_consent_and_no_existing_session(self):
        from unittest.mock import Mock
        for consent, sound, running, expected in [(True, True, False, 1), (False, True, False, 0), (True, False, False, 0), (True, True, True, 0)]:
            window = SimpleNamespace(provider=GeminiTutor(api_key="test"), voice_consent=consent,
                sound_box=SimpleNamespace(isChecked=lambda: sound), voice=SimpleNamespace(running=running), toggle_live=Mock())
            MainWindow.start_lesson_voice(window)
            self.assertEqual(window.toggle_live.call_count, expected)


class ApiFailureTests(unittest.TestCase):
    def test_google_invalid_key_is_http_400(self):
        from google.genai.errors import ClientError
        error = ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
            "message": "private-key-and-code", "details": [{"reason": "API_KEY_INVALID"}]}})
        message = safe_api_error(error)
        self.assertIn("invalid-key", message)
        self.assertNotIn("private-key-and-code", message)

    def test_restricted_key_is_distinct(self):
        error = SimpleNamespace(code=403, details={"error": {"details": [{"reason": "SERVICE_DISABLED"}]}})
        self.assertIn("restricted-key", safe_api_error(error))

    def test_invalid_request_does_not_blame_key(self):
        message = safe_api_error(SimpleNamespace(code=400, details={}))
        self.assertIn("invalid-request", message)
        self.assertNotIn("invalid-key", message)

    def test_transport_timeout_and_server_errors(self):
        import httpx2
        self.assertIn("network-timeout", safe_api_error(httpx2.ReadTimeout("secret")))
        self.assertIn("network-transport", safe_api_error(httpx2.ConnectError("secret")))
        self.assertIn("HTTP 503", safe_api_error(SimpleNamespace(code=503)))

    def test_unknown_failures_never_echo_exception(self):
        message = safe_api_error(RuntimeError("secret-api-key"))
        self.assertIn("sdk-failure", message)
        self.assertNotIn("secret", message)
        self.assertIn("sdk-failure", safe_api_error(SimpleNamespace(details={"error": {"details": None}})))


REFERENCE = {
    "assignment_summary": "Find the greatest integer in an array.",
    "reference_summary": "Keep a candidate value and compare every remaining array value.",
    "concepts": ["arrays", "iteration", "conditions"],
    "objectives": [
        {"id": "array", "title": "Store the numbers", "evidence": "An initialized integer array exists."},
        {"id": "iteration", "title": "Visit each value", "evidence": "Every remaining element is visited, using any valid loop."},
        {"id": "comparison", "title": "Keep the greatest value", "evidence": "A candidate is updated only for a larger value."},
    ], "ambiguity": "Input source was not specified.",
}


def result(action="show_hint", message="What should happen at the last array index?", prepare=False):
    return {"reference": deepcopy(REFERENCE) if prepare else None,
        "student_progress": {"completed": [], "current_objective": "array"},
        "analysis": {"issue": "", "severity": "none", "confidence": 0.9, "line_start": 0, "line_end": 0},
        "intervention": {"action": action, "hint_level": 1, "message": message, "should_speak": True, "snippet": ""},
        "memory_summary": "The learner is working on storing the numbers."}


class FakeClient:
    calls = []
    response = result(prepare=True)
    failures = []

    def __init__(self, **kwargs):
        self.models = self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.failures:
            raise self.failures.pop(0)
        return SimpleNamespace(text=json.dumps(self.response))


class GeminiAnalysisTests(unittest.TestCase):
    def setUp(self):
        FakeClient.calls, FakeClient.failures = [], []
        FakeClient.response = result(prepare=True)

    def tutor(self):
        return GeminiTutor(api_key="test-key", client_factory=FakeClient, sleep=lambda _: None)

    def test_invalid_response_gets_one_corrective_retry(self):
        bad = result(prepare=True)
        bad["student_progress"]["completed"] = ["invented"]
        good = result(prepare=True)
        with patch.object(FakeClient, "generate_content", side_effect=[
            SimpleNamespace(text=json.dumps(bad)), SimpleNamespace(text=json.dumps(good))
        ]) as generate:
            feedback = self.tutor().analyze(Snapshot("task", "ref", "", reason="prepare"))
            self.assertEqual(feedback.structured["student_progress"]["completed"], [])
            self.assertEqual(generate.call_count, 2)
            self.assertIn("response_correction", json.loads(generate.call_args.kwargs["contents"]))

    def test_completed_header_moves_to_next_objective(self):
        reference = deepcopy(REFERENCE)
        reference["objectives"].insert(0, {"id": "header", "title": "Include header", "evidence": "stdio header present"})
        FakeClient.response = result("explain_concept", "Now let's store the numbers in an array.")
        FakeClient.response["student_progress"] = {"completed": ["header"], "current_objective": "array"}
        feedback = self.tutor().analyze(Snapshot("Find largest", "ref", "#include <stdio.h>", reason="check", reference_analysis=reference, current_objective="header"))
        self.assertEqual(feedback.structured["student_progress"]["current_objective"], "array")
        self.assertEqual(feedback.structured["student_progress"]["completed"], ["header"])

    def test_initial_reference_is_structured_and_uses_official_contract(self):
        snap = Snapshot("Find greatest", "reference", "", reason="prepare")
        feedback = self.tutor().analyze(snap)
        self.assertEqual(feedback.structured["reference"], REFERENCE)
        call = FakeClient.calls[0]
        self.assertEqual(call["model"], DEFAULT_FLASH)
        types.GenerateContentConfig.model_validate(call["config"])
        self.assertEqual(call["config"]["response_mime_type"], "application/json")
        self.assertIn("student_progress", call["config"]["response_json_schema"]["properties"])

    def test_student_array_progress_and_while_alternative_are_preserved(self):
        FakeClient.response = result("celebrate_progress", "Your loop visits each array value.")
        FakeClient.response["student_progress"] = {"completed": ["array", "iteration"], "current_objective": "comparison"}
        code = "int values[] = {1,2,3}; int i = 0; while (i < 3) { i++; }"
        feedback = self.tutor().analyze(Snapshot("Find greatest", "for reference", code, reference_analysis=REFERENCE))
        self.assertIn("iteration", feedback.structured["student_progress"]["completed"])
        sent = json.loads(FakeClient.calls[0]["contents"])
        self.assertEqual(sent["code"], code)
        self.assertIn("correct while loop", FakeClient.calls[0]["config"]["system_instruction"])

    def test_wrong_loop_condition_targets_student_line(self):
        FakeClient.response = result("highlight_error", "Line 2 can go past the last element. Which index is the last valid one?")
        FakeClient.response["analysis"] = {"issue": "array_bound", "severity": "logic", "confidence": 0.95, "line_start": 2, "line_end": 2}
        feedback = self.tutor().analyze(Snapshot("Find greatest", "ref", "int a[5];\nfor(int i=0;i<=5;i++) {}", reference_analysis=REFERENCE))
        self.assertEqual(feedback.action, "highlight_error")
        self.assertEqual(feedback.structured["analysis"]["line_start"], 2)

    def test_pause_can_remain_silent(self):
        FakeClient.response = result("stay_silent", "")
        feedback = self.tutor().analyze(Snapshot("", "ref", "int a[] = {1};", reason="auto", reference_analysis=REFERENCE))
        self.assertEqual(feedback.message, "")
        self.assertFalse(feedback.should_speak)

    def test_spoken_question_has_code_and_conversation_context(self):
        FakeClient.response = result("explain_concept", "That variable remembers the greatest value found so far.")
        self.tutor().analyze(Snapshot("Find greatest", "ref", "int largest = values[0];", reason="voice_question",
            reference_analysis=REFERENCE, current_objective="comparison", voice_question="Why do I need this variable?",
            conversation=({"role": "user", "text": "We already made the array."},)))
        sent = json.loads(FakeClient.calls[0]["contents"])
        self.assertIn("Why do I need", sent["voice_question"])
        self.assertIn("largest", sent["code"])
        self.assertTrue(sent["conversation"])

    def test_invalid_actions_ids_ranges_and_unrequested_code_are_rejected(self):
        snap = Snapshot("", "reference", "int a;", reference_analysis=REFERENCE)
        for modify in (
            lambda r: r["intervention"].update(action="overwrite_editor"),
            lambda r: r["student_progress"].update(completed=["invented"]),
            lambda r: r["analysis"].update(line_start=1, line_end=20),
            lambda r: r["intervention"].update(snippet="int answer=42;"),
            lambda r: r["intervention"].update(message="int main(void) { return 0; }"),
        ):
            data = result()
            modify(data)
            with self.assertRaises(TutorError):
                validate_result(data, snap)

    def test_transient_retries_are_bounded_and_keys_never_exposed(self):
        class Transient(Exception):
            code = 503
        FakeClient.failures = [Transient("secret test-key"), Transient("secret test-key")]
        with self.assertRaises(TutorError) as failure:
            self.tutor().analyze(Snapshot("", "ref", "", reason="prepare"))
        self.assertEqual(len(FakeClient.calls), 2)
        self.assertNotIn("secret", str(failure.exception))

    def test_reference_required_before_student_analysis(self):
        with self.assertRaises(TutorError):
            self.tutor().analyze(Snapshot("", "reference", "int a;"))
        self.assertFalse(FakeClient.calls)

    def test_sdk_parsed_result_does_not_require_text(self):
        self.assertEqual(decode_response(SimpleNamespace(parsed=result(prepare=True), text=None)), result(prepare=True))

    def test_unspecified_prompt_block_reason_is_not_a_block(self):
        response = types.GenerateContentResponse(prompt_feedback={"block_reason": "BLOCKED_REASON_UNSPECIFIED"})
        response.parsed = result(prepare=True)
        self.assertEqual(decode_response(response), result(prepare=True))

    def test_empty_truncated_and_invalid_json_have_different_diagnostics(self):
        for response, category in (
            (SimpleNamespace(text=None), "empty-output"),
            (SimpleNamespace(text='{', candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")]), "truncated"),
            (SimpleNamespace(text='not json'), "invalid-json"),
            (SimpleNamespace(text='[]'), "expected-object"),
        ):
            with self.assertRaises(TutorError) as error:
                decode_response(response)
            self.assertIn(category, str(error.exception))

    def test_fenced_json_is_accepted(self):
        fence = chr(96) * 3
        self.assertEqual(decode_response(SimpleNamespace(text=fence+'json\n'+json.dumps(result())+'\n'+fence)), result())

    def test_provider_filter_is_identified_without_exposing_text(self):
        with self.assertRaises(TutorError) as error:
            decode_response(SimpleNamespace(text="private code test-key", candidates=[SimpleNamespace(finish_reason="SAFETY")]))
        self.assertIn("filtered", str(error.exception))
        self.assertNotIn("test-key", str(error.exception))

    def test_truncated_generation_retries_once_with_larger_budget(self):
        class TruncatedClient(FakeClient):
            calls = []
            def generate_content(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    return SimpleNamespace(text=None, candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")])
                return SimpleNamespace(parsed=result(prepare=True), text=None)
        tutor = GeminiTutor(api_key="test", client_factory=TruncatedClient)
        self.assertTrue(tutor.analyze(Snapshot("", "ref", "", reason="prepare")).structured)
        self.assertEqual(len(TruncatedClient.calls), 2)
        self.assertGreater(TruncatedClient.calls[1]["config"]["max_output_tokens"], TruncatedClient.calls[0]["config"]["max_output_tokens"])
        self.assertEqual(TruncatedClient.calls[0]["config"]["thinking_config"]["thinking_level"], "LOW")

    def test_persistent_empty_output_does_not_retry_indefinitely(self):
        class EmptyClient(FakeClient):
            calls = []
            def generate_content(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(text=None)
        with self.assertRaises(TutorError) as error:
            GeminiTutor(api_key="test", client_factory=EmptyClient).analyze(Snapshot("", "ref", "", reason="prepare"))
        self.assertEqual(len(EmptyClient.calls), 2)
        self.assertIn("empty-output", str(error.exception))

    def test_progress_can_update_without_a_spoken_message(self):
        data = result("mark_step_completed", "")
        data["intervention"]["should_speak"] = False
        data["student_progress"]["completed"] = ["array"]
        parsed = validate_result(data, Snapshot("", "ref", "int a[]={1};", reference_analysis=REFERENCE))
        self.assertEqual(parsed.student_progress.completed, ["array"])
        self.assertFalse(parsed.intervention.should_speak)

    def test_spoken_question_cannot_leave_a_live_tool_waiting_in_silence(self):
        parsed = validate_result(result("stay_silent", ""), Snapshot(
            "", "ref", "int a;", reason="voice_question", reference_analysis=REFERENCE))
        self.assertEqual(parsed.intervention.action, "ask_question")
        self.assertTrue(parsed.intervention.should_speak)
        self.assertIn("which part", parsed.intervention.message)


class PolicyTests(unittest.TestCase):
    def test_inactivity_is_not_a_mandatory_hint(self):
        policy = AssistancePolicy()
        self.assertFalse(policy.can_analyze(24, 0, 1))
        self.assertTrue(policy.can_analyze(25, 0, 1))
        self.assertFalse(policy.should_deliver(Feedback("", action="stay_silent"), 25, automatic=True))

    def test_speech_settle_cooldown_duplicate_and_confidence(self):
        policy = AssistancePolicy(last_hint=0, last_voice_activity=44)
        feedback = Feedback("Check the last index.", structured=result())
        self.assertFalse(policy.should_deliver(feedback, 45, automatic=True))
        self.assertTrue(policy.should_deliver(feedback, 47, automatic=True))
        policy.messages.append(feedback.message)
        self.assertFalse(policy.should_deliver(feedback, 100, automatic=True))
        policy.messages.clear()
        feedback.structured["analysis"]["confidence"] = 0.4
        self.assertFalse(policy.should_deliver(feedback, 100, automatic=True))
        policy.listening = True
        self.assertFalse(policy.can_analyze(100, 0, 2))

    def test_silent_analysis_still_has_request_rate_limit(self):
        policy = AssistancePolicy(last_analysis=90)
        self.assertFalse(policy.can_analyze(95, 0, 3, minimum_idle=2))
        self.assertTrue(policy.can_analyze(101, 0, 3, minimum_idle=2))


class AudioTests(unittest.TestCase):
    def test_streaming_resamples_48k_and_44k_to_correct_16k_duration(self):
        for rate in (48000, 44100):
            resampler = PCMResampler(rate, 16000)
            signal = (np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * 12000).astype("<i2")
            output = b""
            for block in np.array_split(signal, 50):
                output += resampler.convert(block.tobytes())
            output += resampler.convert(b"", final=True)
            self.assertEqual(len(output), 16000 * 2)
            self.assertGreater(np.max(np.frombuffer(output, dtype="<i2")), 10000)

    def test_playback_is_bounded_and_cleared_on_interruption(self):
        buffer = PlaybackBuffer(10)
        self.assertTrue(buffer.put(b"123456"))
        self.assertEqual(buffer.take(4), b"1234")
        buffer.clear()
        self.assertEqual(buffer.take(4), b"\0" * 4)
        self.assertFalse(buffer.put(b"x" * 12))
        self.assertEqual(buffer.pending, 0)

    def test_speaker_safe_capture_is_gated_while_playing(self):
        audio = DuplexAudio(headphones=False)
        audio.output.put(b"12")
        audio._capture(b"1234", 2, None, False)
        self.assertTrue(audio.capture.empty())
        audio.headphones = True
        audio._capture(b"1234", 2, None, False)
        self.assertEqual(audio.capture.get_nowait(), b"1234")


class FakeAudio:
    def __init__(self, **_):
        self.pcm = []
        self.output = PlaybackBuffer()
        self.muted = False
        self.closed = False
        self.sent = False

    def open(self):
        pass

    def close(self):
        self.closed = True

    def play(self, data):
        self.pcm.append(data)

    def flush_playback(self):
        pass

    def interrupt(self):
        self.pcm.clear()

    def clear_capture(self):
        pass

    def microphone_chunk(self):
        if self.sent:
            return b""
        self.sent = True
        return b"\0" * 640

    @property
    def playing(self):
        return False


class LiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.voice = LiveVoice(audio_factory=FakeAudio)
        self.voice._audio = FakeAudio()
        self.voice._authorized_output = True
        self.transcripts = []
        self.voice.transcript.connect(lambda *args: self.transcripts.append(args))

    def event(self, **kwargs):
        self.voice.process_event(types.LiveServerMessage.model_validate(kwargs))

    def test_live_config_uses_supported_sdk_fields(self):
        config = types.LiveConnectConfig.model_validate(live_config())
        self.assertIsNotNone(config.input_audio_transcription)
        self.assertIsNotNone(config.output_audio_transcription)
        self.assertIsNotNone(config.session_resumption)
        self.assertIsNotNone(config.context_window_compression)
        self.assertEqual(config.tools[0].function_declarations[0].name, "ask_code_tutor")

    def test_audio_without_authoritative_teaching_action_is_suppressed(self):
        self.voice._authorized_output = False
        self.event(server_content={"model_turn": {"parts": [{"inline_data": {
            "data": b"12", "mime_type": "audio/pcm;rate=24000"}}]},
            "output_transcription": {"text": "An unapproved diagnosis."}})
        self.assertFalse(self.voice._audio.pcm)
        self.assertFalse(self.transcripts)

    def test_one_event_processes_all_audio_parts_and_both_transcripts(self):
        self.event(server_content={"model_turn": {"parts": [
            {"inline_data": {"data": b"12", "mime_type": "audio/pcm;rate=24000"}},
            {"inline_data": {"data": b"34", "mime_type": "audio/pcm;rate=24000"}}]},
            "input_transcription": {"text": "Why this variable?", "finished": True},
            "output_transcription": {"text": "It remembers the largest value."}})
        self.assertEqual(self.voice._audio.pcm, [b"12", b"34"])
        self.assertTrue(any(x[0] == "user" and x[2] for x in self.transcripts))
        self.assertTrue(any(x[0] == "assistant" for x in self.transcripts))

    def test_barge_in_clears_audio_and_marks_received_text_as_interrupted(self):
        self.event(server_content={"model_turn": {"parts": [{"inline_data": {
            "data": b"12", "mime_type": "audio/pcm;rate=24000"}}]},
            "output_transcription": {"text": "An explanation that has not finished playing."}})
        self.event(server_content={"interrupted": True})
        self.assertFalse(self.voice._audio.pcm)
        self.assertTrue(self.transcripts[-1][3])

    def test_code_revision_clears_old_speech_and_drops_old_chunks(self):
        self.voice._generating = True
        self.voice._output.feed("Old hint")
        self.voice._invalidate_output()
        self.event(server_content={"model_turn": {"parts": [{"inline_data": {
            "data": b"old", "mime_type": "audio/pcm;rate=24000"}}]}})
        self.assertFalse(self.voice._audio.pcm)

    def test_transcript_fragments_do_not_duplicate_cumulative_updates(self):
        text = TranscriptAccumulator()
        self.assertEqual(text.feed("Why"), "Why")
        self.assertEqual(text.feed("Why this", interim=True), "Why this")
        self.assertEqual(text.feed("Why this variable?"), "Why this variable?")
        self.assertEqual(text.feed("Why this variable?"), "Why this variable?")

    def test_tool_call_and_cancellation_are_not_arbitrary_editor_actions(self):
        questions, cancelled = [], []
        self.voice.tool_question.connect(lambda *args: questions.append(args))
        self.voice.tool_cancelled.connect(cancelled.append)
        self.event(tool_call={"function_calls": [{"id": "a", "name": "ask_code_tutor", "args": {"question": "Why this variable?"}}]})
        self.assertEqual(questions, [("a", "Why this variable?")])
        self.event(tool_call_cancellation={"ids": ["a"]})
        self.assertEqual(cancelled, ["a"])
        self.assertFalse(self.voice._pending_tools)

    def test_microphone_is_muted_until_learner_talks(self):
        self.assertTrue(self.voice._mute)
        self.voice.mute(False)
        self.assertFalse(self.voice._mute)
        self.voice.mute(True)
        self.assertTrue(self.voice._audio.muted)

    def test_mock_live_session_streams_audio_and_sends_authoritative_tool_result(self):
        sent = []
        voice = self.voice
        class Session:
            async def send_realtime_input(self, **kwargs):
                sent.append(("audio", kwargs))

            async def send_client_content(self, **kwargs):
                sent.append(("context", kwargs))

            async def send_tool_response(self, **kwargs):
                sent.append(("tool", kwargs))

        async def run():
            voice.mute(False)  # learner holds the talk button
            voice._pending_tools.add("q1")
            voice._commands.append(("tool", {"id": "q1", "message": "It keeps the greatest value.", "stale": False}, 0))
            tasks = [asyncio.create_task(voice._send_audio(Session())), asyncio.create_task(voice._send_commands(Session()))]
            await asyncio.sleep(0.08)
            voice.stop_event.set()
            await asyncio.gather(*tasks)
        asyncio.run(run())
        self.assertTrue(any(kind == "audio" and "audio" in data and data["audio"].mime_type == "audio/pcm;rate=16000" for kind, data in sent))
        response = next(data for kind, data in sent if kind == "tool")["function_responses"][0]
        self.assertEqual(response.response["approved_message"], "It keeps the greatest value.")

    def test_stale_tool_result_does_not_authorize_audio(self):
        sent = []
        voice = self.voice
        voice._authorized_output = False
        voice._revision = 2
        class Session:
            async def send_tool_response(self, **kwargs):
                sent.append(kwargs)
                voice.stop_event.set()
        async def run():
            voice._pending_tools.add("old")
            voice._commands.append(("tool", {"id": "old", "message": "Outdated advice", "stale": False}, 1))
            await voice._send_commands(Session())
        asyncio.run(run())
        self.assertFalse(voice._authorized_output)
        self.assertEqual(sent[0]["function_responses"][0].response["status"], "stale")

    def test_controlled_reconnect_uses_resumption_handle_and_closes_devices(self):
        voice = self.voice
        connections, audios = [], []
        class Session:
            def __init__(self, number):
                self.number = number
            async def send_realtime_input(self, **_):
                pass
            async def send_client_content(self, **_):
                pass
            async def receive(self):
                if self.number == 1:
                    yield types.LiveServerMessage(session_resumption_update={"resumable": True, "new_handle": "resume-test"})
                    raise ConnectionError("simulated outage")
                while True:
                    await asyncio.sleep(0.005)
                    if False:
                        yield None
        class Client:
            def __init__(self, **_):
                self.aio = self
                self.live = self
            async def __aenter__(self):
                return self
            async def __aexit__(self, *_):
                pass
            @asynccontextmanager
            async def connect(self, **kwargs):
                connections.append(kwargs)
                yield Session(len(connections))
        def audio_factory(**_):
            audio = FakeAudio()
            audios.append(audio)
            return audio
        voice.client_factory = Client
        voice.audio_factory = audio_factory
        real_sleep = asyncio.sleep
        async def quick_sleep(seconds):
            await real_sleep(min(seconds, 0.005))
        async def run():
            with patch("buddy.live_voice.asyncio.sleep", quick_sleep):
                task = asyncio.create_task(voice._run("test", "test-live", "Aoede", "English", True))
                for _ in range(100):
                    if len(connections) == 2:
                        break
                    await real_sleep(0.005)
                voice.stop_event.set()
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        asyncio.run(run())
        self.assertEqual(len(connections), 2)
        self.assertEqual(connections[1]["config"]["session_resumption"]["handle"], "resume-test")
        self.assertTrue(all(audio.closed for audio in audios))


class GeminiQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate())

    def test_reference_analysis_finishes_before_empty_practice_view_opens(self):
        gate = threading.Event()
        class Gated(FakeClient):
            response = result("explain_concept", "Let's find the greatest number, one step at a time.", prepare=True)
            failures = []
            def generate_content(self, **kwargs):
                gate.wait(2)
                return super().generate_content(**kwargs)
        with patch("buddy.window.load_preferences", return_value=Preferences(sound=False)):
            window = MainWindow()
        window.provider = GeminiTutor(api_key="test", client_factory=Gated)
        window.reference_input.setPlainText("int main(void) { return 0; }")
        window.start_learning()
        self.assertEqual(window.pages.currentIndex(), 0)
        self.assertFalse(window.start_button.isEnabled())
        gate.set()
        self.wait_for(lambda: window.pages.currentIndex() == 1)
        self.assertEqual(window.editor.toPlainText(), "")
        self.assertEqual(window.controller.memory.reference, REFERENCE)
        window.close()

    def test_orchestrator_silent_result_updates_memory_but_emits_no_hint(self):
        controller = LearningOrchestrator(clock=lambda: 100)
        controller.memory.reference = REFERENCE
        controller.snapshot = Snapshot("", "", "", reason="auto", revision=controller.revision)
        feedback = Feedback("", action="stay_silent", structured=result("stay_silent", ""))
        received = []
        controller.result.connect(received.append)
        controller._accept(feedback)
        self.assertFalse(received)
        self.assertEqual(controller.memory.objective, "array")
        controller.shutdown()

    def test_invalidated_analysis_cannot_update_learning_memory(self):
        controller = LearningOrchestrator()
        controller.snapshot = Snapshot("", "", "", reason="prepare", revision=controller.revision)
        controller.invalidate()
        controller._accept(Feedback("old", structured=result(prepare=True)))
        self.assertIsNone(controller.memory.reference)
        controller.shutdown()

    def test_gemini_audio_requires_separate_session_consent(self):
        dialog = SettingsDialog(Preferences(provider="gemini", model=DEFAULT_FLASH), "test", True)
        self.assertFalse(dialog.voice_consent.isChecked())
        dialog.voice_consent.setChecked(True)
        dialog.model.setText("another-flash")
        self.assertFalse(dialog.voice_consent.isChecked())
        dialog.close()

    def test_reference_failure_is_visible_on_start_page(self):
        with patch("buddy.window.load_preferences", return_value=Preferences(sound=False)):
            window = MainWindow()
        window._preparing = True
        window.start_button.setEnabled(False)
        window.receive_error("Gemini access denied.")
        self.assertEqual(window.pages.currentIndex(), 0)
        self.assertTrue(window.start_button.isEnabled())
        self.assertIn("access denied", window.preparation_status.text())
        window.close()

    def test_analysis_highlight_never_edits_code_and_is_cleared_by_typing(self):
        with patch("buddy.window.load_preferences", return_value=Preferences(sound=False)):
            window = MainWindow()
        code = "int values[4];\nfor(int i=0;i<=4;i++) {}"
        window.editor.setPlainText(code)
        window.editor.set_analysis_range(2, 2, "array_bound")
        self.assertEqual(window.editor.toPlainText(), code)
        self.assertEqual(len(window.editor._analysis_selections), 1)
        window.editor.insertPlainText(" ")
        self.assertFalse(window.editor._analysis_selections)
        window.editor.document().setModified(False)
        window.close()


if __name__ == "__main__":
    unittest.main()
