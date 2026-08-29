# Revised Pass Plan U9B: Streaming Chat Rendering

Date: 2026-08-28

Status: documented plan only. Chat improvement implementation is frozen until this plan is explicitly approved for a future source-changing pass.

## TLDR

Do not implement streaming by calling Google GenAI directly from the chat route. The official Google GenAI SDK and Gemini API support streaming, but this application's production response path is ADK `Runner.run_async` inside `SupervisorRuntime`, wrapped by the turn service and FastAPI chat orchestration. Direct model streaming would bypass routing, artifacts, memory and note proposals, continuity receipts, idempotency, persistence, and the existing final `ChatResponse` contract.

The revised implementation should stream through ADK SSE mode in the supervisor runtime, expose a same-origin `POST /api/chat/stream` endpoint, and let the frontend consume backend-owned stream events with `fetch` and `ReadableStream`. Keep `/api/chat` as the non-stream fallback and keep structured decision flows on the existing JSON path unless implementation evidence proves they can safely share the streaming route.

## Official Documentation Evidence

- Google GenAI Python SDK documents synchronous and asynchronous `generate_content_stream` APIs, including `client.aio.models.generate_content_stream(...)`: <https://googleapis.github.io/python-genai/>
- Gemini API documents `models.streamGenerateContent` and the REST streaming endpoint form `POST .../{model=models/*}:streamGenerateContent`: <https://ai.google.dev/api/generate-content>
- Gemini API docs describe streaming as server-sent events for faster interactive applications such as chatbots: <https://ai.google.dev/api>
- ADK runtime docs describe event-loop streaming: one model response may yield multiple events with `partial=True`, and the final event is non-partial/complete: <https://adk.dev/runtime/event-loop/>
- ADK event docs define event content, author, actions, partial state, and final response helpers such as `is_final_response()`: <https://adk.dev/events/>
- FastAPI documents `StreamingResponse` for streaming async iterables: <https://fastapi.tiangolo.com/advanced/stream-data/>
- Browser Fetch documentation shows response bodies can be consumed incrementally with streams and `TextDecoderStream`: <https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch>
- Cloud Run supports streaming HTTP responses without special configuration: <https://docs.cloud.google.com/run/docs/triggering/https-request>

## Local Source Evidence

- `requirements.txt` pins `google-adk==2.7.0`, `google-genai==2.18.1`, `fastapi==0.141.1`, and `uvicorn==0.52.4`.
- Local ADK inspection confirmed `RunConfig` accepts `streaming_mode`, `StreamingMode` includes `SSE`, and `Runner.run_async(...)` accepts `run_config`.
- Local ADK source comments for `StreamingMode.SSE` confirm it yields progressive partial events while the LLM generates text and also yields a final aggregated response. The implementation must avoid displaying both as duplicate text.
- `supervisor_runtime.py` currently imports `RunConfig` and consumes `Runner.run_async(...)`, but it does not set `streaming_mode`.
- `supervisor_runtime.py` currently records final Agent Col text only when `event.author == "Agent_Col"` and `event.is_final_response()`, so partial text events are ignored.
- `agent_col_turn_service.py` defines `ResponderRuntime.run_turn(...)` only; a streaming pass needs a parallel streaming contract rather than bypassing the service.
- `main.py` owns auth, idempotency-key validation, turn claim/replay, history/context loading, memory/note/continuity decisions, preference learning, response persistence, and final `ChatResponse` assembly.
- `frontend/app.mjs` currently submits chat turns through `apiFetchJson("/api/chat", ...)` and waits for the full response before updating the transcript.
- `frontend/chat-view.mjs` currently renders only completed transcript turns; it does not render pending assistant text.

## Revised Implementation Boundary

### Goal

Render ordinary model responses progressively in the chat surface, like text being written live, while preserving the cleaned Markdown response rendering and all existing backend contracts.

### Non-Goals

- Do not redesign the chat card visuals in this pass.
- Do not change drawer/menu/subcard behavior.
- Do not change artifact viewer layout.
- Do not replace ADK orchestration with direct GenAI calls.
- Do not remove or weaken idempotency, replay, persistence, memory, notes, continuity, artifacts, or receipt behavior.
- Do not convert every structured decision flow to streaming unless the implementation investigation proves that can be done safely inside this pass.

## Proposed Technical Approach

### 1. Backend Runtime Streaming

Add a streaming method to `SupervisorRuntime` that uses ADK:

- `RunConfig(streaming_mode=StreamingMode.SSE, ...)`
- `Runner.run_async(...)`
- partial Agent Col events as text deltas
- final Agent Col event as the canonical complete response

The runtime must still observe tool/function responses for research, source, memory, and collaborative-note receipts. The final `SupervisorTurnResult` remains the authoritative completion value.

### 2. Turn Service Streaming

Extend the responder runtime protocol with a stream-capable method and add an `AgentColTurnService` streaming path.

The turn service should preserve existing routing, expert execution, artifact-capable routing, and artifact execution. The stream should start for the final responder phase after any required routing/expert/artifact prework has completed.

### 3. FastAPI Streaming Endpoint

