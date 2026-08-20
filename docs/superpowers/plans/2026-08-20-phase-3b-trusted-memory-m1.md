# Phase 3B Trusted Memory M1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan inline, task by task.
> Do not delegate to subagents. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Implement the pure, offline foundation for Agent_Col's governed
memory: bounded preference and low-sensitivity identity policy, strict domain
schemas, deterministic model-context rendering, and server-derived adaptation
receipts.

**Architecture:** `memory_policy.py` owns versioned allowlists, normalization,
category-value compatibility, grounding, ordering, and exact instructions.
The established `schemas.py` remains the single Pydantic contract module and
adds the normative memory models without changing the current chat API.
`memory_context.py` accepts only a validated `CollaborationProfile` and returns
an immutable rendered instruction block plus matching typed receipts. This M1
pass has no FastAPI, Firestore, Gemini, or ADK integration.

**Tech Stack:** Python 3.14.7, Pydantic 2.13.4, pytest 9.1.1,
pytest-asyncio 1.4.0

**Spec:**
`docs/superpowers/specs/2026-08-20-phase-3b-trusted-memory-design.md`

## Global constraints

- Execute inline and follow strict RED-GREEN-REFACTOR one behavior at a time.
- Keep `memory_schema_version` and `policy_version` fixed at `"1.0"`.
- Support exactly eight collaboration-preference categories, one preferred
  name, and one ordered list of one through three broad roles.
- Treat a preferred name as PII and broad roles as personal data; do not label
  this feature PII-free.
- Allow a preferred name only when it is explicitly present in the current
  user message at proposal validation time.
- Do not infer legal identity, expertise, employer, school, seniority,
  credentials, protected traits, health, finances, contact details, precise
  location, or other private facts.
- Use Unicode NFC normalization, collapsed internal whitespace, Unicode
  alphabetic checks, and the exact allowed punctuation for preferred names.
- Store broad roles in policy-defined order and reject duplicates.
- Render only active signals from a validated `CollaborationProfile`.
- Preserve current `ChatRequest`, `ChatResponse`, `/api/chat`,
  `/api/synthesize`, `MemoryEngine`, supervisor, and Firestore behavior.
- Add no routes, tools, persistence methods, environment variables,
  dependencies, network calls, model calls, or deployment configuration.
- Pytest remains fully offline.
- Logs and smoke output must not expose identifiers or stored memory values.
- Do not commit or push until the user completes manual verification and
  explicitly authorizes the checkpoint.

## File structure

- Create `memory_policy.py`: type aliases, version constants, allowlists,
  preferred-name validation and grounding, broad-role canonicalization,
  category-value compatibility, deterministic instruction lookup, and signal
  ordering.
- Modify `schemas.py`: strict memory proposal, active signal, profile, event,
  decision, and receipt models. Do not nest them into chat request/response in
  M1.
- Create `memory_context.py`: immutable rendered-context result and
  `MemoryContextRenderer`.
- Create `tests/test_memory_policy.py`: exhaustive policy, privacy-boundary,
  normalization, grounding, ordering, and instruction tests.
- Create `tests/test_memory_schemas.py`: strict Pydantic and cross-field tests.
- Create `tests/test_memory_context.py`: deterministic context and receipt
  tests.
- Create `smoke_test_memory_policy.py`: offline, pseudonymous manual runner.
- Create `tests/test_smoke_test_memory_policy.py`: smoke-runner regression.

---

### Task 1: Versioned memory policy and low-sensitivity identity boundary

**Files:**

- Create: `memory_policy.py`
- Create: `tests/test_memory_policy.py`

**Interfaces:**

- Produces `MEMORY_SCHEMA_VERSION = "1.0"`.
- Produces `MEMORY_POLICY_VERSION = "1.0"`.
- Produces the normative aliases `PreferenceCategory`,
  `IdentityContextCategory`, `MemoryCategory`, `PreferenceValue`, `BroadRole`,
  `PreferredNameStr`, `MemoryValue`, `MemoryDecision`,
  `ConfirmationChannel`, and `MemoryEventType`.
- Produces `PreferencePolicy.validate(category, value) -> PreferenceValue`.
- Produces `PreferencePolicy.instruction(category, value) -> str`.
- Produces `IdentityContextPolicy.validate(field, value, *,
  current_message=None, require_grounding=False) -> PreferredNameStr |
  list[BroadRole]`.
