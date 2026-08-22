# M7-EXP.5D.1 Numeric Projection and Routing Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. This
> repository uses inline, approval-gated passes unless the owner explicitly
> authorizes subagents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and live-verify a parallel Agent_Col routing v2 contract that
can select only deterministic, current-message numeric candidates for the
Computational Expert without changing the production v1 chat router.

**Architecture:** A pure numeric projector converts safe literal spans into
strict server-assigned candidates. A parallel v2 routing model lets the Vertex
router select candidate IDs, group them as scalars or series, and request
precision without emitting operand values. Local cross-validation remains
authoritative. Production continues importing the existing v1 router until the
later atomic cutover pass.

**Tech Stack:** Python 3.14, Pydantic v2, Google Gen AI SDK 2.18.1, Vertex AI
global, Gemini 3.6 Flash, pytest, pytest-asyncio

**Spec:**
`docs/superpowers/specs/2026-08-22-phase-3b-m7-exp-5c-computational-routing-provenance-design.md`

## Global Constraints

- Do not modify `main.py`, `agent_col_turn_service.py`,
  `agent_col_expert_executor.py`, `agent_col_responder_context.py`,
  `schemas.py`, Firestore behavior, idempotency, or FastAPI routes.
- Do not modify the production v1 `agent_col_routing.py` or
  `agent_col_routing_provider.py` contracts in this pass.
- Do not advertise computation through `/api/chat` and do not add
  `run_computation` to public action receipts.
- The v2 provider boundary is compatibility-only until M7-EXP.5D.3 performs
  the atomic production cutover.
- Project numeric candidates from the current user message only.
- Never source operands from profile, memory, history, assistant text, URLs,
  artifacts, model prose, identifiers, or credentials.
- Expose at most 32 numeric candidates; overflow or unsupported numeric-like
  syntax sets `numeric_projection_incomplete=true`.
- Preserve displayed percentage magnitude: `5%` resolves to value `5` and
  unit `%`, not value `0.05`.
- The router may select candidate IDs and descriptive names, but may not emit
  operand values, expressions, executable code, or numeric literals in its
  objective and constraints.
- Preserve tool restraint: trivial arithmetic and explicit no-tool requests
  route direct; material ambiguity routes clarify.
- No implementation-step commits. Checkpoint only after the owner completes
  manual verification and explicitly accepts the whole pass.

---

### Task 1: Public computation task-text validation boundary

**Files:**
- Modify: `computational_expert.py`
- Test: `tests/test_computational_expert.py`

**Interfaces:**
- Produces:
  `validate_computation_task_text(value: str) -> str`
- Preserves: existing `ComputationExpertInput` validation behavior exactly.
- Consumed by: `agent_col_routing_v2.py` in Task 3.

- [ ] **Step 1: Write the failing public-validator test**

Add a focused test proving the routing contract can reuse the exact existing
unsafe-text policy without importing a private helper:

```python
@pytest.mark.parametrize(
    "value",
    (
        "Run ```python print(1) ```",
        "Fetch https://example.com/data.csv",
        "Read /Users/example/private.csv",
        "Use api_key=secret-value",
    ),
)
def test_public_task_text_validator_rejects_existing_unsafe_shapes(
    value: str,
) -> None:
    computation = load_computational_expert()

    with pytest.raises(ValueError):
        computation.validate_computation_task_text(value)


def test_public_task_text_validator_preserves_safe_bounded_text() -> None:
    computation = load_computational_expert()

    assert computation.validate_computation_task_text(
        "Calculate the population standard deviation."
    ) == "Calculate the population standard deviation."
```

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_computational_expert.py -k public_task_text
```

Expected: FAIL because `validate_computation_task_text` is not public.

- [ ] **Step 3: Implement the public validator without changing policy**

Rename `_reject_unsafe_task_text` to
`validate_computation_task_text` and update both existing field validators to
call that function. Do not add or remove patterns in this task.

```python
def validate_computation_task_text(value: str) -> str:
    """Reject task text that crosses the computation trust boundary."""
    if any(pattern.search(value) for pattern in _UNSAFE_TASK_PATTERNS):
        raise ValueError("Computation task text contains excluded data.")
    return value
