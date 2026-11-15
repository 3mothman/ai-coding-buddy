"""Sitzungsdaten bleiben ausschließlich im Arbeitsspeicher."""
from dataclasses import dataclass
from pathlib import Path

@dataclass
class LearningSession:
    task: str = ""
    reference: str = ""

def read_reference(path: str) -> str:
    source = Path(path)
    if source.suffix.lower() not in {".c", ".txt"}:
        raise ValueError("Bitte eine .c- oder .txt-Datei auswählen.")
    if source.stat().st_size > 1_000_000:
        raise ValueError("Die Datei ist zu groß. Erlaubt sind maximal 1 MB.")
    data = source.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")
