# Phase 3B Synthesis Schema v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver provider-safe structured generation, a bounded and
semantically validated `SynthesisBlueprint` v2 contract, and a deterministic
quality-evaluation harness before synthesis becomes an ADK tool.

**Architecture:** Keep `SynthesisBlueprint` as the canonical local model.
Adapt its JSON schema for Gemini, run deterministic domain validation after
local Pydantic parsing, and pass server-owned schema metadata from the
application service into schema-agnostic persistence. Add quality evaluation
as a separate offline-tested boundary with an explicitly invoked live runner.

**Tech Stack:** Python 3.14, Pydantic 2.13, Google GenAI SDK 2.18, FastAPI,
asyncio, Firestore AsyncClient, pytest, pytest-asyncio.

**Spec:**
`docs/superpowers/specs/2026-08-20-phase-3b-synthesis-schema-v2-design.md`

## Global Constraints

- Execute each pass inline; do not delegate to subagents.
- Use strict RED-GREEN-REFACTOR and record the observed RED reason.
- `project_id` remains machine identity; `project_name` remains display text.
- Do not register an ADK synthesis tool in Task 4B.
- Do not migrate or delete existing schema `1.0` Firestore documents.
- No network or Gemini calls may run inside pytest.
- Error logs must exclude identifiers, profile values, source text, and
  blueprint content.
- Stop after each pass at implemented, pending manual verification.
- Do not checkpoint a pass until the user reports manual success.

---

## Pass 4B.1: Provider-Safe Gemini Schema

### Task 1: Prove the provider schema adapter contract

**Files:**

- Create: `synthesis_schema.py`
- Create: `tests/test_synthesis_schema.py`

**Interfaces:**

- Consumes: `SynthesisBlueprint.model_json_schema()`.
- Produces:
  `adapt_schema_for_gemini(schema: dict[str, object]) -> dict[str, object]`.
- Produces: `build_gemini_response_schema() -> dict[str, object]`.

- [ ] **Step 1: Write the first failing recursive-removal test**

```python
def test_provider_schema_removes_local_only_string_constraints() -> None:
    from synthesis_schema import build_gemini_response_schema

    schema = build_gemini_response_schema()
    serialized = json.dumps(schema, sort_keys=True)

    assert '"minLength"' not in serialized
    assert '"maxLength"' not in serialized
    assert '"pattern"' not in serialized
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m pytest tests/test_synthesis_schema.py \
  -k local_only_string_constraints -v
```

Expected: FAIL with `ModuleNotFoundError: No module named
'synthesis_schema'`.

- [ ] **Step 3: Implement the minimal pure adapter**

Implement a recursive deep-copy transformation with:

```python
LOCAL_ONLY_SCHEMA_KEYWORDS = frozenset(
    {"minLength", "maxLength", "pattern"}
)


def build_gemini_response_schema() -> dict[str, object]:
    return adapt_schema_for_gemini(
        SynthesisBlueprint.model_json_schema()
    )
```

The helper must create new dictionaries and lists and must not mutate the
Pydantic schema object. It removes constraint keywords from schema nodes, but
must preserve a model property or definition whose name happens to be
`pattern`, `minLength`, or `maxLength`.

- [ ] **Step 4: Verify GREEN**

Run the exact test from Step 2. Expected: PASS.

- [ ] **Step 5: Add preservation tests**

Add tests proving that the adapted schema preserves:

- top-level `additionalProperties=False`;
- required blueprint fields;
- `$defs` and `$ref` entries;
- severity and complexity enums;
- clarifying-option `minItems=2` and `maxItems=3`;
- titles and named property keys;
- independence from mutation of a previously returned schema.

- [ ] **Step 6: Run adapter tests**

```bash
python3 -m pytest tests/test_synthesis_schema.py -v
```

Expected: all adapter tests PASS.

### Task 2: Route structured generation through the adapter

**Files:**

