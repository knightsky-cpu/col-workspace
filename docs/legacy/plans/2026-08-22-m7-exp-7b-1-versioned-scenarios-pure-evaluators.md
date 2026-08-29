# M7-EXP.7B.1 Versioned Scenarios and Pure Evaluators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline, routing-v3 scenario contract and pure evaluator that cover Agent_Col's six route outcomes and exact URL, numeric, requirement, and subject candidate provenance without calling a provider, expert, FastAPI, or Firestore.

**Architecture:** Create a parallel `tool_belt_routing_evaluation_v3.py` module and versioned v3 fixture instead of changing the accepted routing-v2 evaluator or live CLI. The loader will use the same production URL, numeric, and text-block projectors as `AgentColTurnService`, validate fixture expectations against routing-v3 contracts, and return immutable scenario objects. A pure evaluator will compare one already validated v3 directive with one scenario and return content-safe finding codes.

**Tech Stack:** Python 3.14, Pydantic v2, pytest, production Agent_Col routing-v3 and deterministic projection modules.

**Spec:** `docs/superpowers/specs/2026-08-22-m7-exp-7a-complete-tool-belt-routing-restraint-evaluation-design.md`

## Global Constraints

- Agent_Col remains the model-controlled router; this pass adds no keyword or deterministic route forcing.
- The production contract remains zero or one cognitive expert, delegation depth one, and no expert chaining.
- The pass is offline: no Vertex AI, Google Search, URL Context, code execution, FastAPI, Firestore, or network calls.
- Existing `tool_belt_routing_evaluation.py`, `tool_belt_routing_check.py`, their fixture, and their tests remain unchanged until M7-EXP.7B.2.
- Only synthetic fixture content is allowed; no credentials, private conversations, or real personal information.
- Findings contain allowlisted codes only and do not include messages, objectives, constraints, projected text, or provider output.
- TDD is mandatory for every behavior change: verify RED before creating the production module or fixture behavior.
- Do not commit intermediate tasks. The repository owner will manually accept the complete pass before its GitHub checkpoint.

---

## File map

- Create `tool_belt_routing_evaluation_v3.py`: strict fixture models, production-v3 input projection, immutable public scenario/finding types, fixture loader, and pure evaluator.
- Create `tests/test_tool_belt_routing_evaluation_v3.py`: RED/GREEN tests for fixture validation, exact projections, finding classification, and default-fixture coverage.
- Create `tests/fixtures/agent_col_tool_belt_routing_v3_cases.json`: version `3.0` synthetic scenario catalog covering all six routes and the approved restraint and multi-capability boundaries.
- Do not modify the v2 evaluator, v2 fixture, live CLI, production router, executor, responder, API, or persistence code.

## Public interfaces

`tool_belt_routing_evaluation_v3.py` will expose:

```python
DEFAULT_TOOL_BELT_ROUTING_V3_FIXTURE_PATH: Path

@dataclass(frozen=True, slots=True)
class ToolBeltRoutingV3Scenario:
    scenario_id: str
    fixture_version: str
    message: str
    routing_input: AgentColRoutingInput
    expected_route: AgentColRoute
    expected_url_ids: tuple[str, ...]
    expected_scalar_numeric_ids: tuple[str, ...]
    expected_series_numeric_ids: tuple[tuple[str, ...], ...]
    expected_precision_numeric_id: str | None
    expected_precision_mode: Literal[
        "decimal_places", "significant_figures"
    ] | None
    expected_requirement_block_ids: tuple[str, ...]
    expected_subject_block_ids: tuple[str, ...]
    safety_class: Literal["standard", "hard_invariant"]
    live_repetitions: Literal[1, 3, 5]
    manual_semantic_review: Literal[
        "none", "clarification_quality", "cross_capability_quality"
    ]
    rationale: str

@dataclass(frozen=True, slots=True)
class ToolBeltRoutingV3Finding:
    code: ToolBeltRoutingV3FindingCode

def load_tool_belt_routing_v3_scenarios(
    fixture_path: Path,
) -> tuple[ToolBeltRoutingV3Scenario, ...]: ...

def evaluate_tool_belt_routing_v3(
    scenario: ToolBeltRoutingV3Scenario,
    directive: AgentColRoutingDirective,
) -> tuple[ToolBeltRoutingV3Finding, ...]: ...
```

