# Verification — v0.8

Date: 17 November 2026. Platform: Windows, Python 3.11.

| Check | Result |
| --- | --- |
| Automated suite | 76 tests passed in the final source suite |
| Official SDK configuration/schema validation | Passed, google-genai 3.4.0 |
| Offline runtime script | Passed; live analysis explicitly marked not run |
| 44.1/48 kHz capture conversion to 16 kHz | Passed synthetic streaming signal tests |
| Default audio-device probe | Passed with microphone muted; output 24 kHz; zero capture packets |
| Live event handling | Passed mocked multi-part, transcription, interruption and tool-call tests |
| Reconnect/resumption | Passed mocked bounded reconnect and device-cleanup test |
| Real Gemini service inference | Not run: no configured Gemini API key |
| Human voice quality/STT/latency assessment | Not run: requires real Gemini session and user evaluation |

The mocked programming scenarios validate request context, response handling and
allowed actions. They do not establish real-model accuracy on arbitrary C programs.
No microphone recording was stored and no paid API call was made during these checks.

Native Windows settings and learning views were rendered and inspected. The initial portable build passed the expanded offline SDK/audio startup check. The final package also passed extraction and isolated startup verification.

## Final portable verification

The final 85.8 MB ZIP was extracted to a separate folder. Its executable passed
--smoke-test with PYTHONPATH, PYTHONHOME and API-key variables removed and a minimal
Windows PATH. This exercises the packaged Google SDK types and native resampler
as well as Qt initialization; it opens no microphone and makes no service call.
