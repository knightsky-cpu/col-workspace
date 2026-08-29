# M7-EXP.4D-R3.2 Vertex Routing Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to execute this plan inline. Do not use
> subagents for this repository-owner-approved pass.

**Goal:** Prove that Vertex AI accepts and returns the richer R3.1
`AgentColRoutingDirective` while keeping production chat orchestration
unchanged.

**Architecture:** Add an isolated provider adapter that sends the bounded
`AgentColRoutingInput` to Gemini through the existing Vertex ADC client and
strictly validates the returned directive. Add a separate CLI smoke runner
that exercises direct, clarify, Source, and Research compatibility cases
without executing experts or touching FastAPI, ADK, or Firestore.

**Tech Stack:** Python 3.14, Pydantic v2, Google Gen AI SDK, Vertex AI ADC,
pytest

**Spec:**
`docs/superpowers/specs/2026-08-21-phase-3b-m7-exp-4d-r3-production-model-routing-design.md`

## Global constraints

- Reuse `AgentColRoutingInput`, `AgentColRoutingDirective`, and exact-input
  validation from R3.1.
- Reuse `vertex_config.py`; do not introduce an API key or new environment
  contract.
- Use `gemini-3.6-flash`, JSON structured output, temperature zero,
  `ThinkingLevel.MINIMAL`, and an initial 256-token output limit.
- The provider request has no tools and performs no expert execution.
- Keep provider, timeout, malformed-output, and exact-input mismatch failures
  distinct and content-safe.
- Do not modify `main.py`, FastAPI, ADK, Firestore, dependencies, or the
  accepted R2 spike.
- Do not commit or push until manual compatibility verification is accepted.

---

### Task 1: Isolated Vertex routing provider boundary

**Files:**

- Create: `agent_col_routing_provider.py`
- Create: `tests/test_agent_col_routing_provider.py`

**Interfaces:**

- Consumes: `AgentColRoutingInput`
- Produces: `build_agent_col_routing_response_schema()`
- Produces: `request_agent_col_routing_directive(client, routing_input)`
- Produces safe provider, timeout, and output exceptions

- [ ] Write a failing schema test requiring the canonical route enum, nested
  intents, strict objects, and removal of local-only schema constraints.
- [ ] Implement only the provider-safe schema builder and verify GREEN.
- [ ] Write failing async request tests requiring delimited untrusted routing
  input, no tools, JSON output, minimal thinking, temperature zero, 256 output
  tokens, strict parsing, and exact-input validation.
- [ ] Implement the minimum async provider request and verify GREEN.
- [ ] Write failing tests for provider, timeout, malformed output, and
  incompatible directive classifications without content leakage.
- [ ] Implement only the missing safe failure handling and verify GREEN.

### Task 2: Reproducible live compatibility runner

**Files:**

- Create: `smoke_test_agent_col_routing.py`
- Create: `tests/test_smoke_test_agent_col_routing.py`
- Create: `tests/fixtures/agent_col_routing_contract_cases.json`

**Interfaces:**

- Consumes: `request_agent_col_routing_directive()`
- Produces: one-command Vertex compatibility evidence

- [ ] Write failing fixture and runner tests for direct, clarify, Source, and
  Research cases, bounded repetitions, safe outcome codes, Vertex settings,
  and complete async/sync client shutdown.
- [ ] Implement the strict fixture loader and runner, then verify GREEN.
- [ ] Run focused provider, runner, R3.1 contract, Vertex configuration, and
  prior routing-spike tests.
- [ ] Stop at implemented, pending manual verification. Do not call Vertex
  automatically; give the repository owner the live command.

## Focused verification

```bash
venv/bin/pytest -q tests/test_agent_col_routing_provider.py tests/test_smoke_test_agent_col_routing.py
venv/bin/pytest -q tests/test_agent_col_routing.py tests/test_vertex_config.py tests/test_agent_col_routing_spike.py
venv/bin/python -m py_compile agent_col_routing_provider.py smoke_test_agent_col_routing.py
git diff --check
```

## Manual acceptance

```bash
source venv/bin/activate && python3 smoke_test_agent_col_routing.py --repetitions 1
```

Acceptance requires valid direct, clarify, Source, and Research directives,
no expert execution, exit status zero, and no content-bearing error output.
