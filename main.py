"""Launch the desktop app, or perform a noninteractive packaged smoke test."""
import sys

def main():
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from buddy.window import MainWindow
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith("PySide6"):
            print("PySide6 is missing. Run Setup.bat or install requirements.txt first.")
            return 1
        raise
    app = QApplication(sys.argv)
    app.setApplicationName("AI Coding Buddy")
    app.setOrganizationName("AI Coding Buddy")
    window = MainWindow()
    if "--smoke-test" in sys.argv:
        window.speech.set_enabled(False)
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        window.show()
        app.processEvents()
        if window.grab().isNull():
            return 1
        window.close()
        return 0
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