- Modify: `synthesis.py`
- Modify: `tests/test_synthesis.py`

**Interfaces:**

- Consumes: `build_gemini_response_schema()`.
- Preserves: `generate_blueprint(...) -> SynthesisBlueprint` and all existing
  error mappings.

- [ ] **Step 1: Change the existing provider-schema assertion first**

The generation test must assert:

```python
assert config.response_json_schema == build_gemini_response_schema()
assert config.response_json_schema != (
    SynthesisBlueprint.model_json_schema()
)
```

- [ ] **Step 2: Verify RED**

```bash
python3 -m pytest \
  tests/test_synthesis.py::test_generate_blueprint_uses_structured_untrusted_context \
  -v
```

Expected: FAIL because production still sends the raw canonical schema.

- [ ] **Step 3: Make the minimal generation change**

Import the adapter and replace only the `response_json_schema` value. Do not
change model, prompt, temperature, timeout, token limit, parsing, or error
handling.

- [ ] **Step 4: Verify GREEN and focused regressions**

```bash
python3 -m pytest \
  tests/test_synthesis_schema.py \
  tests/test_synthesis.py \
  tests/test_smoke_test_synthesis.py \
  -v
```

- [ ] **Step 5: Static verification**

```bash
python3 -m py_compile synthesis.py synthesis_schema.py \
  tests/test_synthesis.py tests/test_synthesis_schema.py
git diff --check
```

- [ ] **Step 6: Stop for manual verification**

Manual targets are one live `smoke_test_synthesis.py` run and one direct
`/api/synthesize` curl. The response must remain schema `1.0` in Firestore
during this pass. Do not begin 4B.2 or commit until the user accepts 4B.1.

---

## Pass 4B.2: Canonical Blueprint v2 and Domain Validation

### Task 1: Define the v2 structural contract

**Files:**

- Modify: `schemas.py`
- Modify: `tests/test_schemas.py`
- Modify fixtures in: `tests/test_main.py`, `tests/test_synthesis.py`,
  `tests/test_synthesis_service.py`

**Interfaces:**

- Produces: `SYNTHESIS_BLUEPRINT_SCHEMA_VERSION = "2.0"`.
- Produces: a `SynthesisBlueprint` with `architectural_decisions` and no
  `architectural_decisions_and_feedback` field.

- [ ] **Step 1: Write the v2 naming RED test**

```python
def test_blueprint_v2_uses_architectural_decisions(
    valid_blueprint_payload: dict[str, object],
) -> None:
    payload = copy.deepcopy(valid_blueprint_payload)
    decisions = payload.pop("architectural_decisions_and_feedback")
    payload["architectural_decisions"] = decisions

    blueprint = SynthesisBlueprint.model_validate(payload)

    assert blueprint.architectural_decisions
```

Expected RED: the new field is forbidden and the old field is required.

- [ ] **Step 2: Implement only the rename and update shared fixtures**

Change the canonical field and all test payloads. Add a separate test proving
the old field is rejected rather than silently accepted.

- [ ] **Step 3: Add table-driven string and collection bound RED tests**

Cover every exact limit from the design spec. Each test must verify both the
maximum accepted boundary and the first rejected value. Include a
`project_name` containing spaces and capitalization to preserve the identity
decision.

- [ ] **Step 4: Add bounded aliases and field descriptions**

Create purpose-specific annotated types for project names, labels,
explanatory text, and verification steps. Apply explicit `Field` descriptions
and the collection maxima from the spec. Do not add a slug pattern to
`project_name`. Assert that the adapted Gemini schema retains those
descriptions while local string-length keywords remain absent.

- [ ] **Step 5: Verify schema GREEN**

```bash
python3 -m pytest tests/test_schemas.py -v
```

### Task 2: Add deterministic semantic validation

**Files:**

- Create: `blueprint_validation.py`
- Create: `tests/test_blueprint_validation.py`
- Modify: `synthesis.py`
- Modify: `tests/test_synthesis.py`