- Produces `IdentityContextPolicy.instruction(field, value) -> str`.
- Produces `validate_memory_value(category, value) -> MemoryValue`.
- Produces `memory_signal_sort_key(category) -> int`.
- Raises `ValueError` for all invalid policy inputs before any later Firestore
  boundary can be called.

- [ ] **Step 1: Write the category-value compatibility RED tests**

Create exhaustive tables in `tests/test_memory_policy.py` and begin with one
missing-module test:

```python
import pytest


@pytest.mark.parametrize(
    ("category", "value"),
    (
        ("response_length", "concise"),
        ("response_length", "balanced"),
        ("response_length", "detailed"),
        ("explanation_structure", "direct_then_steps"),
        ("explanation_structure", "step_by_step"),
        ("explanation_structure", "concept_then_example"),
        ("example_usage", "none"),
        ("example_usage", "when_helpful"),
        ("example_usage", "always_practical"),
        ("question_style", "ask_before_assuming"),
        ("question_style", "recommend_then_ask"),
        ("question_style", "minimal_follow_up"),
        ("planning_granularity", "milestones"),
        ("planning_granularity", "tasks"),
        ("planning_granularity", "micro_steps"),
        ("progress_check_ins", "only_when_blocked"),
        ("progress_check_ins", "at_milestones"),
        ("progress_check_ins", "frequent"),
        ("tool_use_style", "ask_before_external_tools"),
        ("tool_use_style", "use_when_needed"),
        ("tool_use_style", "minimize_tools"),
        ("formatting_style", "prose"),
        ("formatting_style", "bullets"),
        ("formatting_style", "mixed"),
    ),
)
def test_preference_policy_accepts_only_owned_category_values(
    category: str,
    value: str,
) -> None:
    from memory_policy import PreferencePolicy

    assert PreferencePolicy.validate(category, value) == value
```

Add a Cartesian mismatch test proving that a globally valid value such as
`"concise"` is rejected for `formatting_style`, plus tests rejecting unknown
categories, lists, integers, booleans, and arbitrary strings.

- [ ] **Step 2: Verify the first RED**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_memory_policy.py::test_preference_policy_accepts_only_owned_category_values \
  -v
```

Expected: collection fails with
`ModuleNotFoundError: No module named 'memory_policy'`.

- [ ] **Step 3: Implement the minimal preference aliases and validator**

Define the exact literals from the design and an immutable mapping:

```python
PREFERENCE_VALUES_BY_CATEGORY = {
    "response_length": frozenset({"concise", "balanced", "detailed"}),
    "explanation_structure": frozenset(
        {"direct_then_steps", "step_by_step", "concept_then_example"}
    ),
    "example_usage": frozenset(
        {"none", "when_helpful", "always_practical"}
    ),
    "question_style": frozenset(
        {"ask_before_assuming", "recommend_then_ask", "minimal_follow_up"}
    ),
    "planning_granularity": frozenset(
        {"milestones", "tasks", "micro_steps"}
    ),
    "progress_check_ins": frozenset(
        {"only_when_blocked", "at_milestones", "frequent"}
    ),
    "tool_use_style": frozenset(
        {"ask_before_external_tools", "use_when_needed", "minimize_tools"}
    ),
    "formatting_style": frozenset({"prose", "bullets", "mixed"}),
}
```

`PreferencePolicy.validate()` must require `type(value) is str`; membership in
another category's allowlist is not sufficient.

- [ ] **Step 4: Verify preference GREEN**

Run all current category-value tests and confirm they pass.

- [ ] **Step 5: Write preferred-name and broad-role RED tests**

Add tests proving:

```python
assert IdentityContextPolicy.validate(
    "preferred_name",
    "  Jose\u0301   O’Neil  ",
    current_message="My name is José O’Neil.",
    require_grounding=True,
) == "José O’Neil"

