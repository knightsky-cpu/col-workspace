# Chat Response Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add true progressive assistant-response streaming to the Agent Col chat surface so model text appears while it is being generated, while preserving the same final model response, prompts, receipts, artifacts, memory, notes, continuity behavior, retry semantics, and persistence.

**Architecture:** This is a separately approved behavior pass, not a safe visual-only CSS pass. Keep the existing `/api/chat` JSON endpoint unchanged and add a parallel streaming path for ordinary chat turns first. Use Google ADK `StreamingMode.SSE` in the responder runtime, translate only public Agent_Col partial text into app-owned SSE frames, and finalize with the existing `ChatResponse` semantics.

**Tech Stack:** Python 3 async generators, FastAPI `StreamingResponse`, Google ADK `RunConfig(streaming_mode=StreamingMode.SSE)`, browser `fetch()` response streams, vanilla JavaScript modules, Node frontend tests, pytest backend tests, Cloud Run streaming verification.

**Spec:** `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md`, `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md`, current `frontend/index.html`, current `frontend/app.mjs`, current `frontend/api.mjs`, current `frontend/state.mjs`, current `frontend/chat-view.mjs`, current `main.py`, current `agent_col_turn_service.py`, current `supervisor_runtime.py`, official ADK/FastAPI/MDN/Cloud Run documentation cited below.

## Global Constraints

- Preserve the user's ideal target: true streamed model output while the model generates, not fake line-by-line reveal after the full response is already available.
- Do not change prompts, responder instructions, model behavior, final response text, hidden working-state injection, memory/notes/artifact/continuity semantics, or retry request construction.
- Do not stream raw ADK events, tool-call arguments, function responses, routing decisions, hidden working state, source text, provider payloads, user IDs, project IDs, session IDs, or internal reasoning.
- Keep existing `/api/chat` JSON behavior available as fallback and as the path for structured decision turns in the first implementation pass.
- The visible streamed text must equal the final persisted `ChatResponse.response`, modulo leading/trailing whitespace normalization if ADK emits a final aggregated event with trimmed text.
- Receipts, artifacts, memory proposals, memory clarifications, collaborative note proposals/events, continuity receipts/choices, and adaptations remain authoritative structured effects and should appear only after final completion.
- Use TDD. No production behavior change before a failing test proves the desired behavior.
- Cloud Run response streaming must be manually verified after deployment because local tests cannot prove that the deployed path is not buffered by platform/proxy behavior.

---

## Official Documentation Findings

Google ADK `RunConfig` supports `StreamingMode.SSE`, where `runner.run_async()` yields partial events as the LLM generates text. `StreamingMode.NONE` is the default. See:

- <https://adk.dev/runtime/runconfig/>

ADK event docs define the key split this plan must preserve: streaming chunks are identified by `event.partial`, while final displayable turn output is identified separately with `event.is_final_response()`. See:

- <https://adk.dev/events/>

Local installed ADK source confirms the same behavior and adds a critical duplicate-text warning:

- `requirements.txt` pins `google-adk==2.7.0`, `google-genai==2.18.1`, `fastapi==0.141.1`, and `uvicorn==0.52.4`.
- `venv/lib/python3.14/site-packages/google/adk/agents/_streaming_mode.py` defines `StreamingMode.SSE`.
- That file states that SSE mode yields both partial text chunks and a final aggregated text event. Do not display both as visible assistant text.

FastAPI supports `StreamingResponse` from async generators. Its docs also note that cancellation only happens when async code reaches an `await`, which matters for disconnected clients and long streams. See:

- <https://fastapi.tiangolo.com/advanced/custom-response/>

Browser `EventSource` is not appropriate for Agent Col's current chat shape because it is GET-only, while Agent Col chat submits a POST JSON body with idempotency and authorization headers. Use `fetch()` and `ReadableStream`/`TextDecoderStream` instead. See:

- <https://web.dev/articles/eventsource-basics>
- <https://developer.mozilla.org/en-US/docs/Web/API/Streams_API>
- <https://developer.mozilla.org/en-US/docs/Web/API/TextDecoderStream>

Cloud Run supports HTTP response streaming with no additional feature flag, but the service must return a chunked streaming response. Cloud Run request timeout still applies: default 300 seconds, maximum 3600 seconds. See:

- <https://docs.cloud.google.com/run/docs/triggering/https-request>
- <https://docs.cloud.google.com/run/docs/configuring/request-timeout>

---

## Source-Backed Boundary Findings

### This Is Not A Safe Visual-Only Pass

The safe visual guide allows CSS-only styling of `.chat-transcript`, `.turn`, `.turn-user`, `.turn-model`, `.receipt-list`, `.receipt-item`, `.composer`, and `.chat-error`, but this streaming work changes request flow, backend response mechanics, frontend state, and rendering timing.

Relevant guide boundaries:

- `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md:41` marks frontend JavaScript modules as behavior-bearing surfaces.
- `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md:59` marks backend routes, auth, API handlers, schemas, persistence, prompts, memory, notes, artifacts, and working state as not visual-only.
- `docs/superpowers/plans/safe-frontend-visual-appearance-change-boundaries.md:153` allows chat transcript styling but forbids prompt changes, working-state changes, receipt construction changes, retry payload changes, model output changes, memory output changes, adaptation receipt changes, and continuity receipt changes in a visual-only pass.
- `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md:5` defines the visual plan as behavior-preserving.
- `docs/superpowers/plans/2026-08-28-frontend-visual-improvement-plan.md:60` locks JavaScript and backend for visual work.