Add `POST /api/chat/stream` beside the existing `POST /api/chat`.

The endpoint should preserve the same request payload, auth resolution, idempotency behavior, turn claim/replay behavior, history/context loading, decision handling, persistence, and final `ChatResponse` shape.

Use application-level SSE frames over a same-origin POST response:

```text
event: delta
data: {"text":"..."}

event: final
data: {existing ChatResponse JSON}

event: error
data: {"detail":"...","status":502}
```

Replay behavior must emit only `final`, with no synthetic deltas.

### 4. Frontend Stream Helper

Add a stream helper in `frontend/api.mjs` that:

- enforces same-origin paths;
- sends `Authorization` and `Idempotency-Key`;
- posts JSON;
- consumes `response.body` incrementally;
- parses SSE events even when frames are split across network chunks;
- normalizes backend error events into the existing `ApiError` behavior where practical.

### 5. Frontend Pending Response State

Add explicit pending streamed response text in `frontend/state.mjs`.

Keep `pendingTurn` as the original request to avoid breaking retry/failure handling. Add a separate field such as `pendingResponseText`, append deltas into it, clear it on completion/failure/new conversation, and commit the final response through the existing `completePendingTurn(...)` path.

### 6. Chat Rendering

Update `frontend/chat-view.mjs` so the pending turn can render:

- the user's submitted message immediately;
- an in-progress model card as deltas arrive;
- receipts only after final completion;
- final canonical response through the existing safe Markdown renderer.

### 7. App Submission Flow

Update `frontend/app.mjs` to use streaming only for ordinary chat submissions at first.

Structured decision requests should continue through `/api/chat` unless the pass proves they are safe to stream without changing behavior. This preserves memory clarification, memory decisions, note decisions, artifact feedback decisions, and continuity choices.

## Expected Files To Touch

- `supervisor_runtime.py`
- `agent_col_turn_service.py`
- `main.py`
- `frontend/api.mjs`
- `frontend/state.mjs`
- `frontend/chat-view.mjs`
- `frontend/app.mjs`
- `tests/test_supervisor_runtime.py`
- `tests/test_agent_col_turn_service.py`
- `tests/test_main.py`
- `tests/frontend/api.test.mjs`
- `tests/frontend/state.test.mjs`
- `tests/frontend/chat-view.test.mjs`
- `tests/frontend/workspace-static.test.mjs`, only if import/export coverage requires it

## Expected Files Not To Touch

- `frontend/index.html`
- `frontend/markdown-renderer.mjs`, unless a failing test proves the final-render integration needs a small public helper
- drawer/menu/subcard modules
- artifact viewer layout modules
- memory/note/chats drawer behavior

## TDD Plan

1. RED: `SupervisorRuntime` emits text deltas from ADK partial Agent Col events and still returns one final response.
2. RED: partial text plus final aggregated text does not duplicate displayed content.
3. RED: `AgentColTurnService` streams through the existing artifact-capable orchestration while preserving final receipts.
4. RED: `/api/chat/stream` emits `delta` followed by `final` for a streamed turn.
5. RED: `/api/chat/stream` emits only `final` for an idempotent replay.
6. RED: frontend stream helper parses SSE events split across chunks.
7. RED: frontend state accumulates pending response deltas and clears them on final/failure/new conversation.
8. RED: chat view renders pending streamed assistant text and uses canonical Markdown rendering after final completion.

## Focused Verification Commands

```bash
venv/bin/python -m pytest tests/test_supervisor_runtime.py tests/test_agent_col_turn_service.py tests/test_main.py
node --test tests/frontend/api.test.mjs tests/frontend/state.test.mjs tests/frontend/chat-view.test.mjs tests/frontend/workspace-static.test.mjs
node --check frontend/api.mjs
node --check frontend/state.mjs
node --check frontend/chat-view.mjs
node --check frontend/app.mjs
git diff --check
```

## Manual Verification Targets

1. Submit a normal chat message and confirm the assistant card appears during the pending turn.
2. Confirm assistant text appears progressively as generated.
3. Confirm the final response does not duplicate streamed text.
4. Confirm final Markdown still renders cleanly with no raw `**`, `###`, or avoidable spacing artifacts.
5. Confirm receipts/adaptations appear only after final completion.
6. Confirm an artifact-producing request still creates/selects artifacts and returns a final response.
7. Confirm memory/note/continuity structured decisions still behave as before.
8. Confirm retry/replay with the same idempotency key does not duplicate streamed text.

## Risks And Stop Conditions

- Stop if reusing `/api/chat` logic requires a broad route rewrite. Extract only narrow helpers needed to avoid unsafe duplication.
- Stop if ADK partial event shape differs from official/local inspection during tests.
- Stop if streaming causes duplicated final text.
- Stop if the stream endpoint cannot preserve idempotency or persistence semantics.
- Stop if structured decision flows require broader state changes than this pass authorizes.
- Stop if source evidence shows the final responder phase cannot be streamed without bypassing artifact/memory/note/continuity contracts.

## Approval Boundary

This document records the revised U9B plan only. Implementing U9B requires a separate explicit approval.
