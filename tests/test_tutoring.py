"""Behavior tests using a local mock provider; no paid API or credentials."""
import json
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from buddy.analysis import (
    Snapshot, Feedback, DemoTutor, ChatCompletionsTutor, TutorError,
    concepts, issue_signature, parse_feedback, validate_endpoint, short_message,
)
from buddy.controller import TutorController
from buddy.editor import CodeEditor
from buddy.settings import Preferences, save_preferences, load_preferences, SettingsDialog
from buddy.window import MainWindow

class AnalysisTests(unittest.TestCase):
    def test_screenshot_unfinished_array_never_skips_to_loop(self):
        code = "#include<stdio.h>\n\nint numbers[]=S"
        for tutor in (DemoTutor(), ChatCompletionsTutor("http://localhost:1/v1", "test")):
            result = tutor.analyze(Snapshot("Find largest", "", code, reason="check", cursor_line=3))
            self.assertIn("Line 3", result.message)
            self.assertIn("not finished", result.message)
            self.assertNotIn("loop", result.message)
            self.assertLessEqual(len(result.message.split()), 55)
            self.assertFalse(result.complete)

    def test_short_messages_end_at_a_sentence(self):
        text = "Check this line first. " + "Next consider the condition. " * 30
        result = short_message(text)
        self.assertLessEqual(len(result.split()), 55)
        self.assertTrue(result.endswith("."))

    def test_strings_and_comments_are_not_code(self):
        self.assertEqual(concepts('// for (int i=0;) {}\n"while ([)"'), [])
        self.assertEqual(issue_signature('puts("}"); /* [ */'), "")

    def test_delimiter_checks(self):
        self.assertEqual(issue_signature("int main() {"), "open-delimiter")
        self.assertEqual(issue_signature("if (x]"), "unmatched-delimiter")
        self.assertEqual(issue_signature("int main() {}"), "")

    def test_demo_never_claims_correctness(self):
        for code in ("", "int main(void) { return 0; }", "for (;;)"):
            feedback = DemoTutor().analyze(Snapshot("", code, code, reason="review"))
            self.assertFalse(feedback.complete)
            self.assertIn("cannot verify", feedback.message)

    def test_hint_levels_and_explicit_example(self):
        tutor = DemoTutor()
        messages = [tutor.analyze(Snapshot("", "", "", level=level)).message for level in range(1, 5)]
        self.assertEqual(len(set(messages)), 4)
        self.assertFalse(tutor.analyze(Snapshot("", "", "", level=5)).snippet)
        self.assertTrue(tutor.analyze(Snapshot("", "", "", level=5, reason="example")).snippet)

    def test_examples_hidden_without_explicit_request(self):
        result = parse_feedback(json.dumps({"message": "Consider the stopping condition.", "snippet": "int secret = 42;"}), Snapshot("", "", ""))
        self.assertEqual(result.snippet, "")

    def test_natural_explanation_allows_semicolon(self):
        result = parse_feedback(json.dumps({"message": "This header declares output functions; add it before the entry point."}), Snapshot("", "", ""))
        self.assertIn("header", result.message)

    def test_c_explanations_are_allowed(self):
        text = "Start with #include <stdio.h>: it declares printf(). Then main() is the entry point; braces { and } mark its body."
        result = parse_feedback(json.dumps({"message": text, "state": "friendly", "summary": None, "plan": None}), Snapshot("", "", "", reason="start"))
        self.assertEqual(result.message, text)
        self.assertEqual(result.state, "explaining")

    def test_errors_have_diagnostic_categories(self):
        for content, category in [("not json", "invalid-json"), ("[]", "expected-object"), ("{}", "missing-message"), (None, "empty-content")]:
            with self.assertRaises(TutorError) as failure:
                parse_feedback(content, Snapshot("", "", ""))
            self.assertIn(category, str(failure.exception))

    def test_reference_grounded_intro(self):
        result = DemoTutor().analyze(Snapshot("Print a greeting", '#include <stdio.h>\nint main(void) { puts("Hi"); }', "", reason="start"))
        self.assertIn("stdio.h", result.message)
        self.assertIn("declares", result.message)

    def test_full_solution_rejected(self):
        for response in ({"message": "int main() { return 0; }"},
                         {"message": "Try this.", "snippet": "int main() { return 0; }"}):
            with self.assertRaises(TutorError):
                parse_feedback(json.dumps(response), Snapshot("", "int main() { return 0; }", "", reason="example"))

    def test_review_completion_is_explicit_and_provisional(self):
        response = json.dumps({"message": "Your reasoning is consistent.", "complete": True})
        self.assertFalse(parse_feedback(response, Snapshot("", "", "int x;", reason="help")).complete)
        self.assertFalse(parse_feedback(response, Snapshot("", "", "", reason="review")).complete)
        self.assertTrue(parse_feedback(response, Snapshot("", "", "int x;", reason="review")).complete)

    def test_invalid_schema_and_oversized_prose(self):
        for value in ("[]", "not json", '{"message":42}', json.dumps({"message": "x" * 1801})):
            with self.assertRaises(TutorError):
                parse_feedback(value, Snapshot("", "", ""))

    def test_https_and_localhost_only(self):
        self.assertEqual(validate_endpoint("http://127.0.0.1:1234/v1/"), "http://127.0.0.1:1234/v1")
        for endpoint in ("http://example.com/v1", "https://user:key@example.com/v1", "https://example.com/v1?key=secret", "file:///tmp"):
            with self.assertRaises(ValueError):
                validate_endpoint(endpoint)

    def test_preferences_do_not_contain_code_consent_or_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            save_preferences(Preferences("https://example.com/v1", "test", False, False), path)
            self.assertEqual(set(json.loads(path.read_text())), {"endpoint", "model", "sound", "automatic"})
            self.assertFalse(load_preferences(path).sound)
            path.write_text("broken")
            self.assertEqual(load_preferences(path), Preferences())