assert IdentityContextPolicy.validate(
    "broad_roles",
    ["researcher", "student"],
) == ["student", "researcher"]
```

Reject empty/whitespace names, more than 80 normalized characters, digits,
`@`, `/`, `:`, underscores, control characters, email addresses, URLs,
telephone-like values, names absent from the current message, and partial-word
matches such as `Ann` in `Anna`. Reject empty role lists, duplicates, more than
three roles, arbitrary roles, and non-list role values.

- [ ] **Step 6: Verify identity RED**

Run only the first preferred-name test. Expected: `IdentityContextPolicy` is
missing.

- [ ] **Step 7: Implement normalization, grounding, and role ordering**

The preferred-name algorithm is normative:

```python
normalized = unicodedata.normalize("NFC", value)
normalized = " ".join(normalized.split())
if not 1 <= len(normalized) <= 80:
    raise ValueError("Preferred name must contain 1 through 80 characters.")
if not any(character.isalpha() for character in normalized):
    raise ValueError("Preferred name must contain a letter.")
if any(
    not (character.isalpha() or character in " .'’-")
    for character in normalized
):
    raise ValueError("Preferred name contains a prohibited character.")
```

For grounding, compare NFC-normalized, whitespace-collapsed, case-folded text
and require `(?<!\w)<escaped-name>(?!\w)`. This prevents substring identity
claims. Canonicalize broad roles using this fixed order:

```python
BROAD_ROLE_ORDER = (
    "student",
    "professional",
    "educator",
    "researcher",
    "hobbyist",
    "retired",
    "career_transition",
)
```

- [ ] **Step 8: Add exact instruction and ordering tests**

Assert every category-value pair returns the exact instruction in the design,
both identity fields return their exact bounded instructions, and
`memory_signal_sort_key()` orders `preferred_name`, `broad_roles`, then the
eight preference categories in their documented order.

- [ ] **Step 9: Verify Task 1 GREEN**

Run:

```bash
venv/bin/python -m pytest tests/test_memory_policy.py -v
```

Expected: all memory-policy tests pass offline.

---

### Task 2: Strict memory domain schemas

**Files:**

- Modify: `schemas.py:1-97`
- Create: `tests/test_memory_schemas.py`

**Interfaces:**

- Consumes all normative aliases and validators from `memory_policy.py`.
- Produces `MemoryProposal`, `ActiveMemorySignal`, `CollaborationProfile`,
  `MemoryEvent`, `MemoryDecisionRequest`, `MemoryProposalReceipt`, and
  `AdaptationReceipt`.
- Preserves the existing `StrictModel`, `ChatRequest`, and `ChatResponse`
  contracts unchanged.
- Every model rejects extra fields.
- Every category/value-bearing model normalizes and validates the value against
  its selected category.

- [ ] **Step 1: Write the first proposal-schema RED test**

```python
from datetime import UTC, datetime, timedelta


def test_memory_proposal_accepts_normalized_bounded_value() -> None:
    from schemas import MemoryProposal

    created_at = datetime(2026, 8, 20, tzinfo=UTC)
    proposal = MemoryProposal.model_validate(
        {
            "proposal_id": "preferred_name--proposal-1",
            "category": "preferred_name",
            "proposed_value": "  Avery  ",
            "expected_signal_id": None,
            "policy_version": "1.0",
            "status": "pending",
            "source_session_id": "session-1",
            "source_message_id": "message-1",
            "created_at": created_at,
            "expires_at": created_at + timedelta(hours=24),
        }
    )

    assert proposal.proposed_value == "Avery"
```

- [ ] **Step 2: Verify proposal RED**

Run the named test. Expected: import fails because `MemoryProposal` does not
exist.

- [ ] **Step 3: Add the minimal models and private normalization helper**

Import `model_validator` and the policy aliases. Add one private helper that
copies an input mapping, validates its `category` and selected value field,
and replaces the value with its normalized form before normal Pydantic field
validation. Apply it to `MemoryProposal.proposed_value` and to the `value`
field of active signals, events, and receipts.

Use these exact bounds:

```python
class CollaborationProfile(StrictModel):
    memory_schema_version: Literal["1.0"] = "1.0"
    memory_revision: int = Field(default=0, ge=0)
    identity_context: dict[
        IdentityContextCategory,
        ActiveMemorySignal,
    ] = Field(default_factory=dict, max_length=2)
    active_preferences: dict[
        PreferenceCategory,
        ActiveMemorySignal,
    ] = Field(default_factory=dict, max_length=8)
