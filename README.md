# AI Coding Buddy

Eine einfache Python-Desktop-Anwendung zum eigenständigen Nachprogrammieren von C-Lösungen.

## Stand: Phase 1 – lauffähige Grundanwendung

- Startansicht mit optionaler Aufgabenstellung und Referenzcode.
- Import von `.c` und `.txt` (UTF-8 oder Windows-1252, maximal 1 MB).
- **Start Learning** öffnet einen leeren Editor. Die Referenz wird nicht im Lerneditor angezeigt.
- Selbst gezeichnete, sanft animierte Roboterfigur mit festem Beispielhinweis.
- Code speichern, Undo/Redo und Rückfrage vor dem Verwerfen ungespeicherter Änderungen.
- Vollständig lokal, ohne Anmeldung und ohne Netzwerkzugriffe.

**Noch keine KI-Analyse:** Der Hinweis ist ein klar gekennzeichnetes Beispiel. Syntaxhervorhebung, Zeilennummern, automatische Einrückung, Schreibpausenerkennung, API-Anbindung, Lernkontrolle, fünf emotionale Zustände und Sprachausgabe sind spätere Entwicklungsschritte. Der Editor führt keinen Code aus.

## Unter Windows starten

1. Python 3.11 oder neuer installieren, einschließlich Python Launcher.
2. Repository über **Code → Download ZIP** herunterladen und entpacken.
3. Im Projektordner ein Terminal öffnen.
4. Einmalig eine Umgebung erstellen und die Abhängigkeit installieren:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

5. Anwendung starten:

```powershell
.\.venv\Scripts\python.exe main.py
```

Nach der Einrichtung startet auch ein Doppelklick auf **Start.bat** die Anwendung. Eine fertige EXE gehört noch nicht zu Phase 1.

## Benutzung

Aufgabe optional eingeben → Lösung einfügen oder importieren → **Start Learning**.
Jetzt die Lösung selbst schreiben. **Speichern** oder **Strg+S** speichert nur den selbst geschriebenen Code. **Neue Übung** kehrt zur Eingabe zurück. Referenz und Aufgabenstellung bleiben dort erhalten und können ersetzt werden. Beim Beenden werden die Eingaben nicht automatisch gespeichert.

## Aufbau einfach erklärt

| Datei | Aufgabe |
| --- | --- |
| `main.py` | Startet Qt und das Hauptfenster. |
| `buddy/window.py` | Baut beide Ansichten auf und verbindet die Buttons. |
| `buddy/editor.py` | Kapselt den einfachen Texteditor ohne Autovervollständigung. |
| `buddy/character.py` | Zeichnet und animiert den Roboter mit QPainter und QTimer. |
| `buddy/session.py` | Hält Aufgabenstellung und Referenz im Speicher und liest Dateien. |
| `tests/test_app.py` | Prüft Import, Ansichtswechsel und Schutz ungespeicherter Änderungen. |

Der Code verwendet Qt für Python: [QPlainTextEdit](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QPlainTextEdit.html) und [QPainter](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QPainter.html).

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Nächste Phasen

2. Schreibaktivität und Pausen mit zurückhaltenden, ausdrücklich regelbasierten Hinweisen erkennen.
3. Austauschbaren KI-Anbieter ergänzen: vorherige Einwilligung zur Codeübertragung, sichere Schlüsselverwaltung, asynchrone Anfragen und Verwerfen veralteter Antworten.
4. Sprachausgabe und weitere Charakterreaktionen.
5. Lernqualität, alternative korrekte Lösungen und Windows-Paketierung prüfen.

## Datenschutz

Diese Version sendet weder Code noch Aufgabenstellungen an externe Dienste. Nur ausdrücklich importierte Dateien werden gelesen; nur beim Speichern wird eigener Code geschrieben. Keine API-Schlüssel erforderlich.