Therefore, this plan is a separately approved behavior pass.

### Current Frontend Behavior

Current `frontend/app.mjs` waits for a complete JSON response from `/api/chat` before rendering the model response:

```js
// frontend/app.mjs:579
async function submitRequest(request) {
  state = beginPendingTurn(state, request);
  renderWorkspace();
  document.querySelector("[data-chat-error]").hidden = true;
  setText(document.querySelector("[data-chat-status]"), "Waiting for Agent Col");
  try {
    const response = await apiFetchJson("/api/chat", {
      method: "POST",
      idempotencyKey: request.key,
      authToken: state.context?.auth_token ?? null,
      body: request.body,
    });
    state = completePendingTurn(state, response);
```

Current `frontend/chat-view.mjs` paints the full model response at once with text-safe rendering:

```js
// frontend/chat-view.mjs:69
export function renderTranscript(container, transcript) {
  container.replaceChildren();
  for (const turn of transcript) {
    const article = element("article", "turn");
    const user = element("p", "turn-user");
    const model = element("p", "turn-model");
    setText(user, turn.request?.body?.message ?? "");
    setText(model, turn.response?.response ?? "");
```

Current `frontend/state.mjs` stores only the request while a turn is pending:

```js
// frontend/state.mjs:234
export function beginPendingTurn(state, request) {
  if (state.pendingTurn !== null) {
    throw new Error("A turn is already pending.");
  }
  return {
    ...state,
    pendingTurn: request,
    lastFailure: null,
  };
}
```

Current `frontend/api.mjs` has a JSON-only helper that reads the complete body before returning:

```js
// frontend/api.mjs:93
export async function apiFetchJson(
  path,
  options = {},
  fetchLike = globalThis.fetch,
) {
  assertSameOriginPath(path);
  const headers = { ...(options.headers ?? {}) };
```

The existing HTML already has a live chat transcript target and should not need markup changes:

```html
<!-- frontend/index.html:192 -->
<div class="chat-transcript" data-chat-transcript aria-live="polite"></div>
```

### Current Backend Behavior

Current `main.py` exposes one JSON route:

```python
# main.py:2232
@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
```

The backend does not create a `ChatResponse` until `turn_service.run_turn(...)` returns:

```python
# main.py:2952
try:
    result = await turn_service.run_turn(
        AgentColTurnCommand(
            project_id=effective_project_id,
            session_id=payload.session_id,
```

The final response and structured effects are assembled after the turn result:

```python
# main.py:3144
chat_response = ChatResponse(
    response=result.response,
    actions=list(_merge_receipts(decision_actions, result.actions)),
    artifacts=list(result.artifacts),
    artifact_feedback=list(result.artifact_feedback),
    citations=list(result.citations),
```

`schemas.py` defines the current final response contract:

```python
# schemas.py:847
class ChatResponse(StrictModel):
    response: NonEmptyStr
    actions: list[AgentActionReceipt] = Field(default_factory=list)
    artifacts: list[ArtifactReference] = Field(default_factory=list)
```

### Current ADK Runtime Behavior

Current runtime imports only `RunConfig`, not `StreamingMode`:

```python
# supervisor_runtime.py:8
from google.adk.agents.run_config import RunConfig
```

Current runtime builds non-streaming run config:

```python
# supervisor_runtime.py:241
config = RunConfig(
    max_llm_calls=SUPERVISOR_MAX_LLM_CALLS,
    model_input_context=model_input_context,
)
```

Current runtime already consumes ADK events:

```python
# supervisor_runtime.py:249
async for event in self._runner.run_async(
    user_id=context.user_id,
    session_id=invocation_session_id,
    new_message=message,
    run_config=config,
):
```

Current runtime only stores final Agent_Col responses:

```python
# supervisor_runtime.py:416
if (
    getattr(event, "author", "Agent_Col") == "Agent_Col"
    and event.is_final_response()
):
    text = self._extract_text(event)
    if text:
        final_responses.append(text)
```

---

## Expected File Map

### Expected To Modify

- `supervisor_runtime.py`
  - Add ADK `StreamingMode` import.
  - Add public streaming event dataclasses.
  - Add a streaming runtime method that uses `RunConfig(streaming_mode=StreamingMode.SSE)`.
  - Filter ADK partial events to public Agent_Col text only.
  - Preserve final response validation and receipt extraction.

- `agent_col_turn_service.py`
  - Extend `ResponderRuntime` protocol with a streaming method.
  - Add `AgentColTurnService.stream_turn(...)` beside existing `run_turn(...)`.
  - Reuse existing orchestration/deadline/receipt behavior as much as possible.

- `main.py`
  - Add `POST /api/chat/stream`.
  - Return `StreamingResponse` with `media_type="text/event-stream"`.
  - Reuse validation, auth, idempotency, history, memory, notes, continuity, working-state, and final persistence rules from `/api/chat`.
  - Convert app-owned stream events into SSE frames.

- `frontend/api.mjs`
  - Add POST-compatible streaming fetch helper.
  - Add minimal SSE frame parser.
  - Preserve same-origin validation and API error normalization.

- `frontend/state.mjs`
  - Change pending turn shape narrowly to support a streamed assistant draft.
  - Add `appendPendingResponseDelta(...)`.
  - Preserve exact retry envelope and final transcript shape.

- `frontend/chat-view.mjs`
  - Render completed turns plus one pending streamed turn.
  - Continue using `setText()` / `textContent`.
  - Hide receipts for pending streamed turn until final `ChatResponse`.

