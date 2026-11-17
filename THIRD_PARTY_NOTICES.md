# Third-party components

The Gemini upgrade additionally uses google-genai (Apache-2.0), Pydantic (MIT),
python-sounddevice/PortAudio, NumPy (BSD), and Python-SoXR/libsoxr. Their installed
license notices are copied into the portable package. Consult the bundled license
texts for the exact terms and retained third-party notices.

Project links:
https://github.com/googleapis/python-genai
https://github.com/spatialaudio/python-sounddevice
https://numpy.org/doc/stable/license.html
https://github.com/dofuuz/python-soxr

AI Coding Buddy uses Python, Qt for Python (PySide6 and Shiboken6), and Qt.
Their original copyrights and license terms remain applicable.

- Python: https://docs.python.org/3/license.html
- Qt for Python licensing: https://doc.qt.io/qtforpython-6/licenses.html
- Qt source and license information: https://code.qt.io/
- PyInstaller and its bootloader exception: https://pyinstaller.org/en/stable/license.html

The Windows build copies the installed PySide6 and Shiboken license files into
the portable package's licenses directory. Qt libraries remain separate DLLs in
the portable folder. Keep the entire folder and its notices together.

Project source: https://github.com/3mothman/ai-coding-buddy

Unmodified LGPL/GPL license texts are included under licenses/Qt, copied from
https://github.com/pyside/pyside-setup/tree/dev/LICENSES.
