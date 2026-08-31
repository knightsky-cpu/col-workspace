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

## Current Manual Acceptance

The user manually verified:

```text
STT works.
TTS works.
Pass 6B behavior is working well.
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
- No voice activity detection.
- No automatic full-duplex voice conversation.
- No Gemini TTS.
- No voice bake-off tooling.
- No Cloud Run deployment mutation in source.
- No merge to `main`.

## Recommended Next Work

Before adding more features, deploy or smoke-test the current branch in the intended Cloud Run-like environment.

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