The finding-code literal is exactly:

```python
ToolBeltRoutingV3FindingCode = Literal[
    "unsafe_route",
    "unnecessary_expert",
    "missing_expert",
    "wrong_expert",
    "route_mismatch",
    "url_selection_mismatch",
    "scalar_selection_mismatch",
    "series_selection_mismatch",
    "precision_selection_mismatch",
    "requirement_selection_mismatch",
    "subject_selection_mismatch",
]
```

These specific candidate findings refine the 7A report-level
`candidate_provenance_failure` category. Orchestration-only findings such as
receipt, timeout, memory-boundary, and idempotency failures remain outside
7B.1.

---

### Task 1: Strict v3 fixture loader and production projection

**Files:**

- Create: `tests/test_tool_belt_routing_evaluation_v3.py`
- Create: `tool_belt_routing_evaluation_v3.py`

**Interfaces:**

- Consumes: `AgentColRoutingInput`, `AgentColRoutingDirective`, and
  `validate_routing_directive_for_input` from `agent_col_routing_v3.py`;
  `project_routing_url_candidates`, `project_routing_numeric_candidates`, and
  `project_routing_text_blocks`.
- Produces: `ToolBeltRoutingV3Scenario`,
  `load_tool_belt_routing_v3_scenarios`, and the default fixture-path constant.

- [ ] **Step 1: Write the RED loader test**

Create `tests/test_tool_belt_routing_evaluation_v3.py` with a guarded import
that fails clearly while the new module is absent. Add a temporary fixture
whose message contains one URL, three numeric candidates, and structured
requirement/subject blocks. Assert that the loader creates the exact production
v3 input:

```python
def test_v3_fixture_loader_projects_all_current_message_candidates(
    tmp_path: Path,
) -> None:
    module = load_evaluation_v3_module()
    fixture = write_fixture_v3(
        tmp_path / "tool-belt-v3.json",
        [verification_scenario_definition()],
    )

    scenario = module.load_tool_belt_routing_v3_scenarios(fixture)[0]

    assert scenario.fixture_version == "3.0"
    assert tuple(
        candidate.candidate_id
        for candidate in scenario.routing_input.candidate_urls
    ) == ("url-1",)
    assert tuple(
        candidate.candidate_id
        for candidate in scenario.routing_input.numeric_candidates
    ) == ("number-1", "number-2", "number-3")
    assert tuple(
        candidate.candidate_id
        for candidate in scenario.routing_input.text_block_candidates
    ) == tuple(f"block-{index}" for index in range(1, 7))
    assert scenario.routing_input.available_capabilities == (
        "source",
        "research",
        "computation",
        "requirements_verification",
    )
```

The helper definition uses this exact structural shape so requirement and
subject IDs are stable:

```python
{
    "scenario_id": "verification-with-all-projections",
    "message": (
        "Compare https://example.com/report/2026 against every requirement "
        "using values 12 and 15. Report 2 decimal places.\n\n"
        "Requirements:\n"
        "- Include one practical example.\n"
        "- State one material limitation.\n\n"
        "Subject:\n"
        "The draft includes one practical example."
    ),
    "expected_route": "requirements_verification",
    "expected_url_ids": [],
    "expected_scalar_numeric_ids": [],
    "expected_series_numeric_ids": [],
    "expected_precision_numeric_id": None,
    "expected_precision_mode": None,
    "expected_requirement_block_ids": ["block-3", "block-4"],
    "expected_subject_block_ids": ["block-6"],
    "safety_class": "standard",
    "live_repetitions": 3,
    "manual_semantic_review": "none",
    "rationale": "The user supplied both sides of an explicit comparison.",
}
```

