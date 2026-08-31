# Agent Col STT/TTS Branch Handoff

## Current Branch

Work is on:

```text
STT/TTS-research
```

Before continuing in a new session, switch to this branch and verify state:

```bash
git switch STT/TTS-research
git status --short
git rev-parse HEAD
git status -sb
```

Do not merge to `main` until the STT/TTS feature has completed review and deployment approval.

## Architecture Implemented So Far

The implemented architecture keeps speech as an edge adapter around the existing Agent Col chat pipeline:

```text
Microphone
-> Cloud Speech-to-Text V2
-> ordinary Agent Col composer text
-> existing Agent Col chat submit path
-> persisted canonical assistant/model response
-> Cloud Text-to-Speech, Chirp 3 HD
-> browser audio playback
```

Authority boundaries:

```text
STT transcript = draft user input
Agent Col persisted model response = canonical assistant output
TTS = renderer of canonical persisted model output
```

No speech path should bypass or replace the existing chat request pipeline.

## Provider Decisions

Speech-to-text:

```text
Google Cloud Speech-to-Text V2
recognizer location: global
recognizer path: projects/{project}/locations/global/recognizers/_
model: latest_short
language codes: en-US
decoding: AutoDetectDecodingConfig
baseline MIME types: audio/webm, audio/webm;codecs=opus
```

Text-to-speech:

```text
Google Cloud Text-to-Speech
engine/voice family: Chirp 3 HD
default female voice: en-GB-Chirp3-HD-Kore
alternate male voice: en-GB-Chirp3-HD-Alnilam
speaking rate: 1.0
audio content type: audio/mpeg
```

Gemini TTS is explicitly deferred and is not part of the baseline implementation.

## Completed Passes

### Pass 1: Security And Request Perimeter

Implemented route-aware request body limits and browser security header changes.

Source areas:

- `main.py`: `RequestPerimeterMiddleware` keeps ordinary API requests at the existing 64 KiB ceiling while allowing a larger configured ceiling for `/api/speech/transcribe`.
- `main.py`: security headers allow same-origin microphone access with `Permissions-Policy: microphone=(self)`.
- `main.py`: CSP includes media policy for local/blob audio playback.
- `tests/test_main.py`: coverage for normal request limits, speech route limits, microphone permissions policy, and media CSP.

### Pass 2: STT Backend

Implemented authenticated backend transcription endpoint.

Source areas:

- `main.py`: `POST /api/speech/transcribe` authenticates the user, validates audio MIME, reads raw request body, calls the transcription service, and returns `{ "transcript": "..." }`.
- `speech_service.py`: `CloudSpeechTranscriptionService` builds a Speech-to-Text V2 `RecognizeRequest` using the implicit `_` recognizer, `AutoDetectDecodingConfig`, configured language codes, and configured model.
- `speech_service.py`: strict browser audio MIME allowlist currently accepts `audio/webm` and `audio/webm;codecs=opus`.
- `requirements.txt`: added `google-cloud-speech==2.40.0`.
- `tests/test_speech_service.py`: validates config loading, MIME normalization, request construction, transcript extraction, and provider error wrapping without live Google calls.
- `tests/test_main.py`: validates auth, MIME rejection, response shape, sanitized failure handling, and no workspace/project coupling for STT.

### Pass 3: STT Frontend

Implemented browser microphone recording and transcript insertion.

Source areas:

- `frontend/index.html`: added Mic button in the existing composer action row.
- `frontend/api.mjs`: added `transcribeSpeechAudio()` to POST raw audio to `/api/speech/transcribe` with the actual recording MIME type.
- `frontend/app.mjs`: added `MediaRecorder` lifecycle, microphone permission handling, WebM/Opus MIME selection, track cleanup, transcription call, and composer insertion.
- `frontend/chat-view.mjs`: added `insertComposerText()` to place STT output into the ordinary composer.
- `frontend/styles.css`: added compact speech control styling and recording/transcribing states.
- `tests/frontend/api.test.mjs`: validates raw audio upload contract.
- `tests/frontend/app-runtime.test.mjs`: validates mic start/stop, MIME selection, transcript insertion, permission denial, transcription failure, track cleanup, and prevention of simultaneous recordings.
- `tests/frontend/chat-view.test.mjs`: validates transcript insertion and safe appending.
- `tests/frontend/workspace-static.test.mjs`: validates composer control placement.

### Pass 4: Canonical TTS Lookup

Implemented canonical persisted model-message lookup for TTS without a public text-return endpoint.

Source areas:

