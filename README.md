# AI Coding Buddy

A friendly desktop tutor that helps you understand a C solution by writing it yourself.

**Python + PySide6. English interface. Windows first. No account, browser, or editor extension required.**

## What works

- Paste a task and reference solution, or import a C/text file.
- Start Learning opens a blank editor. Your reference stays out of the learning view.
- C syntax highlighting, line numbers, automatic indentation, undo/redo and saving.
- Five animated robot states: neutral, thinking, happy, surprised and explaining.
- Clearly labelled offline demo with simple local rules.
- Optional AI tutoring through a configurable Chat Completions-compatible provider.
- Background requests; typing, changing settings or starting another exercise invalidates old replies.
- Pause detection after 25 seconds, with a 45-second interruption cooldown and no repeated automatic hints for unchanged code.
- Local recognition of new code structures and recurring delimiter patterns. AI mode also receives up to three recent code snapshots to reason about repeated mistakes.
- Four escalating hint levels, plus a short example only after explicitly pressing **Show a small example**.
- Understanding questions, typed answers and a solution-review summary.
- English text-to-speech when a supported English system voice is available; sound toggle and replay.
- A portable Windows build script and automated tests.

## Start on Windows

### Portable application

Extract the entire **AI-Coding-Buddy-Windows.zip** package, then double-click
**AI-Coding-Buddy.exe** inside the extracted folder. Keep the executable, its
_internal folder and license notices together. Python is not needed for the portable build.

The executable is unsigned. Only run packages obtained from a source you trust.
Source control contains the build scripts, not the large binary package.

### From source — easiest setup

1. Install **Python 3.11 or later** with the Python Launcher.
2. Download this repository with **Code → Download ZIP** and extract it.
3. Double-click **Setup.bat**. It creates a private environment and installs Qt.
4. Double-click **Start.bat**.

Setup needs internet access. Day-to-day demo use does not.

### From a terminal

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## A three-step learning session

1. Paste the task and reference code, or import a `.c` / `.txt` file.
2. Press **Start Learning**.
3. Write your own solution. The buddy asks questions and offers small hints without editing your code.

**Help** requests a hint at the current level. **More help** advances through four
levels. At level 4, **Show a small example** becomes available; it never inserts
anything into your editor. New code concepts reset the hint level.

**Check understanding** asks a question. Type an answer and press Enter or
**Submit answer**. Editing the code hides questions tied to the previous state.

**Review my solution** requests a logic review and a short summary. A positive AI
review is explicitly provisional: the program does not compile or execute C.
Demo mode never certifies correctness.

Uncheck **Automatic hints** to work quietly. Manual help remains available.
Use **Sound** to mute speech and **Repeat** to replay the last message.

## Connect an AI provider

The app always starts in offline demo mode, even when a provider was configured
previously. No API key is bundled.

1. Open **AI settings**.
2. Enter your provider's **API base URL**, usually ending in `/v1`.
3. Enter the **model identifier** supplied by that provider.
4. Enter your **API key** if the provider requires one.
5. Read and check the consent box, then save.

The provider must accept `POST {base_url}/chat/completions` with a system message,
a user message and `stream: false`, and return text in
`choices[0].message.content`. The model must follow JSON output instructions.
This is a replaceable compatibility adapter, not a promise that every model or
provider supports the same protocol.

HTTPS is required for remote services. Local servers can use HTTP on
`localhost`, `127.0.0.1`, or `::1`. No redirects are followed.
Provider charges, limits and retention policies depend on the chosen service.

The AI derives a flexible concept plan, examines the task and code rather than
text similarity, and is instructed to accept valid alternative implementations.
It receives recent hints to avoid repetition. Prompt instructions plus output
validation limit solution disclosure; model judgments and instructions are not
a formal guarantee.

## Privacy and local files

- Demo mode makes no API requests.
- AI mode sends the task, reference code, current/recent student code, answers,
  concept plan and recent hints to the configured provider only after consent.
- API keys and consent live in memory only and must be entered/enabled again
  after restarting. Keys are not logged or stored in the repository.
- Only endpoint, model, sound and automatic-hint preferences are saved as JSON,
  in Qt's per-user application configuration directory.
- Changing the provider URL or model clears the consent checkbox.
- Disabling AI stops future submissions and invalidates pending replies;
  already transmitted data cannot be recalled.
- Exercise code is not automatically persisted. **Save** / **Ctrl+S** writes
  only your own code. Unsaved edits trigger a save/discard/cancel prompt.
- Imports are limited to 1 MB; UTF-8 (including BOM) and Windows-1252 are supported.
- AI requests are limited to 60,000 combined task/code/history characters.
- A running network request has a 25-second socket timeout. Closing the app
  discards its result, though process shutdown may wait for the worker to finish.

## Build a Windows package

Run **Build.bat**, or:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\build_windows.py
```

The script creates `dist/AI-Coding-Buddy/`, copies third-party notices,
runs a noninteractive executable smoke test, and produces
`dist/AI-Coding-Buddy-Windows.zip`. This is a portable folder, not an installer.
Build on Windows. Qt DLLs remain separate and replaceable.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover file import, saving, a blank learning editor, unsaved-change handling,
hint levels, completion guards, response validation, local mock HTTP requests,
authentication errors, blocked redirects, consent changes, privacy, indentation,
highlighting, pause cooldowns, background request ordering and stale replies.

The HTTP integration test uses a local mock server, not a paid service.
A live provider test requires your own configuration and consent. Speech depends
on an installed operating-system voice; if unavailable, text tutoring still works.

## Project structure

| File | Responsibility |
| --- | --- |
| `main.py` | Application startup and packaged smoke test |
| `buddy/window.py` | Start/learning views and interaction flow |
| `buddy/editor.py` | C editor, gutter, highlighting and indentation |
| `buddy/analysis.py` | Shared tutoring data, offline rules and HTTP adapter |
| `buddy/controller.py` | Bounded background work and stale-response rejection |
| `buddy/character.py` | Robot drawing, five expressions and speech animation |
| `buddy/speech.py` | Qt speech and graceful fallback |
| `buddy/settings.py` | Provider consent and nonsecret preferences |
| `buddy/session.py` | In-memory exercise and bounded file import |
| `examples/` | A small C reference and practice ideas |
| `scripts/build_windows.py` | Portable Windows packaging |
| `tests/` | Offline and mocked integration tests |

## Boundaries and future work

This completes the planned MVP phases: base app, activity monitoring, provider
integration, voice/character behavior, and testing/packaging. Demo checks are
heuristics, not a C parser. AI reviews may miss errors or reject valid solutions.
The app deliberately does not execute untrusted code.

Still outside this version: a sandboxed compiler/test runner, microphone input,
3D characters, additional programming languages, accounts/cloud sync and
long-term learning statistics.

Technical references: [Qt plain text editor](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QPlainTextEdit.html),
[Qt speech](https://doc.qt.io/qtforpython-6/PySide6/QtTextToSpeech/QTextToSpeech.html),
[Chat Completions API format](https://developers.openai.com/api/reference/typescript/resources/chat).
See [third-party notices](THIRD_PARTY_NOTICES.md).