```

- [ ] **Step 4: Verify GREEN and regression behavior**

Run:

```bash
venv/bin/pytest -q tests/test_computational_expert.py
```

Expected: all Computational Expert contract tests pass with the known upstream
ADK `BaseAgentConfig` deprecation warning only.

---

### Task 2: Deterministic current-message numeric projection

**Files:**
- Create: `agent_col_numeric_projection.py`
- Create: `tests/test_agent_col_numeric_projection.py`

**Interfaces:**
- Produces:
  `RoutingNumericNotation`
- Produces:
  `RoutingNumericCandidate`
- Produces:
  `RoutingNumericProjection`
- Produces:
  `project_routing_numeric_candidates(current_message: str) -> RoutingNumericProjection`
- Produces:
  `contains_numeric_like_text(value: str) -> bool`
- Consumed by: v2 routing input and directive validation in Task 3.

- [ ] **Step 1: Write failing tests for supported literal projection**

Create tests that require exact source spans and normalized values:

```python
def test_projection_preserves_supported_literals_and_exact_spans() -> None:
    from agent_col_numeric_projection import (
        project_routing_numeric_candidates,
    )

    message = "Use -2, 1,234.5, .75, 6e2, 5%, and $9.99."
    projection = project_routing_numeric_candidates(message)

    assert projection.numeric_projection_incomplete is False
    assert tuple(candidate.candidate_id for candidate in projection.candidates) == (
        "number-1",
        "number-2",
        "number-3",
        "number-4",
        "number-5",
        "number-6",
    )
    assert tuple(candidate.raw_text for candidate in projection.candidates) == (
        "-2",
        "1,234.5",
        ".75",
        "6e2",
        "5%",
        "$9.99",
    )
    assert tuple(candidate.value for candidate in projection.candidates) == (
        -2.0,
        1234.5,
        0.75,
        600.0,
        5.0,
        9.99,
    )
    assert tuple(candidate.unit_symbol for candidate in projection.candidates) == (
        None,
        None,
        None,
        None,
        "%",
        "$",
    )
    for candidate in projection.candidates:
        assert message[candidate.start_index:candidate.end_index] == (
            candidate.raw_text
        )
```

Add separate tests proving repeated equal values retain distinct IDs and that
the candidate models reject extra fields, non-finite values, invalid IDs,
invalid spans, and unsupported unit symbols.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_numeric_projection.py
```

Expected: FAIL because `agent_col_numeric_projection` does not exist.

- [ ] **Step 3: Implement strict projection models and the safe scanner**

Define:

```python
MAX_ROUTING_NUMERIC_CANDIDATES = 32


class RoutingNumericNotation(StrEnum):
    PLAIN = "plain"
    PERCENT = "percent"
    CURRENCY = "currency"


class RoutingNumericCandidate(StrictNumericProjectionModel):
    candidate_id: Annotated[
        str,
        StringConstraints(pattern=r"^number-(?:[1-9]|[12][0-9]|3[0-2])$"),
    ]
    raw_text: Annotated[
        str,
        StringConstraints(min_length=1, max_length=64),
    ]
    value: FiniteFloat
    notation: RoutingNumericNotation
    unit_symbol: Literal["%", "$", "€", "£", "¥"] | None = None
    start_index: int = Field(ge=0)
    end_index: int = Field(gt=0)


class RoutingNumericProjection(StrictNumericProjectionModel):
    candidates: tuple[RoutingNumericCandidate, ...] = Field(max_length=32)
    numeric_projection_incomplete: bool = False
```

The scanner must perform these operations in order:

1. Validate the message as non-empty bounded text before scanning.
2. Record and mask public or private URL spans using the existing HTTP(S) URL
   lexical shape so URL digits never become candidates.
3. Detect and mask fractions, ratios, ranges, dates, times, and explicitly
   marked versions such as `v3.14` or `version 3.14`; set the incomplete flag.
4. Match signed/unsigned integers, decimals, validated comma grouping,
   scientific notation, percentages, and supported currency prefixes.
5. Reject currency-plus-percent combinations and non-finite parses, marking
   projection incomplete.
6. Preserve source order and exact spans without deduplicating repeated values.
7. Keep the first 32 safe candidates but set incomplete if any additional
   candidate exists.

Use one shared internal scan for both public functions. `contains_numeric_like_text`
returns true when the scan yields a candidate or sets the incomplete flag.

- [ ] **Step 4: Add failing tests for excluded and incomplete syntax**

Use this exact behavioral matrix:

```python
@pytest.mark.parametrize(
    "message",
    (
        "Use 1/2 and 4.",
        "Use a 3:1 ratio and 4.",
        "Use the range 5-10 and 12.",
        "Use the date 2026-08-22 and 4.",
        "Use 12:30 and 4.",
        "Use version 3.14 and 4.",
        "Use v3.14 and 4.",
    ),
)
def test_ambiguous_numeric_syntax_marks_projection_incomplete(
    message: str,
) -> None:
    projection = project_routing_numeric_candidates(message)

    assert projection.numeric_projection_incomplete is True
    assert tuple(candidate.raw_text for candidate in projection.candidates) == (
        "4",
    )
```

Add tests proving a URL such as
`https://example.com/v2?limit=10` yields no numeric candidates, 33 plain values
expose exactly 32 and set incomplete, and spelled-out numbers yield no
candidates without claiming incomplete projection.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_numeric_projection.py
```

Expected: all projection tests pass without provider access.

---

### Task 3: Parallel Agent_Col routing v2 contracts

**Files:**
- Create: `agent_col_routing_v2.py`
- Create: `tests/test_agent_col_routing_v2.py`
- Read only: `agent_col_routing.py`

**Interfaces:**
- Imports from v1:
  `RoutingTaskText`, `RoutingMessageText`, `RoutingClarificationText`,
  `RoutingConstraintText`, `RoutingUrlCandidate`, and
  `project_routing_url_candidates`.
- Produces:
  `AgentColRoute`, `AgentColRoutingInput`, `ComputationScalarSelection`,
  `ComputationSeriesSelection`, `ComputationPrecisionSelection`,
  `ComputationRoutingIntent`, `SourceRoutingIntent`,
  `ResearchRoutingIntent`, `AgentColRoutingDirective`,
  `RoutingDirectiveInputError`, and
  `validate_routing_directive_for_input`.
- All produced v2 class names intentionally match their future canonical names;
  module versioning prevents production import changes in this pass.

- [ ] **Step 1: Write failing v2 schema tests**

Cover all five route shapes and require version `2.0`:

```python
def test_v2_computation_directive_selects_only_numeric_candidate_ids() -> None:
    from agent_col_routing_v2 import AgentColRoutingDirective

    directive = AgentColRoutingDirective(
        route="computation",
        computation_intent={
            "objective": "Calculate descriptive statistics for the values.",
            "series_inputs": [
                {
                    "name": "values",
                    "numeric_ids": ["number-1", "number-2", "number-3"],
                }
            ],
            "precision": {
                "mode": "decimal_places",
                "digits_numeric_id": "number-4",
            },
        },
    )

    assert directive.schema_version == "2.0"
    assert directive.computation_intent is not None
    assert directive.computation_intent.series_inputs[0].numeric_ids == (
        "number-1",
        "number-2",
        "number-3",
    )
```

Add a parameterized invalid-structure matrix covering raw operand values,
expressions, extra fields, mismatched payloads, empty selections, duplicate
names, duplicate operand IDs, invalid names, more than 20 scalars, more than 8
series, and more than 32 IDs in one series.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_routing_v2.py
```

Expected: FAIL because `agent_col_routing_v2` does not exist.

- [ ] **Step 3: Implement the strict v2 models**

Define the new route and computation selection types exactly as specified:

```python
class AgentColRoute(StrEnum):
    DIRECT = "direct"
    CLARIFY = "clarify"
    SOURCE = "source"
    RESEARCH = "research"
    COMPUTATION = "computation"


class ComputationScalarSelection(StrictRoutingModel):
    name: ComputationInputName
    numeric_id: RoutingNumericId


class ComputationSeriesSelection(StrictRoutingModel):
    name: ComputationInputName
    numeric_ids: tuple[RoutingNumericId, ...] = Field(
        min_length=1,
        max_length=32,
    )


class ComputationPrecisionSelection(StrictRoutingModel):
    mode: Literal["decimal_places", "significant_figures"]
    digits_numeric_id: RoutingNumericId


class ComputationRoutingIntent(StrictRoutingModel):
    objective: RoutingTaskText
    scalar_inputs: tuple[ComputationScalarSelection, ...] = Field(
        default_factory=tuple,
        max_length=20,
    )
    series_inputs: tuple[ComputationSeriesSelection, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    precision: ComputationPrecisionSelection | None = None
    constraints: tuple[RoutingConstraintText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )
```

Its model validator must require at least one input selection, globally unique
names, unique operand IDs across all scalars and series, and no precision ID
reuse as an operand.