- `database.py`: added `get_completed_model_message()` to resolve `project_id + session_id + message_id` under user/project/session ownership.
- `database.py`: helper rejects unowned sessions/messages, non-model/user messages, incomplete messages, and missing canonical response text.
- `tests/test_database.py` or focused database tests: validate owned completed model lookup and rejection paths.

The temporary public route that returned TTS source text was removed. The browser does not need a separate endpoint that returns canonical text it already displays.

### Pass 5: Chirp 3 HD TTS Backend

Implemented backend TTS synthesis.

Source areas:

- `main.py`: `POST /api/users/{user_id}/speech/synthesize` authenticates user, accepts only canonical locators plus chunk/voice id, retrieves the canonical persisted model message, synthesizes audio, and returns raw audio bytes.
- `main.py`: rejects browser-supplied replacement text.
- `speech_service.py`: `CloudTextToSpeechSynthesisService` chunks text deterministically under the provider byte limit and calls Google Cloud Text-to-Speech.
- `speech_service.py`: maps approved voice ids only: `female -> en-GB-Chirp3-HD-Kore`, `male -> en-GB-Chirp3-HD-Alnilam`.
- `speech_service.py`: never summarizes, rewrites, or reorders canonical text.
- `requirements.txt`: added `google-cloud-texttospeech`.
- `tests/test_speech_service.py`: validates deterministic chunking, voice mapping, TTS request construction, chunk errors, and provider wrapping.
- `tests/test_main.py`: validates canonical locator-only synthesis, ownership enforcement, role/completion enforcement, raw audio response headers, approved voice ids, and sanitized provider failures.

### Pass 6: Frontend TTS Playback Controls

Implemented browser playback against the canonical TTS endpoint.

Source areas:

- `frontend/index.html`: added Stop button and two-voice dropdown in the centered speech controls.
- `frontend/api.mjs`: added `synthesizeSpeechAudio()` to request audio chunks from the canonical TTS endpoint and return raw Blob/audio metadata.
- `frontend/app.mjs`: added canonical message-id derivation, sequential chunk requests, object URL playback, Stop behavior, playback cleanup, and selected voice id usage.
- `frontend/chat-view.mjs`: initially rendered a per-response `Speak` button.
- `frontend/styles.css`: added playback control styling.
- `tests/frontend/app-runtime.test.mjs`: validated selected voice, chunk queue, canonical locator contract, Stop cancellation, and no browser response text submission.

### Pass 6A: Speech Provider Failure Diagnostics

Implemented sanitized provider-cause logging and empty-audio rejection.

Source areas:

- `main.py`: added `_log_speech_provider_failure()` and `_provider_code_label()`.
- `main.py`: STT now rejects empty audio with `400 Speech audio is required.` before provider access.
- `main.py`: STT/TTS provider failures now log wrapper type, underlying cause type, and provider code label without logging private exception text.
- `tests/test_main.py`: validates empty audio rejection and sanitized diagnostic logging for both STT and TTS.

Runtime blocker found and fixed outside source:

```text
Cloud Speech-to-Text API was not enabled on project-e1e2a890-4566-48a8-a32.
```

Resolved with:

```bash
gcloud services enable speech.googleapis.com --project=project-e1e2a890-4566-48a8-a32
```

Verified:

```text
speech.googleapis.com
```

After that, local STT and TTS were manually verified by the user as working.

### Pass 6B: Frictionless STT Submit And Spoken Response Toggle

Implemented the currently accepted working frontend behavior.

Source areas:

- `frontend/index.html`: added `Spoken responses` checkbox beside Mic and the voice dropdown inside `.composer-speech`.
- `frontend/app.mjs`: when a recording started from an empty composer and returns a non-empty transcript, the transcript is inserted and submitted through the existing composer submit path.
- `frontend/app.mjs`: when the composer already had text at recording start, transcript is appended and not auto-submitted.
- `frontend/app.mjs`: when spoken responses are enabled, newly completed model responses are spoken automatically using the canonical TTS endpoint.
- `frontend/app.mjs`: turning spoken responses off stops any current playback.
- `frontend/chat-view.mjs`: removed large per-response `Speak` button from chat bubbles.
- `frontend/chat-view.mjs`: added `submitComposer()` so STT auto-submit still uses the existing `handlers.onSubmit()` and ordinary `ChatRequest.message` construction.
- `frontend/styles.css`: added compact styling for `.spoken-response-toggle` and removed dead bubble Speak styling.
- `tests/frontend/app-runtime.test.mjs`: validates auto-submit only for empty-composer STT, no auto-submit for empty transcript, no auto-submit when existing typed text is present, spoken responses default off, toggle-on auto playback, and Stop cancellation.
- `tests/frontend/chat-view.test.mjs`: validates bubble-level Speak controls are no longer rendered.
- `tests/frontend/workspace-static.test.mjs`: validates the toggle remains in the centered composer speech controls beside Mic and voice selection.