```

Do not add these models to `ChatRequest` or `ChatResponse` during M1.

- [ ] **Step 4: Add profile invariant RED tests**

Test that:

- each map key equals the nested signal category;
- identity categories cannot appear in `active_preferences`;
- preference categories cannot appear in `identity_context`;
- more than two identity fields or eight preferences fail;
- negative revisions fail;
- default profile state is version `1.0`, revision zero, and two empty maps;
- unknown root fields fail rather than entering model context.

Expected RED: one or more invalid map-key/category combinations currently
validate because the cross-field validator is absent.

- [ ] **Step 5: Implement profile cross-field validation**

Add an `after` model validator that checks every map key against
`signal.category`. The typed key aliases and per-map length fields enforce the
category family and cardinality. Return `self` without mutating validated
signals.

- [ ] **Step 6: Add event and confirmation-channel RED tests**

Prove:

- `chat_decision` requires both confirmation session and message IDs;
- `memory_api` forbids both confirmation IDs;
- revision zero fails;
- source type other than `explicit_user_feedback` fails;
- unknown event types and policy versions fail;
- category-value mismatch fails;
- extra fields fail.

- [ ] **Step 7: Implement event cross-field validation**

Use one `after` validator with exactly two valid combinations:

```python
if self.confirmation_channel == "chat_decision":
    valid = (
        self.confirmation_session_id is not None
        and self.confirmation_message_id is not None
    )
else:
    valid = (
        self.confirmation_session_id is None
        and self.confirmation_message_id is None
    )
```

Raise `ValueError` when `valid` is false.

- [ ] **Step 8: Add strict decision and receipt tests**

Validate the exact `approve`/`reject` decision enum, proposal receipt expiry,
and `AdaptationReceipt.status == "provided_to_model"`. Prove all receipt
category-value mismatches and extra fields fail.

- [ ] **Step 9: Verify Task 2 GREEN and existing schema regressions**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_memory_schemas.py tests/test_schemas.py -v
```

Expected: new memory schemas and all existing chat/synthesis schemas pass.

---

### Task 3: Deterministic memory-context rendering and adaptation receipts

**Files:**

- Create: `memory_context.py`
- Create: `tests/test_memory_context.py`

**Interfaces:**

- Consumes `CollaborationProfile`, `ActiveMemorySignal`, and
  `AdaptationReceipt` from `schemas.py`.
- Consumes deterministic validation, instructions, and ordering from
  `memory_policy.py`.
- Produces immutable `RenderedMemoryContext(instruction_text: str,
  adaptations: tuple[AdaptationReceipt, ...])`.
- Produces `MemoryContextRenderer.render(profile) -> RenderedMemoryContext`.
- Returns empty text and receipts for an empty profile.
- Never accepts a raw Firestore dictionary, pending proposal, lifecycle event,
  history message, or arbitrary legacy profile field.

- [ ] **Step 1: Write the empty-context RED test**

```python
def test_renderer_returns_empty_result_for_empty_profile() -> None:
    from memory_context import MemoryContextRenderer
    from schemas import CollaborationProfile

    rendered = MemoryContextRenderer.render(CollaborationProfile())

    assert rendered.instruction_text == ""
    assert rendered.adaptations == ()
```

- [ ] **Step 2: Verify renderer RED**

Run the named test. Expected: `memory_context` cannot be imported.

- [ ] **Step 3: Implement the immutable empty path**

Create a frozen dataclass for `RenderedMemoryContext` and a stateless renderer.
Do not import Google GenAI types; wrapping the text in model content belongs to
M6.

- [ ] **Step 4: Write the complete deterministic rendering RED test**

Build a profile whose dictionaries are deliberately inserted out of order and
assert the exact output:

```text
[APPROVED_IDENTITY_CONTEXT]
- preferred_name=Avery: Address the user by their approved preferred name when natural; do not repeat it mechanically or treat it as verified legal identity.
- broad_roles=[student, researcher]: Use the approved broad role context only to calibrate examples and explanations; do not infer expertise, employer, school, seniority, or credentials.
[/APPROVED_IDENTITY_CONTEXT]
[APPROVED_COLLABORATION_PREFERENCES]
- response_length=concise: Keep the response compact while preserving information required to complete the request.
- example_usage=always_practical: Include one practical example when the task permits it.
[/APPROVED_COLLABORATION_PREFERENCES]
```

Assert the four adaptation receipts have the same order, IDs, categories,
normalized values, source event IDs, and `provided_to_model` status.

