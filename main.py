"""Einstiegspunkt der Desktop-Anwendung."""
import sys

def main():
    try:
        from PySide6.QtWidgets import QApplication
        from buddy.window import MainWindow
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith("PySide6"):
            print("PySide6 fehlt. Bitte zuerst installieren: py -m pip install -r requirements.txt")
            return 1
        raise
    app = QApplication(sys.argv)
    app.setApplicationName("AI Coding Buddy")
    window = MainWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
