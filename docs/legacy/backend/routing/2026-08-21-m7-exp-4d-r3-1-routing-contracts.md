# M7-EXP.4D-R3.1 Routing Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline. Do not use
> subagents for this repository-owner-approved pass.

**Goal:** Define the strict production routing directive, bounded routing
input, server-derived public URL candidate projection, and local
directive-to-input validation without changing live chat orchestration.

**Architecture:** Add one pure `agent_col_routing.py` contract module. Pydantic
models validate Agent_Col's versioned route and capability-specific intent;
pure application functions project public URL candidates from user-authored
text and validate selected candidate IDs against the exact routing input.
Nothing in this pass calls a model, expert, database, FastAPI route, or ADK
runner.

**Tech Stack:** Python 3.14, Pydantic v2, existing Source Expert URL
validation, pytest

**Spec:**
`docs/superpowers/specs/2026-08-21-phase-3b-m7-exp-4d-r3-production-model-routing-design.md`

## Global constraints

- Agent_Col remains the semantic route decision-maker.
- This pass defines contracts only; it does not integrate production routing.
- Route version 1.0 supports `direct`, `clarify`, `source`, and `research`.
- Exactly one route-specific payload is accepted.
- Source selections reference server-issued URL IDs rather than model-authored
  URLs.
- URL candidates originate only from current or recent user-authored text and
  must pass the existing Source public-URL boundary.
- Routing input excludes profiles, raw full history, server identifiers,
  credentials, and persistence data.
- No dependency, public endpoint, Firestore, ADK, or runtime change belongs in
  this pass.
- Do not commit or push until the repository owner manually accepts the pass.

---

### Task 1: Strict versioned routing directive

**Files:**

- Create: `agent_col_routing.py`
- Create: `tests/test_agent_col_routing.py`

**Interfaces:**

- Produces: `AgentColRoute`
- Produces: `SourceRoutingIntent`
- Produces: `ResearchRoutingIntent`
- Produces: `AgentColRoutingDirective`

- [ ] **Step 1: Write RED tests for valid route-specific payloads**

Create literal examples for:

```python
AgentColRoutingDirective(route="direct")
AgentColRoutingDirective(
    route="clarify",
    clarifying_question="Which supplied page should I analyze?",
)
AgentColRoutingDirective(
    route="source",
    source_intent={
        "objective": "Compare the two supplied pages.",
        "selected_url_ids": ["url-1", "url-2"],
        "constraints": ["Use only retrieved evidence."],
    },
)
AgentColRoutingDirective(
    route="research",
    research_intent={
        "question": "What is the current stable Python release?",
        "objective": "Verify the current release with public evidence.",
        "constraints": [],
    },
)
```

Assert whitespace normalization, immutable tuple collections, and default
`schema_version == "1.0"`.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_routing.py -k valid
```

Expected: import failure because `agent_col_routing` does not exist.

- [ ] **Step 3: Implement the minimum strict models**

Use frozen Pydantic models with `extra="forbid"` and
`hide_input_in_errors=True`. Exact bounds:

- question, objective: 1 through 1,000 stripped characters;
- clarification: 1 through 300 stripped characters;
- constraint: 1 through 300 stripped characters;
- zero through five constraints;
- one through three unique Source URL IDs matching `url-[1-8]`.

Add one cross-field validator enforcing:

```text
direct   -> no question and no intent
clarify  -> question only
source   -> Source intent only
research -> Research intent only
```

- [ ] **Step 4: Verify GREEN**

Run the same focused command and require every valid-directive test to pass.

- [ ] **Step 5: Write and verify RED tests for rejected structures**

Cover extra fields, wrong schema version, mismatched route payloads, hidden
rationale, duplicate URL IDs, four URL IDs, six constraints, whitespace-only
text, and over-bound text. Each literal must fail with `ValidationError`.

- [ ] **Step 6: Implement only missing validation and verify GREEN**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_routing.py -k directive
```

---

### Task 2: Bounded routing input and URL candidate projection

**Files:**

- Modify: `agent_col_routing.py`
- Modify: `tests/test_agent_col_routing.py`

