# M7-EXP.5C Computational Routing and Numeric Provenance Design

**Status:** Proposed for user review

**Date:** 2026-08-22

**Scope:** Production routing contract design only; no runtime implementation

## 1. Purpose

This contract defines how Agent_Col may select the already verified
Computational Expert from a normal chat turn without allowing a routing model
to invent, silently change, or misattribute numerical operands.

The central rule is:

> Agent_Col owns the routing judgment, but application code owns the numerical
> values that may cross the computation boundary.

The design preserves Agent_Col as the sole conversational orchestrator. The
Computational Expert remains an isolated cognitive capability that executes
bounded Python, returns locally validated execution evidence, and never owns
the user conversation or authoritative application state.

## 2. Current repository state

The production chat path currently has these verified properties:

- `AgentColRoute` supports `direct`, `clarify`, `source`, and `research`.
- `AgentColRoutingDirective` is an internal, non-persisted schema at version
  `1.0`.
- `AgentColRoutingInput` contains the current message, deterministically
  projected public URL candidates, and capabilities derived from configured
  expert services.
- The model selects one route. The application validates that selection
  against the exact routing input before any expert runs.
- `AgentColExpertExecutor` can run zero or one Source or Research expert.
- `AgentColTurnService` preserves one routed expert result for the
  responder-only Agent_Col runtime.
- Completed Source and Research results derive authoritative action and
  citation receipts. Failed results carry no receipts.
- The Computational Expert provider and evidence boundary exists, passes its
  live Vertex smoke test, and is not connected to production routing.

The missing boundary is trustworthy conversion from user-authored numerical
text into `ComputationExpertInput`.

## 3. Goals

The production computation path must:

1. Let Agent_Col decide whether computation materially improves correctness.
2. Preserve tool restraint for direct, trivial, or prose-only requests.
3. Permit only finite numerical values deterministically extracted from the
   current user message.
4. Make the routing model refer to those values by server-assigned IDs.
5. Reject unknown, duplicated, truncated, or incompatible numeric
   selections before code execution.
6. Ask a focused clarification when the requested calculation lacks operands,
   operation, units, or another consequential interpretation.
7. Execute at most one specialist in the current production turn.
8. Return a completed `run_computation` receipt only after locally validated
   successful execution evidence exists.
9. Give responder-only Agent_Col enough validated result context to explain
   the computation without copying unbounded code-execution material into its
   prompt.
10. Preserve FastAPI authority, Firestore boundaries, idempotency, governed
    memory, and existing Source and Research behavior.

## 4. Non-goals

This contract does not add:

- production code or tests;
- a public computation endpoint;
- file, spreadsheet, image, notebook, or artifact inputs;
- user-supplied executable code;
- package installation, network access, Search, or URL Context inside the
  Computational Expert;
- numerical inputs inferred from profiles, memory, assistant messages, or
  prior sessions;
- multi-expert chaining;
- automatic retries after a computation failure;
- persistence of code, execution output, or computation results;
- a general-purpose sandbox or user-facing code runner;
- Requirements Verification or Deep Research integration.

## 5. Approaches considered

### 5.1 Model emits raw numerical values

The router would return the exact scalars and series that should be computed.

This is rejected. Structured output would prove shape, not provenance. The
model could introduce a value that never appeared in the user's request,
change a sign, normalize a percentage incorrectly, or omit an inconvenient
operand while still producing schema-valid JSON.

### 5.2 Deterministic keyword or formula router

Application code would choose computation from keywords and parse the entire
operation without a model routing decision.

This is rejected for production routing. It would create brittle prompting
friction, duplicate Agent_Col's intent judgment, and scale poorly across
domains. Deterministic code should constrain authority, not replace
collaborative interpretation.

### 5.3 Deterministic candidates plus model-selected references

Application code projects bounded numerical candidates from the current user
message. The routing model decides whether computation is useful and selects
only candidate IDs. Application code resolves the IDs and constructs the
strict Computational Expert request.

This is selected. It preserves Agent_Col's judgment while making operand
provenance locally enforceable.

## 6. Selected architecture