- `frontend/app.mjs`
  - Add `submitStreamingRequest(...)` for ordinary chat.
  - Keep structured decision paths on existing `submitRequest(...)` in Pass 1.
  - Preserve refresh behavior after final completion.
  - Add non-sensitive timing logs for first visible delta and total completion.

### Expected To Add Or Modify Tests

- `tests/test_supervisor_runtime.py`
- `tests/test_agent_col_turn_service.py`
- `tests/test_main.py`
- `tests/frontend/api.test.mjs`
- `tests/frontend/state.test.mjs`
- `tests/frontend/chat-view.test.mjs`
- Optionally `tests/frontend/app.test.mjs` only if existing app orchestration tests already make this practical.

### Expected Not To Touch

- `frontend/index.html`
  - Existing `data-chat-transcript` and `aria-live="polite"` are sufficient for this pass.

- `frontend/requests.mjs`
  - Retry/idempotency request builders should remain unchanged unless a failing test proves a narrow compatibility extension is required.

- `frontend/styles.css`
  - No visual restyle is required. A minimal `.turn-pending` style is allowed only if needed for manual clarity.

- Prompt files, responder instructions, memory policy, artifact schemas, note lifecycle services, continuity services, and working-state services.

---

## Task 1: Runtime Streaming Event Extraction

**Files:**
- Modify: `supervisor_runtime.py`
- Test: `tests/test_supervisor_runtime.py`

**Interfaces:**
- Consumes: existing `SupervisorTurnContext`, `SupervisorTurnResult`, `Runner.run_async(...)`.
- Produces:
  - `SupervisorResponseDelta(text: str)`
  - `SupervisorResponseComplete(result: SupervisorTurnResult)`
  - `SupervisorRuntime.stream_turn(context: SupervisorTurnContext) -> AsyncIterator[SupervisorResponseDelta | SupervisorResponseComplete]`

- [ ] **Step 1: Write failing tests for ADK SSE mode**

Add tests proving the streaming path sets `RunConfig.streaming_mode == StreamingMode.SSE`.

Conceptual test:

```python
async def test_stream_turn_sets_adk_sse_streaming_mode() -> None:
    runner = FakeRunner(events=[
        partial_text_event("Hel"),
        partial_text_event("lo"),
        final_text_event("Hello"),
    ])
    runtime = SupervisorRuntime(
        runner=runner,
        session_service=FakeSessionService(),
    )

    events = [
        event async for event in runtime.stream_turn(
            SupervisorTurnContext(
                project_id="project-1",
                session_id="session-1",
                user_id="user-1",
                message="hello",
            )
        )
    ]

    assert runner.calls[0]["run_config"].streaming_mode is StreamingMode.SSE
    assert [type(event) for event in events] == [
        SupervisorResponseDelta,
        SupervisorResponseDelta,
        SupervisorResponseComplete,
    ]
```

- [ ] **Step 2: Write failing tests for public event filtering**

Add tests proving partial function-call chunks and function responses do not become public deltas.

Conceptual test:

```python
async def test_stream_turn_yields_only_partial_agent_text() -> None:
    runner = FakeRunner(events=[
        partial_text_event("Public", author="Agent_Col"),
        partial_function_call_event(name="propose_memory_signal"),
        function_response_event(name="propose_memory_signal"),
        partial_text_event("Other", author="SourceExpert"),
        final_text_event("Public"),
    ])
    runtime = SupervisorRuntime(
        runner=runner,
        session_service=FakeSessionService(),
    )

    events = [
        event async for event in runtime.stream_turn(valid_context())
    ]

    assert [
        event.text for event in events
        if isinstance(event, SupervisorResponseDelta)
    ] == ["Public"]
```

- [ ] **Step 3: Write failing test for duplicate final aggregation**

ADK SSE emits partial chunks and final aggregated text. The streaming runtime must not yield final text as another delta.

Conceptual test:

```python
async def test_stream_turn_does_not_duplicate_final_aggregated_text() -> None:
    runner = FakeRunner(events=[
        partial_text_event("Hel"),
        partial_text_event("lo"),
        final_text_event("Hello"),
    ])
    runtime = SupervisorRuntime(
        runner=runner,
        session_service=FakeSessionService(),
    )

    events = [
        event async for event in runtime.stream_turn(valid_context())
    ]

    assert "".join(
        event.text for event in events
        if isinstance(event, SupervisorResponseDelta)
    ) == "Hello"
    assert events[-1].result.response == "Hello"
```

- [ ] **Step 4: Verify RED**

Run:

```bash
venv/bin/python -m pytest tests/test_supervisor_runtime.py -k "stream" -v
```

Expected: fail because `stream_turn`, streaming dataclasses, or `StreamingMode.SSE` usage do not exist yet.

- [ ] **Step 5: Implement minimal runtime streaming**

Update imports:

```python
from google.adk.agents.run_config import RunConfig, StreamingMode
```

Add dataclasses:

```python
@dataclass(frozen=True)
class SupervisorResponseDelta:
    text: str


@dataclass(frozen=True)
class SupervisorResponseComplete:
    result: SupervisorTurnResult
```

Add a streaming method that closely mirrors `run_turn(...)`, but uses SSE mode:

```python
async def stream_turn(
    self,
    context: SupervisorTurnContext,
) -> AsyncIterator[SupervisorResponseDelta | SupervisorResponseComplete]:
    # Reuse the same setup, trackers, session state, RunConfig shape,
    # final validation, and cleanup behavior as run_turn(...).
    config = RunConfig(
        streaming_mode=StreamingMode.SSE,
        max_llm_calls=SUPERVISOR_MAX_LLM_CALLS,
        model_input_context=model_input_context,
    )
```

Filter partial public text:

```python
if (
    event.partial is True
    and getattr(event, "author", "Agent_Col") == "Agent_Col"
    and not event.get_function_calls()
    and not event.get_function_responses()
):
    text = self._extract_text(event)
    if text:
        streamed_parts.append(text)
        yield SupervisorResponseDelta(text=text)
```

Use final response only for authoritative result:

```python
if (
    getattr(event, "author", "Agent_Col") == "Agent_Col"
    and event.is_final_response()
):
    text = self._extract_text(event)
    if text:
        final_responses.append(text)
```

Validate visible streamed text against final text:

```python
streamed_text = "".join(streamed_parts)
final_text = final_responses[0]
if streamed_text and streamed_text.strip() != final_text.strip():
    raise SupervisorRuntimeError(
        "Streamed public response did not match final response.",
        actions=tuple(actions),
        memory_proposals=tuple(memory_proposals),
        memory_clarifications=tuple(memory_clarifications),
        collaborative_note_proposals=tuple(collaborative_note_proposals),
        collaborative_note_events=tuple(collaborative_note_events),
    )
```

Yield completion:

```python
yield SupervisorResponseComplete(
    result=SupervisorTurnResult(
        response=final_text,
        actions=tuple(actions),
        citations=tuple(citations),
        memory_proposals=tuple(memory_proposals),
        memory_clarifications=tuple(memory_clarifications),
        collaborative_note_proposals=tuple(collaborative_note_proposals),
        collaborative_note_events=tuple(collaborative_note_events),
    )
)
```

- [ ] **Step 6: Verify GREEN**

Run:

```bash
venv/bin/python -m pytest tests/test_supervisor_runtime.py -k "stream" -v
```

Expected: pass.

---

## Task 2: Agent Turn Service Streaming Wrapper

**Files:**
- Modify: `agent_col_turn_service.py`
- Test: `tests/test_agent_col_turn_service.py`

**Interfaces:**
- Consumes: `ResponderRuntime.stream_turn(...)`.
- Produces: `AgentColTurnService.stream_turn(...)` yielding `AgentColResponseDelta` and `AgentColResponseComplete` or equivalent app-level stream events.

- [ ] **Step 1: Write failing test for ordinary streaming turn**

Conceptual test:

```python
async def test_stream_turn_yields_deltas_then_complete_result() -> None:
    responder = FakeResponderRuntime(stream_events=[
        SupervisorResponseDelta("Hel"),
        SupervisorResponseDelta("lo"),
        SupervisorResponseComplete(SupervisorTurnResult(response="Hello")),
    ])
    service = make_turn_service(responder_runtime=responder)

    events = [
        event async for event in service.stream_turn(valid_command())
    ]

    assert [event.text for event in events[:-1]] == ["Hel", "lo"]
    assert events[-1].result.response == "Hello"
```

- [ ] **Step 2: Write failing test preserving timeout/error mapping**

Conceptual test:

```python
async def test_stream_turn_maps_responder_timeout_like_run_turn() -> None:
    responder = FakeResponderRuntime(error=SupervisorTimeoutError(
        "timeout",
        actions=(completed_action,),
    ))
    service = make_turn_service(responder_runtime=responder)

    with pytest.raises(AgentColTurnTimeoutError) as exc_info:
        async for _event in service.stream_turn(valid_command()):
            pass

    assert exc_info.value.actions == (completed_action,)
```

- [ ] **Step 3: Verify RED**

Run:

```bash
venv/bin/python -m pytest tests/test_agent_col_turn_service.py -k "stream" -v
```

Expected: fail because turn-service streaming path does not exist.

- [ ] **Step 4: Implement minimal service streaming**

Extend protocol:

```python
class ResponderRuntime(Protocol):
    async def run_turn(
        self,
        context: SupervisorTurnContext,
    ) -> SupervisorTurnResult: ...

    async def stream_turn(
        self,
        context: SupervisorTurnContext,
    ) -> AsyncIterator[
        SupervisorResponseDelta | SupervisorResponseComplete
    ]: ...
```

Add service stream method beside `run_turn(...)`:

```python
async def stream_turn(
    self,
    command: AgentColTurnCommand,
) -> AsyncIterator[AgentColResponseDelta | AgentColResponseComplete]:
    deadline = self._clock() + self._turn_timeout_seconds
    try:
        async with asyncio.timeout(self._turn_timeout_seconds):
            # Pass 1: ordinary non-artifact-feedback turns only unless tests
            # explicitly cover broader routes.
            async for event in self._responder_runtime.stream_turn(
                SupervisorTurnContext(...)
            ):
                if isinstance(event, SupervisorResponseDelta):
                    yield AgentColResponseDelta(text=event.text)
                else:
                    yield AgentColResponseComplete(
                        result=AgentColTurnResult(
                            response=event.result.response,
                            actions=_stable_merge(
                                command.precompleted_actions,
                                event.result.actions,
                            ),
                            ...
                        )
                    )
    except TimeoutError as exc:
        raise AgentColTurnTimeoutError(...)
```