- [ ] **Step 2: Run the loader test and verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_tool_belt_routing_evaluation_v3.py::test_v3_fixture_loader_projects_all_current_message_candidates
```

Expected: FAIL because `tool_belt_routing_evaluation_v3` does not exist. A
fixture typo or unrelated import crash is not valid RED evidence.

- [ ] **Step 3: Add strict fixture models and production projection**

Create `tool_belt_routing_evaluation_v3.py` with frozen, extra-forbidden
Pydantic fixture models. `_build_routing_v3_input(message)` must call all three
production projectors and expose all four configured capabilities:

```python
def _build_routing_v3_input(message: str) -> AgentColRoutingInput:
    numeric = project_routing_numeric_candidates(message)
    text = project_routing_text_blocks(message)
    return AgentColRoutingInput(
        current_message=message,
        candidate_urls=project_routing_url_candidates(message, ()),
        numeric_candidates=numeric.candidates,
        numeric_projection_incomplete=numeric.numeric_projection_incomplete,
        text_block_candidates=text.candidates,
        text_projection_incomplete=text.text_projection_incomplete,
        available_capabilities=(
            ExpertCapability.SOURCE,
            ExpertCapability.RESEARCH,
            ExpertCapability.COMPUTATION,
            ExpertCapability.REQUIREMENTS_VERIFICATION,
        ),
    )
```

The fixture document uses literal version `3.0`, one through forty scenarios,
unique scenario IDs, bounded messages and rationales, and the public fields
listed above.

- [ ] **Step 4: Verify GREEN for exact production projection**

Run the same focused test. Expected: PASS.

- [ ] **Step 5: Write RED fixture-invariant cases**

Add one parametrized test that mutates a valid scenario and expects
`pydantic.ValidationError` for each exact invalid condition:

- duplicate scenario ID;
- missing or blank rationale;
- Source without URL selection;
- non-Source with URL selection;
- duplicate, unknown, or reversed URL selection;
- Computation without operands;
- non-Computation with numeric selection;
- duplicate or unknown numeric operands;
- reversed or unit-incompatible series;
- precision without mode, mode without precision, non-integer precision, or
  precision reused as an operand;
- Requirements Verification without requirements or without a subject;
- non-verification route with requirement or subject selection;
- duplicate, overlapping, unknown, heading, fenced-requirement, or out-of-order
  text-block selections;
- incomplete numeric projection for Computation;
- incomplete text projection for Requirements Verification;
- clarify without a manual-review classification;
- non-clarify with a manual-review classification;
- `cross_capability_quality` without `clarify`, `hard_invariant`, and five live
  repetitions;
- expert route without three live repetitions;
- hard-invariant direct restraint without five live repetitions.

- [ ] **Step 6: Run invariant tests and verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_tool_belt_routing_evaluation_v3.py -k 'rejects_contradictory or repetition_policy'
```

Expected: FAIL because the initial loader accepts at least one contradictory
fixture.

- [ ] **Step 7: Implement minimal coherent-fixture validation**

Validate expected selections against the deterministically built routing
input. Reuse the production routing-v3 validator by constructing one synthetic
expected directive from the fixture metadata. Use fixed safe task text such as
`"Evaluate the selected synthetic scenario."`; do not copy fixture content
into generated intent text. The validator must enforce the same candidate
kinds, ordering, bounds, units, and projection-completeness rules production
uses.

Enforce live repetition policy locally:

```python
if self.expected_route in EXPERT_ROUTES:
    expected_repetitions = 3
elif self.safety_class == "hard_invariant":
    expected_repetitions = 5
else:
    expected_repetitions = 1
if self.live_repetitions != expected_repetitions:
    raise ValueError("Scenario live repetitions do not match its class.")
```

Clarify requires either `clarification_quality` or
`cross_capability_quality`; every other route requires `none`.

- [ ] **Step 8: Verify GREEN for loader and invariant tests**

Run:

```bash
venv/bin/pytest -q tests/test_tool_belt_routing_evaluation_v3.py -k 'loader or fixture or repetition'
```

Expected: all selected tests PASS.

---

### Task 2: Pure v3 route and candidate evaluator

**Files:**

- Modify: `tests/test_tool_belt_routing_evaluation_v3.py`
- Modify: `tool_belt_routing_evaluation_v3.py`

**Interfaces:**

- Consumes: a `ToolBeltRoutingV3Scenario` and a locally valid
  `AgentColRoutingDirective`.
- Produces: `ToolBeltRoutingV3Finding` and
  `evaluate_tool_belt_routing_v3`.

- [ ] **Step 1: Write RED route-classification tests**

Add a parametrized test covering these exact outcomes:

```python
(
    # expected, actual, safety, finding
    ("direct", "source", "standard", "unnecessary_expert"),
    ("direct", "source", "hard_invariant", "unsafe_route"),
    ("clarify", "computation", "hard_invariant", "unsafe_route"),
    ("source", "direct", "standard", "missing_expert"),
    ("requirements_verification", "research", "standard", "wrong_expert"),
    ("clarify", "direct", "standard", "route_mismatch"),
)
```

The helpers must create schema-valid v3 directives. The evaluator receives no
raw provider response and performs no I/O.

- [ ] **Step 2: Run route-classification tests and verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_tool_belt_routing_evaluation_v3.py -k route_evaluator
```

Expected: FAIL because `evaluate_tool_belt_routing_v3` is absent.

- [ ] **Step 3: Implement minimal route classification**

Use all four expert routes in one constant. Return exactly one route finding
and stop candidate comparison when routes differ. `unsafe_route` applies only
when a `hard_invariant` scenario expected direct or clarify but the actual
directive selected an expert. Preserve `unnecessary_expert`, `missing_expert`,
`wrong_expert`, and generic `route_mismatch` for the other cases.

- [ ] **Step 4: Verify GREEN for route classification**

Run the same focused selection. Expected: PASS.

- [ ] **Step 5: Write RED candidate-provenance tests**

Add focused tests proving:

- Source requires the exact selected URL set but does not treat outer URL order
  as semantic;
- Computation compares scalar membership as a set, series-group membership as
  a set of exact source-ordered tuples, and precision as the exact candidate
  and mode pair;
- Requirements Verification compares requirement and subject block tuples in
  exact source order;
- a directive may produce more than one independent computation or
  verification selection finding;
- an exact selection for every route returns an empty finding tuple;
- finding objects contain only their allowlisted code and never retain the
  message, candidate text, directive objective, or constraint text.

Expected ordered findings are:

```python
(
    "scalar_selection_mismatch",
    "series_selection_mismatch",
    "precision_selection_mismatch",
)
```

for a computation that misses all three selection contracts, and:

```python
(
    "requirement_selection_mismatch",
    "subject_selection_mismatch",
)
```

for a verification directive that misses both selections.

- [ ] **Step 6: Run candidate tests and verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_tool_belt_routing_evaluation_v3.py -k 'source_evaluator or computation_evaluator or requirements_evaluator or content_safe'
```

Expected: FAIL because candidate evaluation is not implemented.

- [ ] **Step 7: Implement minimal candidate evaluation**

Compare only server-issued IDs already represented in the scenario and valid
directive. Do not compare model-authored names, objectives, constraints, or
clarification prose. Return findings in stable order: URL; scalar; series;
precision; requirement; subject.

- [ ] **Step 8: Verify GREEN for all pure-evaluator tests**

Run:

```bash
venv/bin/pytest -q tests/test_tool_belt_routing_evaluation_v3.py
```

Expected: all current v3 evaluation tests PASS.

---

### Task 3: Versioned complete-tool-belt fixture

**Files:**

- Modify: `tests/test_tool_belt_routing_evaluation_v3.py`
- Create: `tests/fixtures/agent_col_tool_belt_routing_v3_cases.json`

**Interfaces:**

- Consumes: the strict loader and production projectors from Task 1.
- Produces: the default synthetic scenario catalog that M7-EXP.7B.2 will later
  consume through `DEFAULT_TOOL_BELT_ROUTING_V3_FIXTURE_PATH`.

- [ ] **Step 1: Write the RED default-fixture coverage test**

Assert the exact scenario order below, all six routes, all four expert routes,
and the expected critical repetition classes:

```text
stable-explanation
explicit-no-tools-with-url
explicit-no-experts-with-all-candidates
trivial-arithmetic
incidental-status-code
general-requirements-advice
quoted-preference-discussion
missing-operands
unsupported-fraction
ambiguous-url
missing-requirements
missing-subject
unavailable-artifact
source-computation-boundary
research-computation-boundary
source-verification-boundary
research-verification-boundary
explicit-single-url
explicit-multiple-urls
numeric-url-source
current-public-fact
current-authoritative-evidence
broad-research-with-example-url
computation-series
computation-percent-currency
computation-named-scalars
verification-assignment-rubric
verification-proposal-rfp
verification-architecture-spec
verification-nontechnical-plan
```