```text
User message
    |
    v
Deterministic URL and numeric candidate projection
    |
    v
AgentColRoutingInput v2.0
    |
    v
Tool-free structured Vertex routing call
    |
    v
Locally validated AgentColRoutingDirective v2.0
    |
    +-- direct ------> no expert
    +-- clarify -----> focused question, no expert
    +-- source ------> Source Expert
    +-- research ----> Research Expert
    `-- computation -> deterministic candidate resolution
                           |
                           v
                    ComputationExpertInput
                           |
                           v
                    ComputationalExpertService
                           |
                           v
                    Full validated internal result
                           |
                           v
                    Bounded responder projection
                           |
                           v
                    Responder-only Agent_Col
                           |
                           v
                    Final user response and receipts
```

The routing model performs no computation and invokes no expert. The executor
runs only the single route already selected and locally validated.

## 7. Deterministic numeric candidate projection

### 7.1 Source boundary

The first production boundary projects numerical candidates from the current
user message only.

It does not inspect:

- assistant messages;
- profile or memory data;
- prior-session content;
- recent chat history;
- project artifacts;
- retrieved web content;
- model-generated text.

This differs deliberately from URL routing, which may use bounded recent user
history. Numerical follow-ups such as “use the same values as before” require
clarification in the first implementation. This avoids selecting stale or
contextually unrelated numbers.

### 7.2 Candidate contract

```text
RoutingNumericCandidate
  candidate_id: number-1 through number-32
  raw_text: exact bounded slice from current_message
  value: finite numeric value parsed by application code
  notation: plain | percent | currency
  unit_symbol: exact %, $, €, £, or ¥ symbol, or null
  start_index: zero-based start in current_message
  end_index: exclusive end in current_message
```

Candidate validation must prove:

- `current_message[start_index:end_index] == raw_text`;
- spans are ordered, non-overlapping, and unique;
- `value` is finite and deterministically reparses from `raw_text`;
- a percent keeps its displayed magnitude: `5%` has value `5` and unit `%`,
  not silently normalized value `0.05`;
- currency symbols are preserved as exact syntax rather than converted;
- repeated values at different spans receive different candidate IDs;
- no candidate comes from a URL span;
- at most 32 candidates are exposed.

Supported first-version literals are signed or unsigned integers, decimals,
validated thousands-separated decimals, scientific notation, percentages,
and the five listed currency symbols. Non-finite values are rejected.

Compound or ambiguous numeric syntax is not decomposed into misleading
operands. Fractions, ratios, ranges, dates, times, version strings, and values
embedded in identifiers are either excluded as a whole or cause the numeric
projection to be marked incomplete. Spelled-out numbers are not projected.

### 7.3 Truncation and unsupported syntax

`AgentColRoutingInput` gains:

```text
numeric_candidates: zero to 32 RoutingNumericCandidate values
numeric_projection_incomplete: boolean
```

The flag is true when candidate capacity is exceeded or any numeric-like syntax
in the current message cannot be projected safely. This conservative first
boundary may decline some otherwise valid calculations rather than hide an
unrepresented value from the router. A `computation` directive is invalid when
this flag is true. Agent_Col must use `clarify` if computation is materially
needed, or `direct` when it can answer safely without execution.

Silent first-32 truncation is forbidden.

## 8. Routing input contract v2.0

`AgentColRoutingInput` retains `current_message` and URL candidates, and adds
the numeric fields above. `available_capabilities` expands from at most two to
at most three values and permits exactly:

- `source`;
- `research`;
- `computation`.

Availability remains derived from configured services. A model cannot claim
that computation is installed when no `ComputationalExpertService` is
configured.

The routing input still excludes profile content, identifiers, idempotency
keys, memory events, artifacts, credentials, and full history.

## 9. Routing directive contract v2.0

Adding a route and payload is an incompatible internal schema change.
`AgentColRoutingDirective.schema_version` therefore changes atomically from
`1.0` to `2.0`. Dual-version support is unnecessary because directives are
ephemeral and are not persisted.

`AgentColRoute` gains `computation`. The directive gains exactly one optional
`computation_intent` field.

```text
ComputationRoutingIntent
  objective: bounded text containing no numeric literals
  scalar_inputs: zero to 20 ComputationScalarSelection values
  series_inputs: zero to 8 ComputationSeriesSelection values
  precision: ComputationPrecisionSelection or null
  constraints: zero to five bounded strings containing no numeric literals