- [ ] **Step 5: Verify deterministic rendering RED**

Expected: the empty implementation does not render active signals.

- [ ] **Step 6: Implement ordered sections and receipts**

Render identity only when `identity_context` is nonempty and preferences only
when `active_preferences` is nonempty. Sort through
`memory_signal_sort_key()`, never input dictionary order. Format broad roles as
`[role_1, role_2]`. Construct receipts only from signals appended to the text.

- [ ] **Step 7: Add safety and partial-section tests**

Prove:

- identity-only and preference-only profiles omit the other section;
- passing a raw dictionary instead of `CollaborationProfile` raises
  `TypeError` before rendering;
- preferred-name punctuation cannot escape section syntax because schema
  validation rejects brackets and control characters;
- every active signal produces exactly one receipt;
- no receipt exists without a rendered instruction;
- repeated renders are byte-for-byte and object-for-object deterministic;
- a current request can still override a style preference because the rendered
  block contains no instruction claiming precedence over the current turn.

- [ ] **Step 8: Verify Task 3 GREEN**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_memory_policy.py tests/test_memory_schemas.py \
  tests/test_memory_context.py -v
```

Expected: all pure memory tests pass offline.

---

### Task 4: Reproducible offline M1 smoke runner

**Files:**

- Create: `smoke_test_memory_policy.py`
- Create: `tests/test_smoke_test_memory_policy.py`

**Interfaces:**

- Produces `run_smoke() -> int`.
- Uses the pseudonymous name `Avery`, roles `student` and `researcher`, and two
  collaboration preferences.
- Prints only `trusted-memory-m1 pass signals=4` on success.
- Performs no network, Firestore, Gemini, ADK, or environment-variable access.

- [ ] **Step 1: Write the smoke-runner RED test**

```python
def test_memory_policy_smoke_runner_is_offline_and_content_safe(
    capsys,
) -> None:
    from smoke_test_memory_policy import run_smoke

    assert run_smoke() == 0
    assert capsys.readouterr().out == "trusted-memory-m1 pass signals=4\n"
```

- [ ] **Step 2: Verify smoke RED**

Run the named test. Expected: import fails because the runner does not exist.

- [ ] **Step 3: Implement the minimal runner**

Construct four fixed `ActiveMemorySignal` objects, validate one
`CollaborationProfile`, render it, assert four receipts and both section
markers, print the content-free success line, and return zero. Use
`if __name__ == "__main__": raise SystemExit(run_smoke())`.

- [ ] **Step 4: Verify smoke GREEN**

Run:

```bash
venv/bin/python -m pytest tests/test_smoke_test_memory_policy.py -v
venv/bin/python smoke_test_memory_policy.py
```

Expected pytest result: PASS. Expected runner output:

```text
trusted-memory-m1 pass signals=4
```

---

### Task 5: Focused verification, cross-cutting regression, and manual gate

**Files:**

- No new files unless an earlier valid RED test requires a correction within
  the approved M1 boundary.

**Interfaces:**

- Verifies the pure M1 contract without enabling it in runtime routes.
- Preserves the user-controlled checkpoint gate.

- [ ] **Step 1: Run focused M1 verification**

```bash
venv/bin/python -m pytest \
  tests/test_memory_policy.py \
  tests/test_memory_schemas.py \
  tests/test_memory_context.py \
  tests/test_smoke_test_memory_policy.py \
  -v
```

- [ ] **Step 2: Run directly affected schema regressions**

```bash
venv/bin/python -m pytest tests/test_schemas.py tests/test_main.py -q
```

`schemas.py` is a shared public-contract module consumed by chat and synthesis,
so focused M1 tests alone cannot credibly prove no schema regression.

- [ ] **Step 3: Run broader verification required by the shared schema**

```bash
venv/bin/python -m pip check
venv/bin/python -m pytest
venv/bin/python -m compileall -q \
  schemas.py memory_policy.py memory_context.py \
  smoke_test_memory_policy.py tests/test_memory_policy.py \
  tests/test_memory_schemas.py tests/test_memory_context.py \
  tests/test_smoke_test_memory_policy.py
