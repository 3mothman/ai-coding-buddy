# Verification — v0.8.10

Date: 17 November 2026. Platform: Windows, Python 3.11.

| Check | Result |
| --- | --- |
| Automated suite | 96 tests passed in the final source suite |
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

Response-reader regression tests cover parsed SDK output without text, empty
responses, MAX_TOKENS truncation, fenced JSON, filtered output, and bounded retries.
The root cause of the screenshot remains unconfirmed without its finish reason.

HTTP error diagnostics were tested with real SDK error objects and a deliberate invalid diagnostic key (no successful inference or paid call). The user's actual connection failure remains unconfirmed until its diagnostic category is available.

Version 0.8.10: Live connection queues the latest lesson hint for speech; text remains visible during audio generation; the speech status reflects the connection. Invalid structured analyses get one corrective retry with the same validation rules. The initial prompt explicitly includes beginner setup and a brief homework overview. Real microphone-to-speaker behavior has not been verified for this update.

Version 0.8.10 adds a compact current-objective panel above a hold-to-talk button on the left. Live capture starts muted and only transmits while the learner holds the button, preventing open-microphone self-interruption between turns. Live playback on the user device still needs confirmation.

Version 0.8.10 automatically connects Live voice after the lesson introduction is ready when Sound and session audio consent are enabled. On connection the existing introduction is queued for speech; microphone capture remains muted until Hold to talk.

Version 0.8.10 adds contextual direct questions, remembers student questions, uses the accepted snapshot for code comparison, and reports safe validation rejection categories. Prompt instructions explicitly require checking current code and advancing to an unfinished objective. Offline contract tests do not establish real-model teaching accuracy or audible speech playback.

Version 0.8.10: inspected frames from the supplied 59.7-second recording. It shows an interrupted introduction, empty editor and the pre-0.8.6 quiz button/generic error. Approved speech now explicitly bypasses analyzer tool calls; invalidating a generation clears its generating flag so future commands can proceed. Partial speech transcripts no longer overwrite the full explanation. Repeat uses the approved hint. These changes are not a verification of audible playback or real-model tool compliance.

0.8.10 regression: unsolicited snippets are discarded while retaining valid diagnosis, message and line highlight. Complete-program content in displayed messages and requested examples remains rejected. Tested missing array brackets from the screenshot using a mocked model response.

Version 0.8.10 uses native Windows text-to-speech to read the full approved explanation independently of Gemini Live. Routine UI refresh and editor changes no longer stop playback. Review my solution and Automatic hints were removed from the learning controls; Live/microphone controls are hidden for this read-aloud-focused release. Voice and speed controls apply to native speech. Cloud voice quality is not preserved by this switch.

0.8.10: Gemini explanations use the configured Gemini Live model and voice for a text-only, tool-free speech request. The complete PCM response is buffered into an in-memory WAV before playback. No microphone is opened. Generation errors remain visible; partial/interrupted clips are rejected. This adds generation latency. Offline tests verify chunk concatenation and rejection of interrupted output; authenticated speech quality and word completeness are not verified.