`AgentColRoutingInput` must contain URL candidates, numeric candidates,
`numeric_projection_incomplete`, and up to three unique available capabilities.
Its validator must prove sequential numeric IDs, exact message slices, ordered
non-overlapping spans, and an allowed capability set of Source, Research, and
Computation.

`AgentColRoutingDirective` uses `schema_version: Literal["2.0"] = "2.0"` and
enforces the exact five-row route-presence table from the design.

- [ ] **Step 4: Write failing input-specific validation tests**

Create a valid computation routing input using projected current-message
candidates, then mutate one invariant at a time:

```python
def computation_routing_input() -> AgentColRoutingInput:
    message = (
        "Calculate the mean of 12, 15, and 18 with precision set at "
        "2 decimal places."
    )
    projection = project_routing_numeric_candidates(message)
    return AgentColRoutingInput(
        current_message=message,
        numeric_candidates=projection.candidates,
        numeric_projection_incomplete=(
            projection.numeric_projection_incomplete
        ),
        available_capabilities=(
            "source",
            "research",
            "computation",
        ),
    )
```

Require `validate_routing_directive_for_input` to reject before expert access:

- computation absent from available capabilities;
- incomplete projection;
- unknown numeric ID;
- reordered series IDs;
- mixed notation or unit symbols in a series;
- non-integer precision digits;
- zero significant figures;
- numeric literal in objective or constraint;
- unsafe task text;
- a candidate whose raw span does not match `current_message`.

Also prove direct, clarify, Source, and Research directives preserve their v1
cross-validation behavior under the v2 input.

- [ ] **Step 5: Implement local cross-validation**

Resolve candidates from one ID map and enforce all invariants before returning
the directive. Use:

```python
validate_computation_task_text(intent.objective)
for constraint in intent.constraints:
    validate_computation_task_text(constraint)
if contains_numeric_like_text(intent.objective) or any(
    contains_numeric_like_text(value) for value in intent.constraints
):
    raise RoutingDirectiveInputError(incompatible)
```

For precision, require `candidate.value.is_integer()`, convert with `int`, and
instantiate the existing `PrecisionRule`. For each series, compare the source
candidate index order and require exactly one shared `(notation, unit_symbol)`
pair.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_routing_v2.py tests/test_agent_col_numeric_projection.py tests/test_computational_expert.py
```

Expected: all local v2 routing, projection, and computation validation tests
pass without changing production v1 imports.

---

### Task 4: Parallel Vertex structured-routing v2 provider

**Files:**
- Create: `agent_col_routing_provider_v2.py`
- Create: `tests/test_agent_col_routing_provider_v2.py`
- Read only: `agent_col_routing_provider.py`

**Interfaces:**
- Consumes:
  `agent_col_routing_v2.AgentColRoutingInput`
- Produces:
  `AGENT_COL_ROUTING_V2_SYSTEM_INSTRUCTION`
- Produces:
  `build_agent_col_routing_v2_response_schema() -> dict[str, object]`
- Produces:
  `request_agent_col_routing_v2_directive(client, routing_input, *, timeout_seconds=30.0) -> AgentColRoutingDirective`
- Produces safe provider error classes scoped to the v2 compatibility boundary.

- [ ] **Step 1: Write failing provider-schema tests**

Require the provider-safe schema to preserve:

```python
assert schema["$defs"]["AgentColRoute"]["enum"] == [
    "direct",
    "clarify",
    "source",
    "research",
    "computation",
]
assert schema["properties"]["schema_version"]["enum"] == ["2.0"]
assert schema["$defs"]["ComputationRoutingIntent"][
    "additionalProperties"
] is False
assert "computation_intent" in schema["properties"]
```

Assert the provider schema removes local-only `minLength`, `maxLength`,
`pattern`, and `maxItems` keywords while the canonical Pydantic model retains
them locally.

- [ ] **Step 2: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_routing_provider_v2.py
```

Expected: FAIL because the v2 provider module does not exist.

- [ ] **Step 3: Implement the isolated v2 provider adapter**

Follow the existing provider boundary but import only v2 contracts. The system
instruction must state:

- choose only capabilities listed in `available_capabilities`;
- choose computation only for nontrivial bounded calculation;
- select only numeric candidate IDs present in the input;
- never copy or generate raw operand values;
- preserve series candidate order;
- use clarify for incomplete projection, missing historical values, ambiguous
  operation, or consequential unit ambiguity;
