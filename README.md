# AI Coding Buddy

A Python/PySide6 desktop tutor for learning to write C code independently.
Version **0.8.3** adds official Gemini analysis and optional Gemini Live voice.
The existing editor, robot and two-view interface are preserved.

## Start on Windows

**Portable:** extract AI-Coding-Buddy-v0.8.3.zip, open the AI-Coding-Buddy folder,
and run AI-Coding-Buddy.exe. Keep _internal and the notices beside it.

**Source:** install Python 3.11 or later, extract this repository, run Setup.bat
once, then Start.bat. Setup needs internet access.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Connect Gemini

1. Get a key from [Google AI Studio](https://aistudio.google.com/api-keys).
2. In **AI settings**, select **Gemini (official Google SDK)**.
3. Defaults: analysis model **gemini-3.8-flash**, Live model **gemini-3.8-live**.
   Checked against Google's documentation on 17 November 2026. Account access can
   differ; model IDs remain editable.
4. Enter the key in the masked field, or set GEMINI_API_KEY before launching.
   Keys are kept in memory and are not saved.
5. Read and enable code-transfer consent. **Test connection** sends only a built-in
   sample and checks the structured analysis response.
6. Save, paste/import the task and reference, and press **Start Learning**.
   Gemini analyzes the reference first; practice opens with a blank editor after success.

The app starts in offline demo mode each time. Groq and other compatible providers
remain available as legacy options; the new Gemini/Live features need Gemini.

## Natural voice and microphone

Choose a Live voice and English or German in Gemini settings. Enable the
**separate audio-transfer consent**, then save. In the learning view press
**Start Live voice**. The microphone is not opened before that explicit start.

- Headphones permit full-duplex speech and interruptions.
- **Mute microphone** stops audio transmission; **Stop Live voice** closes the session.
- Speaker-safe mode gates capture during playback. It avoids echo but is not
  acoustic echo cancellation and cannot provide full-duplex barge-in.
- Google Live provides the speech and both transcripts. The existing bubble shows
  the output audio transcription, not separately generated unrelated text.
- Partial text is marked while playing. Interrupted text is marked as received,
  potentially including an unplayed ending.
- Gemini mode does not fall back to Windows TTS. If Live fails, text tutoring works.
  System speech is retained for demo/legacy-provider use only.

## Learning controls

**Check my code** checks current work. **Help** asks for a guiding question or hint.
**More help** increases support through four levels; a tiny example requires an
explicit request. **Ask me a question** is a separate understanding quiz.

Session memory keeps the task, a flexible concept plan, progress evidence, current
objective, recent conversation, prior hints and recurring issues. Valid alternative
implementations are allowed. AI assessments are provisional, not compiler validation.

**Automatic hints** start off. Enable them if desired and configure inactivity
(default 25 seconds) and unsolicited-hint cooldown (default 45 seconds).
Meaningful statement/block changes are debounced, with at least 10 seconds between
background requests. Analysis waits during speech and two seconds afterward.
A pause requests a decision: the analyzer can stay silent. Python filters
duplicates and low-confidence unsolicited hints.

The editor keeps highlighting, line numbers, indentation, undo/redo and saving.
Gemini may highlight a validated student-code range; it cannot write into the editor.
The app never compiles or executes student C code.

## Tests and architecture

See [GEMINI_UPGRADE.md](GEMINI_UPGRADE.md) for diagnosis, exact file changes,
architecture, API references, verification and live acceptance scenarios.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\check_gemini.py
```

The second command checks SDK/audio dependencies offline. To explicitly send
built-in code scenarios to the real model (API usage may be charged), configure
GEMINI_API_KEY locally, then run:

```powershell
.\.venv\Scripts\python.exe scripts\check_gemini.py --run-live-analysis --report gemini-verification.json
```

The script records observations for human review, not a correctness certificate.
No live key was available during development: actual Gemini reasoning quality,
STT accuracy, audible naturalness and end-to-end latency remain unverified.
Mocked tests do not establish those qualities.

## Build

Run Build.bat, or install requirements-dev.txt and run
`python scripts/build_windows.py` in the project environment. Build on Windows.
The script bundles the SDK/audio dependencies, includes notices, runs an offline
executable smoke test, and creates a portable ZIP.

## Privacy

After consent, analysis sends the task, reference, student code and compact
learning/conversation context to Google. Live additionally sends microphone audio.
Keys, consent, transcripts, code and resumption handles stay in app memory.
Only nonsecret preferences are persisted. No microphone recordings are written.
Exercise code is saved only through **Save**. Providers apply their own charges,
limits and data policies. Disabling consent cannot recall data already sent.
Diagnostic logs contain failure categories, not keys or raw provider responses.

Still outside this release: a sandboxed C compiler, long-term learning profiles,
additional editor languages, and automatic acoustic echo cancellation.

[Third-party notices](THIRD_PARTY_NOTICES.md)

## Response diagnostics (0.8.3)

The old unreadable-response error covered multiple failures. The app now checks
finish reasons, uses SDK-parsed output when available, and distinguishes empty,
truncated, filtered, malformed-JSON and SDK-configuration failures. Empty/truncated
responses get at most one retry with a larger output budget. Gemini 3 models use
LOW thinking, a supported setting, to leave more room for the structured answer.
The exact cause of the reported 0.8 error could not be determined from its generic
message alone. The new diagnostics allow that distinction without exposing keys
or raw code. No live Gemini credentials were available for this fix.

Version 0.8.3 distinguishes Google HTTP 400 invalid-key errors from invalid requests, restricted projects, network timeouts, transport failures and service failures. Error messages never include raw provider text or keys. An intentional invalid-key request confirmed that Google returns HTTP 400 with API_KEY_INVALID; this does not establish the cause of any user screenshot.

Version 0.8.3: Live connection queues the latest lesson hint for speech; text remains visible during audio generation; the speech status reflects the connection. Invalid structured analyses get one corrective retry with the same validation rules. The initial prompt explicitly includes beginner setup and a brief homework overview. Real microphone-to-speaker behavior has not been verified for this update.
