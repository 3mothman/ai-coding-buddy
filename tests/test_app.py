import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from buddy.window import MainWindow
from buddy.session import read_reference

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.editor.document().setModified(False)
        self.window.close()

    def test_start_keeps_reference_out_of_editor(self):
        self.assertFalse(self.window.start_button.isEnabled())
        self.window.reference_input.setPlainText("int main(void) { return 0; }")
        self.window.start_button.click()
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.assertEqual(self.window.editor.toPlainText(), "")
        self.assertIn("main", self.window.session.reference)

    def test_cancel_preserves_work(self):
        self.window.reference_input.setPlainText("int main(void) {}")
        self.window.start_learning()
        self.window.editor.insertPlainText("unfinished")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.window.new_exercise()
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.assertEqual(self.window.editor.toPlainText(), "unfinished")

    def test_save_only_student_code(self):
        self.window.reference_input.setPlainText("reference")
        self.window.start_learning()
        self.window.editor.insertPlainText("student")
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "result.c")
            with patch("buddy.window.QFileDialog.getSaveFileName", return_value=(path, "")):
                self.assertTrue(self.window.save_code())
            self.assertEqual(Path(path).read_text(encoding="utf-8"), "student")
        self.assertFalse(self.window.editor.document().isModified())

    def test_import_encodings_and_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.c"
            path.write_bytes("// Grüße".encode("cp1252"))
            self.assertEqual(read_reference(str(path)), "// Grüße")
            path.write_bytes(b"\xef\xbb\xbfint main(void) {}")
            self.assertTrue(read_reference(str(path)).startswith("int"))
            path.write_bytes(b"x" * 1_000_001)
            with self.assertRaises(ValueError):
                read_reference(str(path))

    def test_character_renders(self):
        self.window.show()
        self.app.processEvents()
        self.assertFalse(self.window.grab().isNull())

if __name__ == "__main__":
    unittest.main()