Current intended UX:

```text
Empty composer:
click Mic -> speak -> click Mic off -> transcript returns -> prompt auto-sends

Existing typed composer text:
click Mic -> speak -> click Mic off -> transcript appends -> user still sends manually

Spoken responses off:
assistant responses do not play automatically

Spoken responses on:
newly completed assistant responses play automatically using the selected approved voice
```

### Pass 6C: Lower-Latency TTS Chunk Playback

Implemented Option B from the TTS latency investigation: keep the existing
canonical-response TTS architecture and reduce perceived latency by changing only
chunking and scheduling.

Preserved boundaries:

- TTS still starts only after the final canonical Agent Col response exists.
- The browser still calls the authenticated FastAPI TTS route.
- The backend still uses synchronous Google Cloud Text-to-Speech
  `synthesize_speech()`.
- Approved Chirp 3 HD voices and MP3 output are unchanged.
- No Google streaming TTS, provisional LLM speech, MediaSource, Web Audio
  playback, or alternate playback architecture was introduced.

Source areas:

- `speech_service.py`: split the provider byte ceiling from latency-oriented
  chunk sizing.
  - Provider ceiling remains `TTS_CHUNK_BYTE_LIMIT = 4800` bytes, below the
    Google provider input limit.
  - First playback chunk now uses a smaller target
    `TTS_FIRST_CHUNK_BYTE_LIMIT = 700`.
  - Later chunks use `TTS_LATER_CHUNK_BYTE_LIMIT = 1800`.
  - `chunk_text_for_speech()` remains deterministic, preserves exact text when
    chunks are joined, and remains sentence/paragraph-aware where possible.
- `speech_service.py`: `CloudTextToSpeechSynthesisService` now applies the
  latency chunk limits through `_chunks_for_text()` before calling the existing
  synchronous synthesis path.
- `frontend/api.mjs`: `synthesizeSpeechAudio()` now accepts an abort signal for
  cancellation of in-flight prefetch requests.
- `frontend/app.mjs`: TTS playback now requests chunk 0, begins playback as soon
  as that chunk returns, and prefetches exactly chunk N+1 while chunk N is
  playing.
- `frontend/app.mjs`: playback order remains strict; chunk N+2 is not requested
  until chunk N finishes and chunk N+1 becomes current.
- `frontend/app.mjs`: Stop aborts current/in-flight TTS requests and prevents
  queued/future playback.
- `tests/test_speech_service.py`: validates latency-sized first chunks, larger
  later chunks, provider ceiling preservation, and service-level chunk limit
  wiring.
- `tests/frontend/app-runtime.test.mjs`: validates first audio can start before
  all chunks synthesize, exactly one-chunk-ahead prefetch, strict order,
  short-response behavior, cancellation, and prefetch failure isolation.

Manual acceptance:

```text
The user verified TTS latency was meaningfully reduced.
```

Measurement note:

The automated proxy measurement used during the pass compared old and new first
chunk size on a 7640-byte sample:

```text
old first chunk: 4777 bytes
new first chunk: 658 bytes
first chunk byte reduction: 86.2%
synthetic final-to-play proxy: 100.90ms -> 18.37ms
```

The source-backed improvement is reduced time-to-first-audio by requiring only
the first sentence-sized MP3 chunk before playback, while later chunks synthesize
one at a time during playback.

Issue found during manual verification:

```text
ImportError: cannot import name 'texttospeech' from 'google.cloud'
```

Root cause:

- `requirements.txt` already declared `google-cloud-texttospeech==2.37.0`.
- The active local `venv` did not actually have `google-cloud-texttospeech`
  installed, so the existing lazy import failed at runtime.

Resolution:

```bash
venv/bin/python -m pip install -r requirements.txt
```

The first sandboxed install attempt failed because DNS/network access to PyPI was
blocked. The same command was rerun with network approval and installed:

```text
google-cloud-speech-2.40.0
google-cloud-texttospeech-2.37.0
```

Verified after install:

```bash
venv/bin/python -c 'from google.cloud import texttospeech; print(texttospeech.TextToSpeechClient.__name__)'
```

Output:

```text
TextToSpeechClient
```

No source change was made for that dependency issue. If this error reappears in
a fresh environment, install from `requirements.txt` before changing source.