ComputationScalarSelection
  name: unique lowercase identifier
  numeric_id: one RoutingNumericCandidate ID

ComputationSeriesSelection
  name: unique lowercase identifier
  numeric_ids: one to 32 ordered, unique RoutingNumericCandidate IDs

ComputationPrecisionSelection
  mode: decimal_places | significant_figures
  digits_numeric_id: one RoutingNumericCandidate ID
```

The model assigns descriptive input names and groups candidates, but it never
emits an operand value. Names must match `^[a-z][a-z0-9_]{0,39}$` and must be
unique across scalars and series.

The directive must satisfy all of these local invariants:

- exactly one route-specific payload is present;
- computation is listed in `available_capabilities`;
- numeric projection is complete;
- at least one scalar or series selection exists;
- every selected ID exists in the exact routing input;
- an ID is selected at most once across scalars, series, and precision;
- series preserve candidate order from the current message;
- every candidate in a series has the same notation and unit symbol;
- precision digits resolve to an integer accepted by `PrecisionRule`;
- significant figures cannot resolve to zero;
- objective and constraints pass the Computational Expert's unsafe-text
  validation and contain no numerical literals;
- no expression or executable code is accepted from the routing model.

The expected presence table becomes:

```text
direct      -> no route payload
clarify     -> clarifying_question only
source      -> source_intent only
research    -> research_intent only
computation -> computation_intent only
```

## 10. Invocation and restraint rules

### 10.1 Choose computation

Choose `computation` when executable calculation materially improves
correctness or supplies evidence Agent_Col should not claim from unaided
reasoning. Examples include:

- descriptive statistics over a supplied series;
- a multi-step financial, scientific, or engineering calculation;
- checking a formula across multiple supplied values;
- a bounded transformation or numerical comparison;
- a calculation where precision or reproducible execution materially matters.

### 10.2 Choose direct

Choose `direct` when no specialist materially improves the answer, including:

- trivial arithmetic that Agent_Col can answer reliably;
- conceptual explanations of formulas;
- general programming or shell-command advice;
- prose-only reasoning;
- requests where the user explicitly declines tools or execution.

An incidental number does not justify computation.

### 10.3 Choose clarify

Choose `clarify` rather than guessing when:

- the operation is consequentially ambiguous;
- required operands are missing;
- units or scale change the answer and are unclear;
- the user refers to prior values not present in the current message;
- numeric projection is incomplete;
- a fraction, range, date, or another excluded syntax is essential;
- multiple plausible groupings would materially change the result.

The clarification asks one focused question and invokes no expert.

### 10.4 Choose another expert

- Use `source` when supplied public URL contents are required.
- Use `research` when current external public evidence is required.
- Do not use computation to discover facts.
- Do not chain Source or Research into computation in this production pass.
  If both are necessary, Agent_Col asks the user to choose or stages the work
  across turns until a separately approved multi-expert contract exists.

## 11. Deterministic request construction

After local directive validation, `AgentColExpertExecutor` constructs
`ComputationExpertInput` without another model call:

- `objective` is copied from the validated computation intent;
- scalar values are resolved from selected numeric candidates;
- series values are resolved in current-message order;
- exact percent or currency symbols are copied as units when available;
- model-assigned names become the bounded scalar or series names;
- `required_precision` is resolved from the referenced numeric candidate;
- constraints are copied only after existing computation safety validation;
- `inputs.expression` is always `None` in the first production boundary.

The executor must then instantiate `ComputationExpertInput`. A validation
failure stops before provider access and becomes a contentless
`rejected_input` computation result. Unknown programming or configuration
errors remain fatal; they are not disguised as expected expert failures.

## 12. Execution budget and lifecycle

The current production turn supports one routed expert, which is stricter than
the overall two-delegation architectural ceiling. Computation does not expand
that limit.

The existing turn service checks whether enough time remains before starting
an expert, but its named expert budget does not currently impose an active
deadline around the executor call. Computation integration must close that
gap:

- derive the allowed executor duration as the lesser of the configured expert
  budget and `remaining_turn_time - responder_reserve`;
- wrap the executor call in that active deadline;
- preserve cancellation so the Computational Expert deletes its temporary ADK
  session;
- convert a budget deadline into a contentless `timed_out` result for the
  selected capability;
- reserve time for responder-only Agent_Col;
- never automatically rerun a failed or timed-out computation.

This enforcement applies consistently to Source, Research, and Computation so
the documented expert budget becomes real rather than advisory.

## 13. Internal result and responder projection

`ComputationalExpertService` returns the full internal
`ComputationExpertResult`, including up to five bounded code/output pairs.
Those pairs are useful for validation and diagnostics, but their current
maximum size is too large to copy wholesale into every responder prompt.

The executor therefore derives a smaller server-validated projection:

```text
ComputationResponderResult
  capability: computation
  status: shared ExpertStatus
  summary: completed-only bounded summary
  limitations: completed-only bounded limitations
  payload: ComputationResponderPayload or null
  evidence: ComputationResponderEvidence or null