git diff --check
git status --short --branch
```

The full suite is justified because adding imports and Pydantic types to
`schemas.py` affects every route, synthesis parser, and shared fixture that
imports that module.

- [ ] **Step 4: Stop at implemented, pending manual verification**

Provide the user these exact checks. Do not commit.

Offline M1 behavior:

```bash
venv/bin/python smoke_test_memory_policy.py
```

Expected: `trusted-memory-m1 pass signals=4` and exit code zero.

Existing health regression with the application running:

```bash
curl --fail-with-body --silent --show-error http://127.0.0.1:8000/
```

Expected: `{"status":"online"}`.

Existing chat regression, kept on one line so the JSON remains valid:

```bash
curl --fail-with-body --silent --show-error --max-time 100 --request POST --header 'Content-Type: application/json' --data '{"project_id":"agent-col","session_id":"phase-3b-memory-m1-regression","user_id":"wifiknight","message":"Explain in one paragraph why user-approved memory is safer than inferred profiling."}' http://127.0.0.1:8000/api/chat
```

Expected: HTTP 200 with the existing `response`, `actions`, `artifacts`, and
`citations` fields. M1 intentionally returns no memory proposal or adaptation
fields because route integration belongs to M6.

Firestore regression target:

- The chat request may append its ordinary user/model messages.
- M1 must create no `memory_proposals`, `memory_events`, `identity_context`, or
  `active_preferences` data because persistence is not wired yet.

## Pass acceptance criteria

- The exact eight preference categories reject every cross-category value.
- Preferred names are NFC-normalized, whitespace-collapsed, 1 through 80
  characters, alphabetic with only spaces, apostrophes, typographic
  apostrophes, periods, and hyphens.
- Preferred-name proposal validation rejects names absent from the current
  message and partial-word matches.
- Broad roles accept one through three unique allowlisted values and use fixed
  order.
- All M1 memory models forbid extra fields and category-value mismatch.
- Profile maps enforce category family, key/category equality, and 2/8 bounds.
- Event confirmation metadata obeys the selected channel contract.
- Empty profiles render nothing; active profiles render deterministic bounded
  sections and one matching receipt per signal.
- Pending proposals, raw profile dictionaries, legacy fields, and chat text
  cannot enter `MemoryContextRenderer`.
- Existing chat and synthesis schemas remain unchanged.
- Pytest performs no network, Gemini, ADK invocation, or Firestore access.
- Focused tests, required full regression suite, compilation, dependency
  integrity, and whitespace checks pass.
- Manual smoke and existing-route regressions pass.
- No commit or push occurs before the user accepts the implementation pass and
  explicitly authorizes the checkpoint.

## Explicit M1 exclusions

- No `MemoryEngine` methods or Firestore paths.
- No proposal TTL enforcement or unresolved-proposal collection query.
- No transactions, batches, lifecycle mutation, inspection route, or deletion.
- No `ChatRequest` decision field or `ChatResponse` memory fields.
- No `AgentActionReceipt` memory action names.
- No supervisor proposal tool or ADK instruction changes.
- No live adaptation, synthesis personalization migration, authentication,
  frontend, Cloud Run, Search, URL Context, or R2 requirement coverage.

## Spec coverage and intentional deferrals

- Versioned preference and identity allowlists, exact instructions, name
  grounding, role ordering, and active-signal ordering are covered by Task 1.
- Proposal, active signal, profile, event, decision, and receipt shape plus
  cross-field validation are covered by Task 2.
- Typed-only context injection boundaries and deterministic adaptation receipts
  are covered by Task 3.
- Reproducible offline demonstration is covered by Task 4.
- The active projection's two identity fields, eight preferences, and ten total
  signals are enforceable in M1 because one `CollaborationProfile` owns that
  complete projection.
- The maximum of ten unresolved proposals is not enforceable by one
  `MemoryProposal` instance. M2 enforces the proposal-slot write boundary and
  M5 enforces the bounded inspection response; neither is falsely claimed as
  M1 coverage.
- Proposal expiry behavior, lifecycle persistence, transactions, idempotency,
  deletion, HTTP integration, supervisor tooling, and live cross-session
  adaptation remain assigned to M2 through M8 exactly as the design contract
  specifies.

## Next approval boundary

After M1 is implemented, automatically verified, manually accepted, and
checkpointed, the next separately planned pass is **M2 — Pending proposal
persistence**. M2 will add one bounded Firestore proposal slot per category,
24-hour application-enforced expiry, idempotent creation, safe errors, and no
active-profile mutation.