Checkpoint:

```text
77453e9 Optimize TTS chunk playback latency
```

This commit was pushed to `origin/STT/TTS-research`.

### Pass 6D: Silence-Triggered STT Mic Stop

Implemented browser-side trailing-silence auto-stop for the existing
MediaRecorder STT user-prompt flow.

Preserved boundaries:

- No live transcription.
- No backend speech service changes.
- No second transcription or submission path.
- The browser still records locally with `MediaRecorder`.
- Completed recording still becomes one final `Blob`.
- The final blob still goes to the existing `/api/speech/transcribe` endpoint.
- Transcription still lands in the existing composer.
- Existing composer submit rules still decide whether to auto-send.
- Manual mic on/off behavior is preserved.

Target flow now implemented:

```text
mic on
-> MediaRecorder records locally
-> browser-side RMS detector waits for actual speech
-> after speech, 2 continuous seconds of trailing silence
-> calls existing stopSpeechRecording()
-> MediaRecorder onstop fires
-> finishSpeechRecording()
-> transcribeSpeechAudio()
-> transcript inserted into composer
-> existing composer auto-send rules apply
```

Source areas:

- `frontend/app.mjs`: added lightweight browser-side audio amplitude analysis
  using `AudioContext`, `MediaStreamSource`, `AnalyserNode`,
  `getByteTimeDomainData()`, RMS calculation, and `requestAnimationFrame`.
- `frontend/app.mjs`: added detector state equivalent to:

  ```text
  speechHasStarted = false
  wait for RMS above adaptive threshold
  after speech starts, measure trailing silence
  if speech resumes before 2 seconds, reset the timer
  if silence lasts 2 continuous seconds, call stopSpeechRecording()
  ```

- `frontend/app.mjs`: the detector does not start the silence countdown merely
  because the mic is enabled. Initial silence can continue indefinitely until the
  user speaks or manually stops.
- `frontend/app.mjs`: `stopSpeechRecording()` is the single authoritative stop
  lifecycle for both manual and automatic stop.
- `frontend/app.mjs`: added a `stopRequested` guard to prevent automatic and
  manual stop from running the lifecycle twice.
- `frontend/app.mjs`: silence detection cleanup cancels the animation frame,
  disconnects analyser/source resources, closes the `AudioContext`, and still
  stops media tracks through the existing path.
- `frontend/app.mjs`: if audio analysis is unavailable or throws during setup,
  the detector fails closed and normal manual MediaRecorder recording continues.
- `frontend/app.mjs`: added `autoSubmitEligible`, initialized from whether the
  composer was empty at recording start.
- `frontend/app.mjs`: composer input during an active recording revokes
  `autoSubmitEligible`, so typing/editing while recording prevents auto-send.
- `tests/frontend/app-runtime.test.mjs`: added fake browser audio-analysis
  support for deterministic VAD/silence tests.
- `tests/frontend/app-runtime.test.mjs`: validates:
  - speech followed by two seconds trailing silence auto-stops through the
    existing transcription path;
  - mic enabled without speech does not auto-stop;
  - speech resuming before two seconds resets trailing silence;
  - existing composer text prevents auto-send;
  - editing during recording revokes auto-send;
  - automatic and manual stop share one lifecycle;
  - manual stop cleans up detector resources;
  - recording still works if browser audio analysis fails.

Important behavior examples now covered:

```text
Empty composer:
click Mic -> speak -> 2s silence -> auto stop -> transcript -> auto-send
```

```text
Existing composer text:
click Mic -> speak -> 2s silence -> auto stop -> transcript appends -> no auto-send
```

```text
Empty composer, then user types while recording:
click Mic -> speak + edit composer -> 2s silence -> transcript appends -> no auto-send
```

Implementation notes for future sessions:

- The silence detector is intentionally small and heuristic-based.
- It uses RMS amplitude and a small adaptive noise floor rather than a large VAD
  dependency.
- If live testing shows false stops or missed stops in real rooms, tune only the
  detector constants/heuristics in `frontend/app.mjs` and keep the STT backend
  architecture unchanged.
- Do not add live transcription or another STT path to solve threshold tuning.

Verification:

```bash
node tests/frontend/app-runtime.test.mjs
node --test tests/frontend/workspace-static.test.mjs
git diff --check
```

Latest focused result before this handoff update:

```text
frontend app-runtime: 27 pass, 0 fail
workspace-static: 1 pass, 0 fail
git diff --check: clean
```

Manual acceptance:

```text
The user verified the silence-triggered mic-stop pass was successful.
```

## Current Manual Acceptance

The user manually verified:

```text
STT works.
TTS works.
Pass 6B behavior is working well.
Pass 6C TTS latency is meaningfully reduced.
Pass 6D silence-triggered mic stop is successful.
```

## Known Operational Requirements

Local development currently uses Application Default Credentials. `.env` contains:

```text
GOOGLE_CLOUD_PROJECT=project-e1e2a890-4566-48a8-a32
GOOGLE_CLOUD_LOCATION=global
```

For local STT/TTS:

- `speech.googleapis.com` must be enabled.
- `texttospeech.googleapis.com` must be enabled.
- ADC must be valid for the configured project.

For Cloud Run deployment:

- enable `speech.googleapis.com`;
- enable `texttospeech.googleapis.com`;
- verify the Cloud Run runtime service account;
- grant the runtime identity the least-privilege Speech and Text-to-Speech permissions needed for recognition and synthesis;
- do not rely on `.env` to enable Google APIs or IAM.

## Verification Commands Used Recently

Focused frontend verification:

```bash
node --test tests/frontend/app-runtime.test.mjs tests/frontend/chat-view.test.mjs tests/frontend/workspace-static.test.mjs
```

Broader frontend verification:

```bash
node --test tests/frontend/*.test.mjs
```

Backend main regression:

```bash
venv/bin/pytest tests/test_main.py -q
```

Speech service tests:

```bash
venv/bin/pytest tests/test_speech_service.py -q
```

Whitespace check:

```bash
git diff --check
```

Known unrelated stale tests:

```text
tests/test_workspace_static.py has stale assertions from unrelated earlier production changes.
Those failures were previously confirmed not to be STT/TTS regressions.
Do not edit them as part of STT/TTS work unless separately approved.
```

## Current Source Touch Map

Backend:

- `main.py`: security headers, route-aware body perimeter, `/api/speech/transcribe`, `/api/users/{user_id}/speech/synthesize`, sanitized provider failure logging.
- `speech_service.py`: Cloud Speech-to-Text V2 adapter, Cloud Text-to-Speech Chirp 3 HD adapter, MIME allowlist, config loading, deterministic TTS chunking, approved voice map.
- `database.py`: canonical completed model-message lookup.
- `requirements.txt`: Google speech and text-to-speech client dependencies.

Frontend:

- `frontend/index.html`: composer speech control anchors: Mic, voice select, Spoken responses toggle, Stop, speech status.
- `frontend/api.mjs`: raw STT upload and raw TTS audio chunk fetch helpers.
- `frontend/app.mjs`: MediaRecorder lifecycle, STT transcript insertion/auto-submit, TTS chunk playback, Stop cleanup, spoken-response toggle behavior.
- `frontend/chat-view.mjs`: ordinary composer insertion/submission helpers and transcript rendering without bubble Speak buttons.
- `frontend/styles.css`: compact speech control styling.

Tests:

- `tests/test_main.py`: FastAPI speech endpoints, middleware/security, canonical TTS contract, sanitized provider errors.
- `tests/test_speech_service.py`: speech provider adapters, config, request construction, chunking.
- `tests/frontend/api.test.mjs`: frontend API contracts.
- `tests/frontend/app-runtime.test.mjs`: browser runtime STT/TTS behavior.
- `tests/frontend/chat-view.test.mjs`: composer and transcript rendering.
- `tests/frontend/workspace-static.test.mjs`: static layout/security assertions.

## Things Not Implemented

- No live streaming transcription.
- No wake words.
- No continuous listening.
- No backend/server-side voice activity detection.
- Browser-side RMS silence detection is implemented only to stop the existing
  local MediaRecorder flow after trailing silence.
- No automatic full-duplex voice conversation.
- No Gemini TTS.
- No voice bake-off tooling.
- No Cloud Run deployment mutation in source.
- Merge to `main` was requested after Pass 6D manual acceptance.

## Recommended Next Work

Before adding more features, deploy or smoke-test `main` in the intended Cloud
Run-like environment after the STT/TTS branch merge is complete.

Suggested next pass:

```text
Pass 7: Cloud Run deployment readiness and runtime verification
```

Scope:

- verify required Google APIs are enabled;
- identify Cloud Run runtime service account;
- verify or add required IAM roles;
- verify environment variables for Speech and TTS;
- run local and deployed smoke checks for STT, TTS, typed chat, and spoken-response toggle;
- do not add new speech UX features in the same pass.

If deployment is deferred, the next source pass should be small and UI-only, for example persistence of the spoken-response toggle preference if the user wants it to survive reloads. Do not add that unless explicitly approved.