**Interfaces:**

- Produces:
  `validate_blueprint(blueprint: SynthesisBlueprint,
  profile_context: dict[str, object]) -> None`.
- Produces: `BlueprintValidationError(ValueError)` with content-free messages.

- [ ] **Step 1: Write one RED test per deterministic invariant**

Use parametrized tests for normalized duplicates and separate tests for scope
overlap, personalization, and serialized size. The first test is:

```python
def test_validator_rejects_scope_overlap(
    blueprint: SynthesisBlueprint,
) -> None:
    from blueprint_validation import (
        BlueprintValidationError,
        validate_blueprint,
    )

    blueprint.synthesized_conceptual_model.out_of_scope = [" planning "]

    with pytest.raises(BlueprintValidationError):
        validate_blueprint(blueprint, {})
```

Expected RED: `blueprint_validation` does not exist.

- [ ] **Step 2: Implement normalization and uniqueness helpers**

Use `value.strip().casefold()` and return no content in exception messages.
Implement only the invariants listed in the design spec.

- [ ] **Step 3: Add the 131,072-byte boundary test and implementation**

Serialize with compact separators, UTF-8 encoding, and `ensure_ascii=False`.
Test exactly 131,072-or-less as accepted and greater than 131,072 as rejected
using a structurally valid large roadmap.

- [ ] **Step 4: Replace generation's personalization-only validator**

After `model_validate_json`, call `validate_blueprint`. Preserve translation
to `SynthesisEngineError`, safe logging, and no Firestore write after failure.

- [ ] **Step 5: Verify domain GREEN**

```bash
python3 -m pytest \
  tests/test_blueprint_validation.py \
  tests/test_synthesis.py \
  -v
```

### Task 3: Persist server-owned schema version 2.0

**Files:**

- Modify: `database.py`
- Modify: `synthesis_service.py`
- Modify: `schemas.py`
- Modify: `tests/test_database.py`
- Modify: `tests/test_synthesis_service.py`
- Modify: `tests/test_schemas.py`

**Interfaces:**

- Changes `MemoryEngine.save_blueprint` to accept `schema_version: str`
  immediately before `blueprint`.
- `SynthesisApplicationService` supplies
  `SYNTHESIS_BLUEPRINT_SCHEMA_VERSION`.
- `ArtifactReference.schema_version` accepts only `"2.0"` for newly returned
  artifacts.

- [ ] **Step 1: Change the atomic persistence expectation to `2.0`**

Pass `"2.0"` into `save_blueprint` and expect the stored metadata to equal
that supplied value. Verify RED because the current method hard-codes `1.0`.

- [ ] **Step 2: Add invalid-version pre-access tests**

Blank and non-string schema versions must raise `ValueError` before any
Firestore call.

- [ ] **Step 3: Implement the signature and service call**

Validate `schema_version` with the existing string validator. Keep the atomic
batch shape, paths, timestamps, and safe `GoogleAPIError` translation.

- [ ] **Step 4: Verify persistence GREEN**

```bash
python3 -m pytest \
  tests/test_database.py \
  tests/test_synthesis_service.py \
  tests/test_schemas.py \
  -v
```

### Task 4: Integrate and document v2

**Files:**

- Modify: `tests/test_main.py`
- Modify: `tests/test_smoke_test_synthesis.py` only if fixture shape requires
  it.
- Modify: `docs/superpowers/specs/2026-08-19-phase-3-synthesis-engine-design.md`
- Modify: `docs/superpowers/specs/2026-08-19-hybrid-adk-supervisor-contract-design.md`
- Modify: `docs/architecture.md`

- [ ] **Step 1: Run focused integration tests**

```bash
python3 -m pytest \
  tests/test_schemas.py \
  tests/test_blueprint_validation.py \
  tests/test_synthesis_schema.py \
  tests/test_synthesis.py \
  tests/test_synthesis_service.py \
  tests/test_database.py \
  tests/test_main.py \
  tests/test_smoke_test_synthesis.py \
  -v
```

