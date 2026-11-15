"""Exercise data lives in memory unless the user explicitly saves their code."""
from dataclasses import dataclass
from pathlib import Path

@dataclass
class LearningSession:
    task: str = ""
    reference: str = ""

def read_reference(path: str) -> str:
    source = Path(path)
    if source.suffix.lower() not in {".c", ".txt"}:
        raise ValueError("Choose a .c or .txt file.")
    with source.open("rb") as stream:
        data = stream.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError("The file is too large. The maximum size is 1 MB.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")