- use direct for trivial arithmetic and explicit no-tool requests;
- never execute computation, retrieve sources, call tools, answer the user, or
  reveal hidden reasoning.

Use the same Vertex model, tool-free `generate_content`, temperature zero,
minimal thinking, and application timeout as v1. Start with a bounded
`max_output_tokens=1_024`; the live compatibility gate in Task 5 decides
whether this value is sufficient before any production cutover.

- [ ] **Step 4: Add provider failure and local-mismatch tests**

Prove:

- the exact v2 routing input is wrapped in untrusted-data delimiters;
- no tools are configured;
- a valid computation directive parses and validates;
- raw values or schema version `1.0` become safe output errors;
- provider payloads never appear in raised messages;
- application timeout has its own safe type;
- an unknown candidate ID becomes `RoutingDirectiveInputError` rather than a
  generic provider error;
- non-positive timeout rejects before provider access.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
venv/bin/pytest -q tests/test_agent_col_routing_provider_v2.py tests/test_agent_col_routing_v2.py
```

Expected: all v2 provider and local contract tests pass offline.

---

### Task 5: Reproducible live v2 compatibility and restraint runner

**Files:**
- Create: `tests/fixtures/agent_col_routing_v2_contract_cases.json`
- Create: `smoke_test_agent_col_routing_v2.py`
- Create: `tests/test_smoke_test_agent_col_routing_v2.py`
- Preserve: `smoke_test_agent_col_routing.py` and its v1 fixture

**Interfaces:**
- `python3 smoke_test_agent_col_routing_v2.py --repetitions 1`
- Exit `0`: every provider directive matches the hand-authored route and local
  v2 validation succeeds.
- Exit `1`: provider responds successfully but at least one route mismatches.
- Exit `2`: configuration, provider, timeout, output, or directive-input error.

- [ ] **Step 1: Write the strict v2 fixture**

Use fixture version `2.0` with exactly these five scenarios:

1. `direct-restraint`: stable prose with all three capabilities available;
   expected `direct`.
2. `clarify-unsupported-fraction`: essential `1/2` input with incomplete
   projection; expected `clarify`.
3. `source-regression`: explicit supplied public URL analysis; expected
   `source`.
4. `research-regression`: current stable Python release; expected `research`.
5. `computation-series`: mean and population standard deviation for six
   current-message values; expected `computation`.

For `computation-series`, use:

```json
{
  "current_message": "Calculate the mean and population standard deviation for 12, 15, 18, 21, 24, and 27.",
  "numeric_candidates": [
    {"candidate_id":"number-1","raw_text":"12","value":12,"notation":"plain","unit_symbol":null,"start_index":57,"end_index":59},
    {"candidate_id":"number-2","raw_text":"15","value":15,"notation":"plain","unit_symbol":null,"start_index":61,"end_index":63},
    {"candidate_id":"number-3","raw_text":"18","value":18,"notation":"plain","unit_symbol":null,"start_index":65,"end_index":67},
    {"candidate_id":"number-4","raw_text":"21","value":21,"notation":"plain","unit_symbol":null,"start_index":69,"end_index":71},
    {"candidate_id":"number-5","raw_text":"24","value":24,"notation":"plain","unit_symbol":null,"start_index":73,"end_index":75},
    {"candidate_id":"number-6","raw_text":"27","value":27,"notation":"plain","unit_symbol":null,"start_index":81,"end_index":83}
  ],
  "numeric_projection_incomplete": false,
  "available_capabilities": ["source", "research", "computation"]
}
```

- [ ] **Step 2: Write failing offline runner tests**

Adapt the existing compatibility-runner pattern with v2 types. Tests must
prove:

- fixture strictness and unique IDs;
- all five expected routes are present;
- one request per scenario and repetition;
- exit `1` for route mismatch;
- exit `2` for safe provider, timeout, output, or input failures;
- unknown scenario and repetition outside one through five are configuration
  errors;
- Vertex ADC client arguments are exact and both async/sync clients close;
- output contains scenario/status metadata only and never input values,
  provider payloads, or directive contents.

- [ ] **Step 3: Verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_smoke_test_agent_col_routing_v2.py
```

Expected: FAIL because the v2 fixture and runner do not exist.

- [ ] **Step 4: Implement the minimal v2 runner**