- [ ] **Step 2: Run the full suite because the shared contract changed**

```bash
python3 -m pytest
python3 -m pip check
git diff --check
```

- [ ] **Step 3: Update documentation literally**

Replace active `1.0` and old field-name claims with v2 behavior. Preserve
historical plan evidence as historical; do not rewrite old implementation
plans to pretend they originally specified v2.

- [ ] **Step 4: Stop for manual verification**

Run one live synthesis and inspect the new Firestore document for
`schema_version="2.0"` and `blueprint.architectural_decisions`. Confirm the
old field is absent. Do not begin 4B.3 or commit until the user accepts 4B.2.

---

## Pass 4B.3: Scenario-Based Quality Evaluation

### Task 1: Define offline quality scenarios and evaluator

**Files:**

- Create: `synthesis_quality.py`
- Create: `tests/fixtures/synthesis_quality_cases.json`
- Create: `tests/test_synthesis_quality.py`

**Interfaces:**

- Produces immutable `QualityScenario` and `QualityFinding` dataclasses.
- Produces:
  `evaluate_blueprint(scenario: QualityScenario,
  blueprint: SynthesisBlueprint) -> tuple[QualityFinding, ...]`.

- [ ] **Step 1: Write RED tests for concept groups and forbidden claims**

Required concepts are arrays of acceptable case-insensitive phrases. A
concept passes when any phrase appears in the serialized blueprint. Forbidden
claims fail when any phrase appears.

- [ ] **Step 2: Write RED tests for structural expectations**

Cover expected adaptation keys and minimum/maximum decisions, questions,
milestones, and warnings. Do not score prose style with regex.

- [ ] **Step 3: Implement the minimum pure evaluator**

The evaluator must call the canonical semantic validator first and return
stable public finding codes without copying blueprint content into messages.

- [ ] **Step 4: Add and validate eight versioned fixtures**

Fixtures cover the eight scenarios in the design. Tests must reject malformed
fixture definitions before any model call.

- [ ] **Step 5: Verify offline GREEN**

```bash
python3 -m pytest tests/test_synthesis_quality.py -v
```

### Task 2: Add an explicit live quality runner

**Files:**

- Create: `synthesis_quality_check.py`
- Create: `tests/test_synthesis_quality_check.py`

**Interfaces:**

- CLI: `python3 synthesis_quality_check.py [--scenario SCENARIO_ID]`.
- Exit `0` only when all selected scenarios pass; exit `1` for quality
  findings; exit `2` for configuration or provider failure.

- [ ] **Step 1: Write RED CLI tests with injected fake generation**

Prove scenario selection, stable output, three exit classes, and client close
on success and failure. Tests must not use network access.

- [ ] **Step 2: Implement fixture loading and live orchestration**

Use `load_dotenv`, `genai.Client`, existing `generate_blueprint`, and the pure
evaluator. Print scenario IDs and finding codes only; never print source text,
profiles, or full blueprints on failure.

- [ ] **Step 3: Verify focused and full suites**

```bash
python3 -m pytest \
  tests/test_synthesis_quality.py \
  tests/test_synthesis_quality_check.py \
  tests/test_synthesis.py \
  -v
python3 -m pytest
git diff --check
```

- [ ] **Step 4: Stop for explicit live evaluation**

First run one scenario:

```bash
python3 synthesis_quality_check.py --scenario agent-col-architecture
```

Only after that passes should the user elect to run all eight live scenarios.
Do not register the ADK synthesis tool or checkpoint until manual acceptance.

## Final Task 4B Acceptance

Task 4B is accepted only when all three passes have separate manual success
reports and checkpoints. The next design discussion then covers the
server-owned ADK `synthesize_project` tool adapter and canonical artifact-read
endpoint. Neither is implicitly authorized by accepting this plan.