Use existing run-turn error classes and receipt merging patterns. Do not invent new persistence semantics here.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
venv/bin/python -m pytest tests/test_agent_col_turn_service.py -k "stream" -v
```

Expected: pass.

---

## Task 3: Backend `/api/chat/stream` SSE Endpoint

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `AgentColTurnService.stream_turn(...)`.
- Produces: `POST /api/chat/stream` returning `text/event-stream`.

- [ ] **Step 1: Write failing route test**

Conceptual test:

```python
async def test_chat_stream_returns_deltas_then_final_response(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.turn_service.stream_events = [
        AgentColResponseDelta(text="Hel"),
        AgentColResponseDelta(text="lo"),
        AgentColResponseComplete(result=AgentColTurnResult(response="Hello")),
    ]

    async with client.stream(
        "POST",
        "/api/chat/stream",
        headers={
            "Idempotency-Key": "chat--stream-1",
            "Accept": "text/event-stream",
        },
        json={
            "project_id": "project-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "hello",
        },
    ) as response:
        body = await response.aread()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = body.decode("utf-8")
    assert 'event: response_delta' in text
    assert 'data: {"text":"Hel"}' in text
    assert 'event: response_complete' in text
    assert '"response":"Hello"' in text
```

- [ ] **Step 2: Write failing privacy/filtering test**

Conceptual test:

```python
async def test_chat_stream_does_not_expose_private_context(
    client: httpx.AsyncClient,
    service_state: ServiceState,
) -> None:
    service_state.turn_service.stream_events = [
        AgentColResponseDelta(text="Public answer."),
        AgentColResponseComplete(
            result=AgentColTurnResult(response="Public answer.")
        ),
    ]

    response = await client.post(
        "/api/chat/stream",
        headers={"Idempotency-Key": "chat--stream-private"},
        json={
            "project_id": "private-project",
            "session_id": "private-session",
            "user_id": "private-user",
            "message": "private prompt text",
        },
    )

    assert "private-project" not in response.text
    assert "private-session" not in response.text
    assert "private-user" not in response.text
    assert "private prompt text" not in response.text
```

- [ ] **Step 3: Verify RED**

Run:

```bash
venv/bin/python -m pytest tests/test_main.py -k "chat_stream" -v
```

Expected: fail because `/api/chat/stream` does not exist.

- [ ] **Step 4: Implement app-owned SSE formatting**

Add helper:

```python
def _sse_frame(event: str, data: dict[str, object]) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, separators=(',', ':'))}\n\n"
    )
```

Add route:

```python
from fastapi.responses import StreamingResponse


@app.post("/api/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    authorization: Annotated[
        str | None,
        Header(alias="Authorization"),
    ] = None,
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async for event in _stream_chat_turn_events(
            payload=payload,
            request=request,
            idempotency_key=idempotency_key,
            authorization=authorization,
        ):
            yield event
            await asyncio.sleep(0)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

Translate only app-owned stream events:

```python
if isinstance(event, AgentColResponseDelta):
    yield _sse_frame("response_delta", {"text": event.text})
elif isinstance(event, AgentColResponseComplete):
    chat_response = _chat_response_from_turn_result(...)
    await _persist_completed_chat_response(...)
    yield _sse_frame(
        "response_complete",
        chat_response.model_dump(mode="json"),
    )
```