**Interfaces:**

- Produces: `RoutingUrlSource`
- Produces: `RoutingUrlCandidate`
- Produces: `AgentColRoutingInput`
- Produces:
  `project_routing_url_candidates(current_message, recent_user_messages)`

- [ ] **Step 1: Write a RED projection test**

Use a current message containing two URLs and chronological prior
user-authored messages containing one duplicate, one recent public URL, one
private URL, and trailing sentence punctuation. Require:

```text
url-1 current_message first current URL
url-2 current_message second current URL
url-3 recent_user_history newest remaining public URL
```

Require normalized public URLs, deterministic ordering, deduplication, and no
private URL candidate.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_routing.py -k projection
```

Expected: missing projection interface.

- [ ] **Step 3: Implement the pure projection**

- Extract only explicit `http://` and `https://` tokens.
- Strip sentence punctuation without rewriting URL paths or query values.
- Validate each candidate by constructing the existing strict
  `SourceExpertInput` with one URL.
- Process the current message first, then prior user messages newest to oldest.
- Deduplicate by normalized URL.
- Stop at eight candidates.
- Return immutable `RoutingUrlCandidate` models using IDs `url-1` through
  `url-8` and provenance `current_message` or `recent_user_history`.

- [ ] **Step 4: Verify GREEN**

Run the projection test and inspect the literal candidate sequence.

- [ ] **Step 5: Write RED tests for input bounds and isolation**

Require `AgentColRoutingInput` to:

- accept a stripped current message of at most 10,000 characters;
- accept zero through eight unique candidates;
- accept only unique available capabilities `source` and `research`;
- reject empty or oversized messages, duplicate candidate IDs/URLs, invalid
  provenance, computation capability, profile data, identifiers, and extra
  fields.

- [ ] **Step 6: Implement missing input validation and verify GREEN**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_routing.py -k "input or projection"
```

---

### Task 3: Validate a directive against its exact routing input

**Files:**

- Modify: `agent_col_routing.py`
- Modify: `tests/test_agent_col_routing.py`

**Interfaces:**

- Produces: `RoutingDirectiveInputError`
- Produces:
  `validate_routing_directive_for_input(directive, routing_input)`

- [ ] **Step 1: Write RED tests for authoritative mapping**

Require a Source directive selecting `url-2` and `url-1` to validate against
an input containing both IDs without changing selection order. Require a
Research directive to validate only when `research` is available. Require
direct and clarify to validate without expert capability access.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_routing.py -k for_input
```

Expected: missing validation function.

- [ ] **Step 3: Implement minimum cross-boundary validation**

The function returns the same immutable directive on success. It raises the
single safe `RoutingDirectiveInputError("Routing directive is incompatible "
"with its input.")` when:

- the selected capability is unavailable;
- a Source ID is absent from the exact routing input;
- Source has no projected URL candidates.

The exception and logs must not include messages, URLs, identifiers, or model
output.

- [ ] **Step 4: Verify GREEN and related regressions**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_routing.py
venv/bin/pytest -q tests/test_agent_col_routing_spike.py tests/test_source_expert.py
venv/bin/python -m py_compile agent_col_routing.py tests/test_agent_col_routing.py
git diff --check
```

Inspect all exit codes, failures, warnings, and skipped tests. Stop at
**implemented, pending manual verification**.

## Manual acceptance targets

R3.1 has no live model, server, or Firestore behavior. Manual verification is
the focused offline contract command:

```bash
source venv/bin/activate && pytest -q tests/test_agent_col_routing.py
```

Success requires every test to pass with no warnings. Existing `/api/chat`
behavior must remain unchanged because no production consumer imports this
module yet.

## Stop and revise conditions

Stop for a revised design if:

- URL projection requires a new parser dependency;
- public URL validation cannot reuse the current Source boundary safely;
- directive validation requires profile, full-history, or server-ID access;
- the richer contract cannot remain provider-schema compatible without a
  redesign;
- implementation requires modifying FastAPI, ADK, Firestore, or dependencies.