Reuse the existing runner's exit-code semantics, argument names, ADC loading,
safe output format, and client cleanup. Import only
`request_agent_col_routing_v2_directive` and v2 models. Do not execute any
expert or call the production FastAPI application.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
venv/bin/pytest -q tests/test_smoke_test_agent_col_routing_v2.py
```

Expected: all runner tests pass offline.

---

### Task 6: Focused regression verification and manual gate

**Files:**
- Verify all files created or changed above.
- Verify production v1 files remain byte-for-byte unchanged from checkpoint
  `8a851ae`, except the approved public validator exposure in
  `computational_expert.py`.

**Interfaces:**
- Produces a parallel, live-verified routing v2 contract.
- Does not produce a public computation action or production computation
  route.

- [ ] **Step 1: Run focused local verification**

Run:

```bash
venv/bin/pytest -q \
  tests/test_agent_col_numeric_projection.py \
  tests/test_agent_col_routing_v2.py \
  tests/test_agent_col_routing_provider_v2.py \
  tests/test_smoke_test_agent_col_routing_v2.py \
  tests/test_computational_expert.py \
  tests/test_agent_col_routing.py \
  tests/test_agent_col_routing_provider.py \
  tests/test_smoke_test_agent_col_routing.py
```

The v1 routing tests are included because absence of production contract drift
is an explicit acceptance requirement.

- [ ] **Step 2: Compile and inspect source hygiene**

Run:

```bash
venv/bin/python -m py_compile \
  agent_col_numeric_projection.py \
  agent_col_routing_v2.py \
  agent_col_routing_provider_v2.py \
  smoke_test_agent_col_routing_v2.py \
  computational_expert.py
git diff --check
```

- [ ] **Step 3: Confirm unchanged production boundaries and complete scope**

Run:

```bash
git diff --exit-code 8a851ae -- \
  main.py \
  agent_col_turn_service.py \
  agent_col_expert_executor.py \
  agent_col_responder_context.py \
  agent_col_routing.py \
  agent_col_routing_provider.py \
  schemas.py
git status --short
```

Expected: the first command exits `0` with no output. The second command lists
only these modified or untracked paths:

```text
agent_col_numeric_projection.py
agent_col_routing_provider_v2.py
agent_col_routing_v2.py
computational_expert.py
docs/superpowers/plans/2026-08-22-m7-exp-5d-1-numeric-projection-routing-contracts.md
smoke_test_agent_col_routing_v2.py
tests/fixtures/agent_col_routing_v2_contract_cases.json
tests/test_agent_col_numeric_projection.py
tests/test_agent_col_routing_provider_v2.py
tests/test_agent_col_routing_v2.py
tests/test_computational_expert.py
tests/test_smoke_test_agent_col_routing_v2.py
```

- [ ] **Step 4: Report implemented, pending manual verification**

State explicitly that production `/api/chat` still uses v1 and cannot emit a
`run_computation` receipt in this pass.

- [ ] **Step 5: User runs the one-line live compatibility check**

```bash
source venv/bin/activate && python3 smoke_test_agent_col_routing_v2.py --repetitions 1; printf 'exit=%s\n' "$?"
```

Accept only when all five scenarios report `pass` and the final exit is `0`.
No Firestore check is required because the compatibility runner performs no
persistence.

- [ ] **Step 6: User runs the production-v1 regression check**

With `uvicorn main:app --reload` running, use:

```bash
curl --fail-with-body --silent --show-error --max-time 100 --request POST --header 'Content-Type: application/json' --header 'Idempotency-Key: m7-exp-5d-1-v1-regression-20260822-01' --data '{"project_id":"agent-col","session_id":"m7-exp-5d-1-v1-regression-20260822-01","user_id":"wifiknight","message":"Explain in one paragraph why deterministic provenance matters for numerical inputs."}' http://127.0.0.1:8000/api/chat
```

Expected: HTTP 200, a direct answer, and no expert action. This proves the
parallel v2 work did not cut production chat over early.

## Stop conditions

Stop and propose a correction before expanding scope if:

- exact current-message span reconstruction cannot be made deterministic;
- the numeric grammar misclassifies URLs or decomposes excluded compound
  syntax into operands;
- the provider-safe v2 schema is rejected by Vertex;
- 1,024 output tokens cannot return the six-value computation directive;
- Vertex repeatedly selects computation for trivial/no-tool scenarios or
  declines the explicit computation scenario;
- any production v1 routing test or manual regression fails;
- implementation would require production executor, responder, receipt,
  FastAPI, Firestore, idempotency, dependency, or schema cutover changes.