Important: avoid copy-paste drift from `/api/chat`. If extracting shared helpers from existing `chat(...)`, keep the extraction narrow and covered by existing tests. Preserve all existing validations for auth, idempotency, structured decisions, history, memory, notes, continuity, working state, and persistence.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
venv/bin/python -m pytest tests/test_main.py -k "chat_stream" -v
```

Expected: pass.

---

## Task 4: Frontend SSE Fetch Helper

**Files:**
- Modify: `frontend/api.mjs`
- Test: `tests/frontend/api.test.mjs`

**Interfaces:**
- Consumes: browser `fetch()` `Response.body`.
- Produces:
  - `apiFetchSse(path, options, handlers, fetchLike)`
  - `parseSseStream(body, handlers)`
  - parsed events shaped as `{ type, data }`.

- [ ] **Step 1: Write failing split-frame parser test**

Conceptual test:

```js
test("apiFetchSse parses split SSE frames in order", async () => {
  const events = [];
  const chunks = [
    "event: response_delta\ndata: {\"text\":\"Hel\"}\n",
    "\nevent: response_delta\ndata: {\"text\":\"lo\"}\n\n",
    "event: response_complete\ndata: {\"response\":\"Hello\"}\n\n",
  ];

  await apiFetchSse("/api/chat/stream", {
    method: "POST",
    idempotencyKey: "chat--1",
    body: { message: "hello" },
  }, {
    onEvent(event) {
      events.push(event);
    },
  }, fakeStreamingFetch(chunks));

  assert.deepEqual(events, [
    { type: "response_delta", data: { text: "Hel" } },
    { type: "response_delta", data: { text: "lo" } },
    { type: "response_complete", data: { response: "Hello" } },
  ]);
});
```

- [ ] **Step 2: Write failing same-origin test**

Conceptual test:

```js
test("apiFetchSse rejects remote URLs like apiFetchJson", async () => {
  await assert.rejects(
    () => apiFetchSse("https://example.com/api/chat/stream", {}, {}, async () => {
      throw new Error("fetch should not run");
    }),
    /same-origin/,
  );
});
```

- [ ] **Step 3: Verify RED**

Run:

```bash
node --test tests/frontend/api.test.mjs
```

Expected: fail because `apiFetchSse` does not exist.

- [ ] **Step 4: Implement streaming fetch helper**

Do not use `EventSource`; it cannot POST. Use `fetch()`:

```js
export async function apiFetchSse(
  path,
  options = {},
  handlers = {},
  fetchLike = globalThis.fetch,
) {
  assertSameOriginPath(path);
  const headers = {
    ...(options.headers ?? {}),
    Accept: "text/event-stream",
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  if (options.authToken) {
    headers.Authorization = `Bearer ${options.authToken}`;
  }

  const response = await fetchLike(path, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    const body = await parseBody(response);
    throw normalizeApiError(response, body);
  }
  await parseSseStream(response.body, handlers);
}
```

Parser:

```js
async function parseSseStream(body, handlers) {
  if (!body) {
    throw new Error("Streaming response body is unavailable.");
  }
  const reader = body
    .pipeThrough(new TextDecoderStream())
    .getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += value;
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = parseSseFrame(frame);
      if (event !== null) {
        handlers.onEvent?.(event);
      }
    }
  }
}
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
node --test tests/frontend/api.test.mjs
```

Expected: pass.

---

## Task 5: Frontend Pending Stream State

**Files:**
- Modify: `frontend/state.mjs`
- Test: `tests/frontend/state.test.mjs`

**Interfaces:**
- Consumes: existing `beginPendingTurn`, `failPendingTurn`, `completePendingTurn`.
- Produces: `appendPendingResponseDelta(state, text)`.

- [ ] **Step 1: Write failing pending-delta test**

Conceptual test:

```js
test("pending streamed deltas accumulate without completing transcript", () => {
  const request = Object.freeze({
    key: "chat--1",
    body: Object.freeze({ message: "hello" }),
  });
  let state = beginPendingTurn(createInitialState(), request);

  state = appendPendingResponseDelta(state, "Hel");
  state = appendPendingResponseDelta(state, "lo");

  assert.equal(state.pendingTurn.request, request);
  assert.equal(state.pendingTurn.streamedResponse, "Hello");
  assert.equal(state.transcript.length, 0);
});
```

- [ ] **Step 2: Write failing exact retry compatibility test**

Conceptual test:

```js
test("failed streamed turn preserves exact retry request", () => {
  const request = Object.freeze({
    key: "chat--1",
    body: Object.freeze({ message: "hello" }),
  });
  const pending = appendPendingResponseDelta(
    beginPendingTurn(createInitialState(), request),
    "partial",
  );
  const failed = failPendingTurn(
    pending,
    { message: "network failed", status: 0 },
  );

  assert.equal(failed.lastFailure.request, request);
});
```

- [ ] **Step 3: Verify RED**

Run:

```bash
node --test tests/frontend/state.test.mjs
```

Expected: fail because `appendPendingResponseDelta` and the new pending shape do not exist.

- [ ] **Step 4: Implement pending stream state**

Narrowly change pending turn shape:

```js
export function beginPendingTurn(state, request) {
  if (state.pendingTurn !== null) {
    throw new Error("A turn is already pending.");
  }
  return {
    ...state,
    pendingTurn: {
      request,
      streamedResponse: "",
    },
    lastFailure: null,
  };
}
```

Add delta appender:

```js
export function appendPendingResponseDelta(state, text) {
  if (state.pendingTurn === null) {
    return state;
  }
  return {
    ...state,
    pendingTurn: {
      ...state.pendingTurn,
      streamedResponse: state.pendingTurn.streamedResponse + text,
    },
  };
}
```

Update `failPendingTurn(...)`:

```js
lastFailure: {
  request: state.pendingTurn?.request ?? state.pendingTurn,
  message: error.message,
  status: error.status ?? null,
  retryAfterSeconds: error.retryAfterSeconds ?? null,
},
```

Update `completePendingTurn(...)` transcript append:

```js
{
  request: state.pendingTurn.request,
  response,
}
```

Audit helper functions that inspect `state.pendingTurn`:

- `isMemoryClarificationSelectionRequest(...)`
- `isContinuitySelectionRequest(...)`
- `selectCanSubmit(...)`
- tests around pending turn lifecycle.

If helpers expect a request object, pass `state.pendingTurn?.request` rather than the wrapper.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
node --test tests/frontend/state.test.mjs
```

Expected: pass.

---

## Task 6: Frontend Transcript Rendering For Pending Stream

**Files:**
- Modify: `frontend/chat-view.mjs`
- Test: `tests/frontend/chat-view.test.mjs`

**Interfaces:**
- Consumes: `state.transcript`, `state.pendingTurn`.
- Produces: transcript render that includes completed turns plus one pending assistant draft.

- [ ] **Step 1: Write failing pending render test**

Conceptual test:

```js
test("renderTranscript renders pending streamed response without receipts", () => {
  const container = node();

  renderTranscript(container, [], {
    request: { body: { message: "hello" } },
    streamedResponse: "Streaming now",
  });

  assert.equal(container.querySelector(".turn-user").textContent, "hello");
  assert.equal(
    container.querySelector(".turn-model").textContent,
    "Streaming now",
  );
  assert.equal(container.querySelector(".turn-receipts"), null);
});
```

- [ ] **Step 2: Write failing XSS safety test for pending stream**

Conceptual test:

```js
test("renderTranscript uses textContent for pending streamed response", () => {
  const container = node();

  renderTranscript(container, [], {
    request: { body: { message: "hello" } },
    streamedResponse: "<img src=x onerror=alert(1)>",
  });

  assert.equal(
    container.querySelector(".turn-model").textContent,
    "<img src=x onerror=alert(1)>",
  );
});
```

