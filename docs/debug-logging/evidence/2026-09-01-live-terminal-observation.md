# Live Terminal Observation - 2026-09-01

## Launch

```text
AGENT_COL_AUTH_MODE=google_oidc venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## Observed Pattern

The server started successfully, served `/workspace`, loaded frontend modules,
and returned `200 OK` for repeated `/api/chat/stream` requests during the manual
stress prompts.

The raw terminal output contained repeated access logs like:

```text
INFO:     127.0.0.1:<PORT> - "POST /api/chat/stream HTTP/1.1" 200 OK
INFO:     127.0.0.1:<PORT> - "GET /api/projects/[PROJECT_ID]/artifacts?limit=20&lifecycle_status=active HTTP/1.1" 200 OK
INFO:     127.0.0.1:<PORT> - "GET /api/users/[USER_ID]/projects/[PROJECT_ID]/notes?limit=20&status_filter=active HTTP/1.1" 200 OK
INFO:     127.0.0.1:<PORT> - "GET /api/users/[USER_ID]/memory HTTP/1.1" 200 OK
INFO:     127.0.0.1:<PORT> - "GET /api/users/[USER_ID]/projects/[PROJECT_ID]/chat-sessions?limit=20 HTTP/1.1" 200 OK
```

The terminal also showed these recurring warnings:

```text
Direct use of automatic function calling (AFC) in AsyncModels.generate_content is not recommended. Instead, we recommend to use AFC in AsyncChat.send_message. Similarly, direct use of AFC in AsyncModels.generate_content_stream is not recommended. Instead, we recommend to use AFC in AsyncChat.send_message_stream.

/Users/wifiknight/col-workspace/venv/lib/python3.14/site-packages/google/adk/models/llm_request.py:273: UserWarning: [EXPERIMENTAL] feature FeatureName.JSON_SCHEMA_FOR_FUNC_DECL is enabled.

/Users/wifiknight/col-workspace/venv/lib/python3.14/site-packages/google/adk/models/google_llm.py:276: UserWarning: [EXPERIMENTAL] feature FeatureName.PROGRESSIVE_SSE_STREAMING is enabled.

/Users/wifiknight/col-workspace/venv/lib/python3.14/site-packages/google/cloud/firestore_v1/base_collection.py:317: UserWarning: Detected filter using positional arguments. Prefer using the 'filter' keyword argument instead.
```

## Failure Evidence

No random failure was reproduced in this run.

No `ChatTurnStateError` was reproduced in this run.

No visible `Agent_Col chat pipeline` or `Agent_Col turn pipeline` module-log
lines appeared in the pasted terminal output, even though the focused automated
tests prove those log records are emitted under test capture.

## Evidence Interpretation

The diagnostic code path is covered by automated tests, but live stdout
visibility remains unproven. The likely next diagnostic boundary is Python /
Uvicorn logging configuration, not chat routing behavior.