ComputationResponderPayload
  method: validated method
  inputs_used: validated normalized inputs
  result: validated result text

ComputationResponderEvidence
  execution_verified: true
  execution_count: one to five
  successful_execution_count: one to five
  code_character_count: bounded server-derived count
  output_character_count: bounded server-derived count
```

The projection excludes raw executed code and raw execution output. It is
derived only after the full result passes local validation. A noncompleted
result remains contentless.

This is an information-minimization boundary, not a claim that the underlying
code is secret. A future explicit evidence-inspection surface may expose
bounded execution details, but it requires a separate contract. The first
production chat integration does not persist them or add them to Agent_Col's
prompt.

Local validation proves that bounded Python executed successfully and that the
projection matches the accepted provider events. It does not prove that
arbitrary generated mathematics is semantically correct. Agent_Col must state
the inputs and method used so the answer remains inspectable.

## 14. Responder and receipt mapping

`AgentColResponderContext` expands its discriminated expert-result union to
include `ComputationResponderResult`.

For `route=computation`, it must enforce:

- result capability is `computation`;
- a completed result has the exact derived receipt;
- a noncompleted result has no action or citation receipts;
- citations are always empty for computation alone;
- direct, clarify, Source, and Research invariants remain unchanged.

`AgentActionReceipt.action_name` gains `run_computation` in the production
integration pass.

Receipt mapping is deterministic:

```text
completed computation -> run_computation/completed
all other statuses    -> no computation receipt
```

Responder-only Agent_Col integrates the validated method, inputs, result,
precision, limitations, and execution-verification metadata. It cannot reroute,
rerun computation, fabricate code, create citations, or change receipts.

## 15. Failure behavior

```text
Projection has no usable candidates
  -> computation route is invalid; clarify or direct

Projection incomplete
  -> computation route is invalid; clarify or direct

Unknown, duplicated, reordered, or conflicting candidate selection
  -> routing directive mismatch; no expert access

Constructed ComputationExpertInput fails validation
  -> rejected_input; no provider access; no receipt

Provider unavailable
  -> unavailable; responder explains the bounded failure; no receipt

Application or ADK deadline
  -> timed_out; temporary session cleanup; no receipt

Missing, failed, unpaired, oversized, or non-Python execution evidence
  -> invalid_output; no receipt

Unexpected programming/configuration defect
  -> existing safe turn-service failure and HTTP 502 behavior