- [ ] **Step 3: Verify RED**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs
```

Expected: fail because `renderTranscript` does not accept/render pending streamed turns.

- [ ] **Step 4: Implement pending render support**

Extract a turn renderer:

```js
function renderTurn(request, response, options = {}) {
  const article = element(
    "article",
    options.pending ? "turn turn-pending" : "turn",
  );
  const user = element("p", "turn-user");
  const model = element("p", "turn-model");
  setText(user, request?.body?.message ?? "");
  setText(model, response?.response ?? "");
  article.append(user, model);
  if (!options.pending) {
    const receipts = element("div", "turn-receipts");
    renderReceipts(receipts, response ?? {});
    article.append(receipts);
  }
  return article;
}
```

Update `renderTranscript`:

```js
export function renderTranscript(container, transcript, pendingTurn = null) {
  container.replaceChildren();
  for (const turn of transcript) {
    container.append(renderTurn(turn.request, turn.response));
  }
  if (pendingTurn !== null) {
    container.append(renderTurn(
      pendingTurn.request,
      { response: pendingTurn.streamedResponse },
      { pending: true },
    ));
  }
}
```

Update `createChatView.render(...)`:

```js
renderTranscript(
  elements.transcript,
  state.transcript,
  state.pendingTurn,
);
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
node --test tests/frontend/chat-view.test.mjs
```

Expected: pass.

---

## Task 7: Frontend Submit Streaming Path

**Files:**
- Modify: `frontend/app.mjs`
- Test: use focused frontend module tests; add `tests/frontend/app.test.mjs` only if existing app tests support this without broad harness work.

**Interfaces:**
- Consumes: `apiFetchSse`, `appendPendingResponseDelta`, existing ordinary request builder.
- Produces: ordinary chat uses `/api/chat/stream`; structured decisions keep `/api/chat`.

- [ ] **Step 1: Write failing test for ordinary streaming submit if harness exists**

Conceptual test:

```js
test("ordinary chat submit renders streamed deltas before final completion", async () => {
  const fetchLike = fakeStreamingFetch([
    "event: response_delta\ndata: {\"text\":\"Hel\"}\n\n",
    "event: response_delta\ndata: {\"text\":\"lo\"}\n\n",
    "event: response_complete\ndata: {\"response\":\"Hello\"}\n\n",
  ]);

  await submitOrdinaryChatForTest({ message: "hello", fetchLike });

  assert.equal(screenTranscriptText(), "hello Hello");
});
```

If no practical app harness exists, request an explicit TDD exception for this integration slice and compensate with the module-level tests from Tasks 4-6 plus manual browser verification.

- [ ] **Step 2: Implement ordinary streaming submit**

Import:

```js
import {
  apiFetchJson,
  apiFetchSse,
  ...
} from "./api.mjs";
```

Import state helper:

```js
import {
  appendPendingResponseDelta,
  beginPendingTurn,
  completePendingTurn,
  ...
} from "./state.mjs";
```

Add streaming submit:

```js
async function submitStreamingRequest(request) {
  state = beginPendingTurn(state, request);
  renderWorkspace();
  document.querySelector("[data-chat-error]").hidden = true;
  setText(document.querySelector("[data-chat-status]"), "Waiting for Agent Col");
  const submittedAt = performance.now();
  let firstDeltaAt = null;
  let finalResponse = null;
  try {
    await apiFetchSse("/api/chat/stream", {
      method: "POST",
      idempotencyKey: request.key,
      authToken: state.context?.auth_token ?? null,
      body: request.body,
    }, {
      onEvent(event) {
        if (event.type === "response_delta") {
          if (firstDeltaAt === null) {
            firstDeltaAt = performance.now();
            console.info(
              "chat_stream_first_delta_ms",
              firstDeltaAt - submittedAt,
            );
          }
          state = appendPendingResponseDelta(state, event.data.text);
          renderWorkspace();
        }
        if (event.type === "response_complete") {
          finalResponse = event.data;
        }
      },
    });
    if (finalResponse === null) {
      throw new Error("Streaming response ended before completion.");
    }
    state = completePendingTurn(state, finalResponse);
    setText(document.querySelector("[data-chat-status]"), "");
    document.querySelector("[data-chat-input]").value = "";
    await refreshAfterChatResponse(finalResponse);
  } catch (error) {
    state = failPendingTurn(state, error);
    setText(document.querySelector("[data-chat-error]"), error.message);
    document.querySelector("[data-chat-error]").hidden = false;
  }
  renderWorkspace();
}
```

If `submitRequest(...)` currently owns refresh behavior inline, extract only the existing post-completion refresh block:

```js
async function refreshAfterChatResponse(response) {
  const refreshPlan = selectWorkRefreshPlan(response);
  if (refreshPlan.reloadList) {
    await loadWorkList();
  }
  if (refreshPlan.selectArtifactId !== null) {
    await loadWorkDetail(refreshPlan.selectArtifactId);
  }
  const receiptRefresh = selectNeedsReceiptRefresh(response);
  if (receiptRefresh.memory) {
    await loadMemory();
  }
  if (receiptRefresh.notes) {
    await loadNotes();
  }
  await loadChatSessions();
}
```

Route only ordinary submit through streaming:

```js
onSubmit(message) {
  if (!selectCanSubmit(state)) {
    return;
  }
  const request = buildOrdinaryChatRequest(state.context, message);
  submitStreamingRequest(request);
},
```

Keep existing `submitRequest(...)` for:

- exact retry;
- memory clarification selection;
- continuity selection.

Do not change request builders or idempotency-key format.

- [ ] **Step 3: Verify frontend focused tests**

Run:

```bash
node --test tests/frontend/api.test.mjs
node --test tests/frontend/state.test.mjs
node --test tests/frontend/chat-view.test.mjs
```

Expected: pass.

---

## Task 8: Focused Integration Verification

**Files:**
- No new source unless tests expose a narrow defect in approved touched files.

- [ ] **Step 1: Run backend focused tests**

```bash
venv/bin/python -m pytest tests/test_supervisor_runtime.py -k "stream" -v
venv/bin/python -m pytest tests/test_agent_col_turn_service.py -k "stream" -v
venv/bin/python -m pytest tests/test_main.py -k "chat_stream" -v
```

Expected: pass.

- [ ] **Step 2: Run frontend focused tests**

```bash
node --test tests/frontend/api.test.mjs
node --test tests/frontend/state.test.mjs
node --test tests/frontend/chat-view.test.mjs
```

Expected: pass.

- [ ] **Step 3: Run syntax/static sanity checks**

```bash
venv/bin/python -m py_compile supervisor_runtime.py agent_col_turn_service.py main.py
git diff --check
```

Expected: pass with no whitespace errors.

- [ ] **Step 4: Manual local curl streaming check**

Start the app in local dev mode using the repo's normal command, then run:

```bash
curl -N -X POST "http://127.0.0.1:8000/api/chat/stream" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "Idempotency-Key: chat--manual-stream-check" \
  -d '{"project_id":"PROJECT","session_id":"SESSION","user_id":"USER","message":"Write a short deployment checklist."}'