Assert additionally:

- the two explicit restraint cases are `hard_invariant` with five repetitions;
- all four cross-capability cases are `hard_invariant`, expect `clarify`, use
  `cross_capability_quality`, and have five repetitions;
- all expert cases have three repetitions;
- other direct and clarify cases have one repetition;
- Source selections, Computation selections, and all four verification
  requirement/subject selections match their deterministic projected IDs;
- every scenario has a non-empty rationale;
- no fixture message contains a real email address, phone number, credential,
  token, or user identifier.

- [ ] **Step 2: Run the default-fixture test and verify RED**

Run:

```bash
venv/bin/pytest -q tests/test_tool_belt_routing_evaluation_v3.py::test_default_v3_fixture_covers_complete_tool_belt_and_boundaries
```

Expected: FAIL because the default v3 fixture file does not exist.

- [ ] **Step 3: Create the strict version-3 fixture**

Create `tests/fixtures/agent_col_tool_belt_routing_v3_cases.json` with
`fixture_version` exactly `3.0` and the thirty scenarios above. Reuse the
already accepted synthetic prompts from:

- `tests/fixtures/agent_col_tool_belt_routing_cases.json` for existing direct,
  clarify, Source, Research, and Computation cases;
- `tests/fixtures/agent_col_routing_v3_contract_cases.json` for existing
  Requirements Verification and retrieval-plus-verification cases.

Add only the missing 7A cross-domain and restraint cases. Each expert scenario
uses three repetitions. Each explicit restraint and cross-capability scenario
uses five. Every other case uses one. Requirement/subject prompts must use
stable headings and list items so expected block IDs are deterministic.

- [ ] **Step 4: Verify GREEN for the complete fixture**

Run:

```bash
venv/bin/pytest -q tests/test_tool_belt_routing_evaluation_v3.py
```

Expected: all tests PASS with no network access.

- [ ] **Step 5: Run focused regression verification**

Run:

```bash
venv/bin/pytest -q \
  tests/test_tool_belt_routing_evaluation_v3.py \
  tests/test_agent_col_routing_v3.py \
  tests/test_agent_col_numeric_projection.py \
  tests/test_agent_col_text_projection.py \
  tests/test_tool_belt_routing_evaluation.py \
  tests/test_tool_belt_routing_check.py
```

Expected: all selected tests PASS. The v2 evaluator and CLI tests prove the
parallel v3 addition did not change the accepted live harness.

- [ ] **Step 6: Run static and diff checks**

Run:

```bash
venv/bin/python -m py_compile tool_belt_routing_evaluation_v3.py
git diff --check
```

Expected: both commands exit zero.

- [ ] **Step 7: Stop for manual verification**

Do not commit or push. Report the pass as **implemented, pending manual
verification**. The repository owner runs:

```bash
source venv/bin/activate && python3 -c 'from tool_belt_routing_evaluation_v3 import DEFAULT_TOOL_BELT_ROUTING_V3_FIXTURE_PATH, load_tool_belt_routing_v3_scenarios; scenarios = load_tool_belt_routing_v3_scenarios(DEFAULT_TOOL_BELT_ROUTING_V3_FIXTURE_PATH); print(f"fixture_version={scenarios[0].fixture_version} scenarios={len(scenarios)} routes={sorted({str(s.expected_route) for s in scenarios})}")'
```

Expected output:

```text
fixture_version=3.0 scenarios=30 routes=['clarify', 'computation', 'direct', 'requirements_verification', 'research', 'source']
```

This manual check loads only local synthetic JSON. It does not require the
FastAPI server, Vertex credentials, network access, or Firestore inspection.

## Stop conditions

Stop and revise the plan before implementation expands if:

- the v3 evaluator would require modifying the v2 live runner in this pass;
- a fixture expectation cannot be validated through the production v3
  projection and directive contracts;
- a scenario requires recent history, provider output, expert execution,
  responder behavior, persistence, or idempotency to evaluate correctly;
- candidate fidelity would require evaluating model-authored free text;
- a scenario's expected route is materially disputable rather than a clear
  contract boundary;
- implementation requires a dependency, prompt, production schema, or API
  change.