```

No failure path logs user input, candidate text, numerical values, generated
code, execution output, identifiers, or provider payloads. Logs contain only
allowlisted status or exception-class metadata.

## 16. Schema and deployment compatibility

The production change must be atomic because the routing provider and local
validator share one exact schema:

1. Add numeric projection contracts and tests.
2. Add routing directive version `2.0`, computation intent, and local
   cross-validation.
3. Verify the provider-safe JSON schema against Vertex before production
   cutover.
4. Add executor mapping, responder projection, receipt derivation, and active
   expert-budget enforcement.
5. Construct `ComputationalExpertService` in FastAPI lifespan and advertise
   computation only when construction succeeds.
6. Cut over routing instruction, provider schema, validator, executor,
   responder, and tests together.

There is no Firestore migration because routing directives and full execution
results are not persisted.

The routing provider's output token cap must be reassessed through a live
compatibility test. The current 256-token cap may be insufficient for bounded
series selections. It must be raised only to the smallest verified value.

## 17. Required future TDD coverage

Implementation must begin with focused RED tests for:

### Numeric projection

- supported literal formats and exact spans;
- URL masking;
- finite-value enforcement;
- percentages retaining displayed magnitude;
- currency-symbol preservation;
- duplicate values retaining distinct IDs;
- compound ambiguous syntax exclusion;
- candidate overflow setting `numeric_projection_incomplete`;
- current-message-only provenance.

### Routing contracts

- schema version `2.0` and exact route-payload presence;
- computation capability availability;
- unknown, duplicate, reused, or reordered numeric IDs;
- scalar and series name uniqueness;
- precision ID validation;
- numeric literals forbidden in objective and constraints;
- incomplete projection forbidding computation;
- Source, Research, direct, and clarify regression coverage.

### Provider compatibility and restraint

- provider-safe schema retains the computation branch;
- live Vertex returns valid v2 directives;
- computation-worthy requests select computation;
- trivial arithmetic and prose select direct;
- missing or ambiguous operands select clarify;
- explicit no-tool requests select direct;
- Source and Research routing remain stable.

### Executor and responder

- exact candidate-to-request mapping;
- zero provider access after local mismatch;
- one computation invocation maximum;
- typed failures become contentless results;
- completed results derive exactly one `run_computation` receipt;
- responder projection excludes code/output but preserves verified counts;
- route/result/receipt mismatch is rejected;
- no citations are created.

### Turn service and application wiring

- active expert deadline preserves responder reserve;
- cancellation cleans the temporary computation session;
- late-start computation becomes `timed_out` without execution;
- FastAPI lifespan advertises computation only when configured;
- idempotent chat replay returns the original response and receipt without
  re-executing computation;
- headerless chat and existing Source/Research routes do not regress.

## 18. Manual acceptance targets for future implementation

A production integration pass is not accepted until live checks demonstrate:

1. A multi-step numerical request produces a correct Agent_Col response and
   exactly one `run_computation` receipt.
2. The response states the relevant inputs, method, precision, and result.
3. A trivial arithmetic question receives a direct answer with no action.
4. An ambiguous calculation receives one useful clarification and no action.
5. Reusing an idempotency key returns the same response without a second
   computation.
6. Changing the request under the same idempotency key returns HTTP 409.
7. Source and Research requests still route correctly.
8. No computation result or execution evidence appears in Firestore unless a
   later, separately approved artifact contract explicitly adds persistence.

## 19. Security and trust boundaries

- User text and all model output remain untrusted data.
- Numeric values become eligible only through deterministic current-message
  projection.
- Candidate IDs are server-assigned and invocation-local.
- Routing selects references; it cannot authorize persistence or external
  actions.
- The Computational Expert has no user identity, profile, history, project
  identifiers, credentials, URLs, files, Firestore client, or other experts.
- Successful execution is not equivalent to semantic correctness.
- Only locally derived receipts are authoritative.
- Agent_Col remains accountable for the final explanation.

## 20. Implementation decomposition after approval

The production change should not be implemented as one large pass. The
smallest safe sequence is:

1. **M7-EXP.5D.1 — Numeric Projection and Routing Contracts**

   Implement current-message candidate projection, directive v2.0, local
   validation, and provider-schema compatibility tests without production
   cutover.

2. **M7-EXP.5D.2 — Executor, Responder Projection, and Receipts**

   Add deterministic request construction, computation result projection,
   `run_computation` receipt derivation, and executor/responder tests without
   FastAPI cutover.

3. **M7-EXP.5D.3 — Turn-Service Budget and FastAPI Cutover**

   Enforce the active expert deadline, wire the computation service into
   application lifespan, preserve idempotency, and perform live production
   regression checks.

4. **M7-EXP.5E — Complete Tool-Belt Routing and Restraint Evaluation**

   Evaluate direct, clarify, Source, Research, and Computation judgment before
   beginning Requirements Verification or Deep Research design.

Each implementation pass requires its own approval, RED/GREEN TDD cycle,
focused automated verification, manual runtime acceptance, and GitHub
checkpoint.