```

Expected:

- `response_delta` frames arrive before `response_complete`;
- final `response_complete.response` equals the visible streamed text;
- no raw ADK events, function-call arguments, hidden context, user IDs, project IDs, session IDs, prompt text, or provider payloads appear.

- [ ] **Step 5: Manual browser verification**

Open `/workspace` and verify:

1. Sending an ordinary prompt starts visible assistant text before final completion.
2. The text does not duplicate when the final response arrives.
3. Receipts appear only after final completion.
4. Refreshing/reopening the chat shows the same final response text from persisted transcript.
5. Exact retry still works through the existing JSON path.
6. Memory clarification, continuity selection, artifact feedback, and collaborative note decisions still use existing behavior.
7. The transcript remains readable with the visual direction in `agent-col-visual-target.jpeg`; no visual restyle is required in this pass.

- [ ] **Step 6: Manual Cloud Run streaming verification**

After deployment, run:

```bash
curl -N -X POST "$SERVICE_URL/api/chat/stream" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "Idempotency-Key: chat--cloud-run-stream-check" \
  -d '{"project_id":"PROJECT","session_id":"SESSION","user_id":"USER","message":"Write three short bullet points."}'
```

Expected:

- chunks arrive progressively over the deployed Cloud Run service;
- response is not buffered until the end;
- request completes inside Cloud Run timeout;
- disconnected/retried requests remain governed by existing idempotency behavior.

---

## Latency Measurement Requirements

This pass improves perceived latency by making the first assistant text visible earlier. It does not necessarily reduce total model completion latency.

Measure:

- submit-to-first-delta milliseconds;
- submit-to-final-complete milliseconds;
- final persistence/refresh duration after `response_complete`.

Frontend concept:

```js
const submittedAt = performance.now();
let firstDeltaAt = null;

if (event.type === "response_delta" && firstDeltaAt === null) {
  firstDeltaAt = performance.now();
  console.info("chat_stream_first_delta_ms", firstDeltaAt - submittedAt);
}
```

Backend concept:

```python
logger.info(
    "chat_stream_timing stage=first_delta elapsed_ms=%s",
    elapsed_ms,
)
```

Do not log prompt text, response text, user IDs, project IDs, session IDs, hidden working state, raw ADK events, or provider payloads.

---

## Known Exclusions

- No fake typewriter reveal of already-complete responses.
- No WebSocket or ADK BIDI streaming in this pass.
- No prompt changes.
- No Markdown renderer changes.
- No raw ADK event streaming to browser.
- No streaming of tool events, function-call arguments, hidden context, provider payloads, or internal reasoning.
- No structured decision streaming in Pass 1.
- No broad frontend visual restyle in this pass.
- No dependency upgrade unless official/local compatibility evidence proves current pinned packages cannot support the required behavior.

---

## Stop Conditions

Stop and ask for revised approval if any of these happen:

- ADK partial text cannot be isolated from function-call chunks.
- Streamed public text cannot be reconciled with final `ChatResponse.response`.
- Implementing streaming requires changing prompts or responder instructions.
- Implementing streaming requires changing retry request construction.
- Implementing streaming requires exposing raw ADK events or hidden working state to the browser.
- The `/api/chat` JSON route would need to be removed or behaviorally changed.
- Structured decision turns must be changed to make ordinary streaming work.
- Cloud Run buffers the streaming response despite local success and requires infrastructure changes outside this pass.

---

## Final Implementation Report Requirements

When implemented, report using the repository pass-report template:

- Pass status: `Implemented, pending manual verification.`
- Behavior-level summary.
- Files changed.
- TDD evidence with RED, GREEN, and REFACTOR notes.
- Focused verification commands and exact results.
- Scope deviations or limitations.
- Manual local/browser/Cloud Run verification targets.
- Proposed next pass, with approval required before implementation.