class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = []
        cls.status = 200
        cls.response = {}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                cls.requests.append((self.path, json.loads(raw), self.headers.get("Authorization")))
                cls.last_agent = self.headers.get("User-Agent", "")
                self.send_response(cls.status)
                if cls.status == 302:
                    self.send_header("Location", "/stolen")
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(cls.response).encode())
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        type(self).requests.clear()
        type(self).status = 200
        type(self).response = {"choices": [{"message": {"content": json.dumps({
            "message": "What happens at the last index?", "state": "thinking",
            "plan": ["iteration", "boundary cases"], "complete": False,
        })}}]}

    def test_real_http_request_and_response(self):
        result = ChatCompletionsTutor(self.endpoint, "test-model", "test-key").analyze(Snapshot("Find a maximum", "reference", "student", level=3))
        self.assertEqual(result.state, "thinking")
        path, payload, auth = self.requests[0]
        self.assertTrue(self.last_agent.startswith("AI-Coding-Buddy/"))
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(auth, "Bearer test-key")
        context = json.loads(payload["messages"][1]["content"])
        self.assertEqual(context["code"], "student")
        self.assertEqual(context["level"], 3)
        self.assertIn("alternative", payload["messages"][0]["content"])

    def test_http_provider_c_explanation_reaches_tutor(self):
        type(self).response = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"message": "We will use #include <stdio.h> for printf(). Next comes main(), the starting point.", "plan": ["headers", "main()"], "snippet": None})}}]}
        result = ChatCompletionsTutor(self.endpoint, "test").analyze(Snapshot("", "", "", reason="start"))
        self.assertIn("stdio.h", result.message)

    def test_truncated_response_has_specific_error(self):
        type(self).response = {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}
        with self.assertRaises(TutorError) as failure:
            ChatCompletionsTutor(self.endpoint, "test").analyze(Snapshot("", "", ""))
        self.assertIn("truncated", str(failure.exception))

    def test_error_does_not_leak_response_or_key(self):
        type(self).status = 401
        type(self).response = {"error": "sensitive-code test-key"}
        with self.assertRaises(TutorError) as failure:
            ChatCompletionsTutor(self.endpoint, "test", "test-key").analyze(Snapshot("", "", ""))
        self.assertIn("Authentication", str(failure.exception))
        self.assertNotIn("test-key", str(failure.exception))

    def test_model_permission_error_is_specific(self):
        type(self).status = 403
        type(self).response = {"error": {"code": "model_permission_blocked_project", "message": "secret-key"}}
        with self.assertRaises(TutorError) as failure:
            ChatCompletionsTutor(self.endpoint, "test").analyze(Snapshot("", "", ""))
        self.assertIn("project permissions", str(failure.exception))
        self.assertNotIn("secret-key", str(failure.exception))

    def test_redirect_not_followed(self):
        type(self).status = 302
        with self.assertRaises(TutorError):
            ChatCompletionsTutor(self.endpoint, "test", "key").analyze(Snapshot("", "", ""))
        self.assertEqual(len(self.requests), 1)

    def test_large_exercise_never_sent(self):
        with self.assertRaises(TutorError):
            ChatCompletionsTutor(self.endpoint, "test").analyze(Snapshot("", "x" * 60001, ""))
        self.assertEqual(self.requests, [])

class QtBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate())

    def test_background_results_for_old_code_are_discarded(self):
        gate = threading.Event()
        class Slow:
            def analyze(self, snap):
                gate.wait(2)
                return Feedback(snap.code)
        controller = TutorController()
        received = []
        controller.result.connect(lambda result: received.append(result.message))
        controller.request(Slow(), Snapshot("", "", "old"))
        controller.invalidate()
        gate.set()
        self.wait_for(lambda: controller.active is None)
        self.assertEqual(received, [])
        controller.shutdown()

    def test_only_newest_pending_request_runs(self):
        gate = threading.Event()
        seen = []
        class Provider:
            def analyze(self, snap):
                seen.append(snap.code)
                gate.wait(2)
                return Feedback(snap.code)
        controller = TutorController()
        received = []
        controller.result.connect(lambda result: received.append(result.message))
        provider = Provider()
        controller.request(provider, Snapshot("", "", "first"))
        controller.request(provider, Snapshot("", "", "obsolete"))
        controller.request(provider, Snapshot("", "", "latest"))
        gate.set()
        self.wait_for(lambda: controller.active is None)
        self.assertEqual(seen, ["first", "latest"])
        self.assertEqual(received, ["latest"])
        controller.shutdown()

    def test_shutdown_ignores_late_result(self):
        gate = threading.Event()
        class Provider:
            def analyze(self, snap):
                gate.wait(2)
                return Feedback("late")
        controller = TutorController()
        received = []
        controller.result.connect(received.append)
        controller.request(Provider(), Snapshot("", "", ""))
        controller.shutdown()
        gate.set()
        self.wait_for(lambda: controller.active is None)
        self.assertEqual(received, [])

    def test_indentation_and_undo(self):
        editor = CodeEditor()
        editor.insertPlainText("    if (ok) {")
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        editor.keyPressEvent(event)
        self.assertTrue(editor.toPlainText().endswith("\n        "))
        editor.undo()
        self.assertEqual(editor.toPlainText(), "    if (ok) {")
        editor.deleteLater()

    def test_multiline_comment_highlighter(self):
        editor = CodeEditor()
        editor.setPlainText('/* comment\nstill comment */\nint value = 3;')
        editor.highlighter.rehighlight()
        self.assertEqual(editor.document().firstBlock().userState(), 1)
        self.assertEqual(editor.document().firstBlock().next().userState(), 0)
        self.assertGreater(len(editor.document().lastBlock().layout().formats()), 0)
        editor.deleteLater()

    def test_changing_destination_revokes_consent(self):
        dialog = SettingsDialog(Preferences("https://example.com/v1", "model"), "secret", True)
        self.assertTrue(dialog.consent.isChecked())
        dialog.endpoint.setText("https://other.example/v1")
        self.assertFalse(dialog.consent.isChecked())
        dialog.close()

    def test_manual_check_sends_current_line_and_changes(self):
        with patch("buddy.window.load_preferences", return_value=Preferences(sound=False, automatic=True)), patch("buddy.window.save_preferences"):
            window = MainWindow()
            self.assertFalse(window.auto_box.isChecked())
            window.reference_input.setPlainText("int main(void) { return 0; }")
            with patch.object(window.controller, "request") as request:
                window.start_learning()
                window.editor.insertPlainText("#include <stdio.h>\nint numbers[]=S")
                window.check_button.click()
                snap = request.call_args.args[1]
                self.assertEqual(snap.reason, "check")
                self.assertEqual(snap.cursor_line, 2)
                self.assertIn(2, snap.changed_lines)
                self.assertEqual(snap.code, window.editor.toPlainText())
                window.receive_feedback(Feedback("Line 2 is not finished yet."))
                window.editor.insertPlainText(";")
                window.check_button.click()
                self.assertEqual(request.call_args.args[1].previous_checked_code, snap.code)
            window.editor.document().setModified(False)
            window.close()

    def test_auto_pause_and_demo_default(self):
        with patch("buddy.window.load_preferences", return_value=Preferences(sound=False)), patch("buddy.window.save_preferences"):
            window = MainWindow()
            self.assertIsInstance(window.provider, DemoTutor)
            window.reference_input.setPlainText("int main(void) { return 0; }")
            window.start_learning()
            window.auto_box.setChecked(True)
            window.editor.insertPlainText("int value")
            self.assertEqual(window.pause_timer.interval(), 25000)
            self.assertTrue(window.pause_timer.isActive())
            window.auto_box.setChecked(False)
            self.assertFalse(window.pause_timer.isActive())
            with patch.object(window, "ask") as ask:
                window.idle_hint()
                ask.assert_not_called()
            window.editor.document().setModified(False)
            window.close()

    def test_idle_cooldown_and_single_hint_for_unchanged_code(self):
        with patch("buddy.window.load_preferences", return_value=Preferences(sound=False)), patch("buddy.window.save_preferences"):
            window = MainWindow()
            window.reference_input.setPlainText("int main(void) {}")
            window.start_learning()
            window.auto_box.setChecked(True)
            window.editor.insertPlainText("int x")
            with patch.object(window, "ask") as ask:
                window.last_message_time = time.monotonic()
                window.idle_hint()
                ask.assert_not_called()
                window.last_message_time = time.monotonic() - 60
                window.idle_hint()
                window.idle_hint()
                self.assertEqual(ask.call_count, 1)
            window.editor.document().setModified(False)
            window.close()

if __name__ == "__main__":
    unittest.main()
