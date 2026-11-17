"""Create a portable Windows folder with Qt, speech plugins and notices."""
from pathlib import Path
import importlib.metadata
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    if sys.platform != "win32":
        raise SystemExit("Build the Windows application on Windows.")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--windowed", "--onedir", "--name", "AI-Coding-Buddy",
        "--hidden-import", "PySide6.QtTextToSpeech",
        "--collect-all", "google.genai",
        "--collect-all", "soxr",
        "--collect-all", "_sounddevice_data",
        "--copy-metadata", "google-genai",
        "--copy-metadata", "sounddevice",
        "--collect-data", "certifi",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtPdf",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        str(ROOT / "main.py"),
    ], cwd=ROOT, check=True)
    output = ROOT / "dist" / "AI-Coding-Buddy"
    # Qt 6.12 uses the Windows ICU API. A similarly named ICU DLL from a
    # developer tool on PATH can have incompatible, version-suffixed exports.
    # Let supported Windows 10/11 systems provide their own ICU instead.
    internal = (output / "_internal").resolve()
    if not internal.is_relative_to(output.resolve()):
        raise RuntimeError("Unexpected bundle path")
    for name in ("icuuc.dll", "icudt78.dll"):
        (internal / name).unlink(missing_ok=True)
    for name in ("README.md", "THIRD_PARTY_NOTICES.md", "GEMINI_UPGRADE.md", "VERIFICATION.md"):
        shutil.copy2(ROOT / name, output / name)
    shutil.copytree(ROOT / "licenses", output / "licenses", dirs_exist_ok=True)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, output / "licenses" / "Python.txt")
    for package in ("PySide6-Essentials", "PySide6-Addons", "shiboken6", "PyInstaller", "google-genai", "sounddevice", "numpy", "soxr", "pydantic"):
        distribution = importlib.metadata.distribution(package)
        for entry in distribution.files or []:
            if "licenses" in entry.parts:
                source = Path(distribution.locate_file(entry))
                if source.is_file():
                    relative = Path(*entry.parts[entry.parts.index("licenses") + 1:])
                    target = output / "licenses" / package / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    subprocess.run([str(output / "AI-Coding-Buddy.exe"), "--smoke-test"], check=True, timeout=60)
    shutil.make_archive(str(ROOT / "dist" / "AI-Coding-Buddy-Windows"), "zip", output.parent, output.name)
    print("Portable package:", output.parent / "AI-Coding-Buddy-Windows.zip")

if __name__ == "__main__":
    main()
