# M7-EXP.5A Computational Expert Compatibility Spike

**Goal:** Verify, without changing production routing, that Agent_Col's pinned
Vertex AI and ADK stack exposes enough native execution evidence to support a
future trustworthy Computational Expert.

## Decision boundary

This pass answers one question:

> Does Vertex AI `global` + `gemini-3.6-flash` + Google ADK 2.7.0 +
> `BuiltInCodeExecutor` return observable, locally validatable Python
> `executable_code` and `code_execution_result` events?

The answer requires a live manual run. Offline tests prove the local evidence
contract and runner topology; they cannot prove provider compatibility.

## Implemented boundary

- One isolated `LlmAgent` in `single_turn` mode, wrapped by a one-node ADK
  `Workflow` because ADK permits only `chat` or `task` agents as direct roots.
- `BuiltInCodeExecutor(timeout_seconds=30)` and no model-facing tools.
- No sub-agents, transfers, files, network access, user input, persistence, or
  FastAPI integration.
- One fixed statistics prompt over a non-sensitive literal data set.
- One temporary in-memory ADK session, always deleted after the invocation.
- At most two LLM calls and a 60-second application timeout.
- Event validation accepts only ordered Python `executable_code` /
  `code_execution_result` pairs authored by the spike agent.
- Code and output are each capped at 8,000 characters.
- Raw code and raw execution output are never printed or logged; diagnostics
  contain counts, lengths, outcomes, and a content-safe status only.

## Exit contract

- `0`: at least one bounded Python execution completed with `OUTCOME_OK`, and
  no execution failed or exceeded its deadline.
- `1`: the provider responded, but execution evidence was absent, malformed,
  oversized, failed, or deadline-exceeded.
- `2`: Vertex configuration or provider execution failed before trustworthy
  evidence could be evaluated.

## TDD coverage

- Prose-only output is not accepted as computation.
- Failed and deadline-exceeded results cannot complete.
- A mixed failed/successful run remains failed.
- Oversized code or output is rejected.
- Successful native Python evidence produces exit `0` and content-safe
  metrics.
- The exact model, Vertex client settings, executor, and isolated agent
  topology are asserted.
- The default runner path is regression-tested to mount the `single_turn`
  specialist beneath `computational_executor_spike_workflow`, rather than
  directly as the application root.
- Temporary session creation, event collection, and cleanup are asserted.
- Configuration and provider failures use exit `2` without leaking values or
  provider payloads.
- The real script entry point propagates its exit code.
- The repository `.env` path is explicit and reproducible.

## Manual compatibility command

Run from the repository root with the virtual environment activated:

```bash
python3 computational_executor_spike.py; printf 'exit=%s\n' "$?"
```

Acceptance requires output shaped like:

```text
computational-executor-spike completed executions=1 successful=1 code_chars=<positive> output_chars=<positive> outcomes=OUTCOME_OK
exit=0
```

An ADK deprecation warning about `BaseAgentConfig` is an upstream ADK 2.7.0
warning already present in neighboring agent-construction tests. It is not a
compatibility success signal and does not replace the required execution
evidence.

## Explicit exclusions

- No production `ComputationalExpert` class or public result schema.
- No `run_computation` receipt or chat response integration.
- No routing changes or model-facing tool registration.
- No user-authored code, file ingestion, plotting, package installation,
  shell access, or network access.
- No Firestore writes or durable job orchestration.
- No Requirements Verification implementation.

If the live run returns exit `0`, the smallest next pass is the Computational
Expert provider/evidence boundary. If it returns exit `1` or `2`, production
implementation must stop until the observed provider limitation is diagnosed.
