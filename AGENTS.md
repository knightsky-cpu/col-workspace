# AGENTS.md

## Purpose

This file defines the required collaboration and engineering workflow for this repository. Its goals are to keep source-code changes bounded, test-driven, evidence-based, manually verified where appropriate, and explicitly approved by the user at every implementation-pass boundary.

These instructions are binding for agents working in this repository.

## Scope of the approval-gated workflow

The approval-gated implementation workflow applies whenever an agent will add, modify, or delete source code. This includes:

- application and library code;
- UI components, graphics, styles, and animation code;
- tests and test-support code;
- behavior-affecting scripts, schemas, and source configuration;
- build or dependency changes that can affect application behavior.

The workflow does not automatically apply to:

- read-only investigation or diagnosis;
- architecture or source reviews;
- status reports;
- implementation-plan drafting;
- documentation-only changes;
- other work that does not alter source behavior.

The user may explicitly require an approval gate for any otherwise exempt task. When instructions conflict, the user's current explicit direction takes precedence.

## Core collaboration contract

For every source-changing request, use this lifecycle:

1. Understand and investigate the request without editing source code.
2. Propose a bounded implementation-pass plan.
3. Wait for the user's explicit approval or requested revisions.
4. Execute only the approved pass, using test-driven development.
5. Run focused automated verification and inspect the actual results.
6. Report what changed, verification evidence, remaining limitations, manual visual-verification targets, and a proposed next-pass plan.
7. Stop at **implemented, pending manual verification**.
8. Wait for the user to confirm success or report failure.
9. If verification fails, use systematic debugging, propose a fix plan, and wait for approval before changing source.
10. If verification succeeds, wait for explicit approval before implementing the next pass.

Automated tests, builds, or agent-observed behavior do not replace the user's acceptance. A pass is not accepted until the user confirms that its required manual verification succeeded.

## GitHub checkpoint workflow

When the user requests a GitHub checkpoint in this repository, commit and push
directly to `origin/main` with no pull request. Use explicit path staging for
the accepted pass, not broad staging such as `git add -A`. Because the managed
workspace may block writes to `.git`, perform the explicit staging and commit
with elevated Git access when needed, then push the resulting commit to
`origin/main`. Do not checkpoint unaccepted work.

## Source-changing implementation workflow

### 1. Request and investigation

When the user requests a source change:

- inspect the current repository state and relevant local instructions;
- trace the existing behavior and identify the actual change boundary;
- inspect relevant tests, configuration, and documentation;
- identify behavior that must not regress;
- use read-only commands and diagnostics as needed;
- do not edit source code during this stage.

The investigation should produce evidence, not guesses. If the request is ambiguous in a way that materially changes the implementation, ask one concise question at a time. Otherwise, make narrow, clearly stated assumptions.

### 2. Proposed implementation-pass plan

Before editing source code, present a bounded plan containing:

- the pass goal and user-visible outcome;
- the current behavior or verified problem;
- the proposed technical approach;
- the exact files or subsystems expected to change;
- behavior and invariants that must be preserved;
- the failing test or tests that will begin the TDD cycle;
- the focused verification commands that will be run;
- manual visual or runtime verification targets;
- material risks, trade-offs, and known exclusions;
- conditions that would require stopping and revising the plan.

Keep each pass narrow enough to review, test, and manually verify independently. Do not hide unrelated refactors or cleanup inside a feature or fix pass.

### 3. Approval gate

After proposing the plan, stop and wait for explicit user approval.

Valid approval clearly authorizes implementation, for example:

- “Approved; proceed.”
- “I approve this pass.”
- “Use option 2 and implement it.”

Questions, discussion, partial agreement, or approval of the general goal are not authorization to edit source code. If the user revises the plan, incorporate the revision and present the updated boundary before implementation.

### 4. Execute only the approved scope

After approval:

- follow the approved plan and TDD cycle;
- preserve unrelated user-owned changes;
- avoid speculative additions and unrelated refactoring;
- stop if evidence shows the approved approach is wrong or materially incomplete;
- propose a revised plan and wait for approval before expanding or changing direction.

Small implementation details that do not change the approved outcome or risk boundary may be resolved by the agent. New behavior, broader refactoring, dependency changes, or cross-surface expansion require renewed approval.

### 5. Automated verification

Run the narrowest focused verification that can prove the approved pass.

Focused verification is the default. Examples include:

- a single unit test or named test case;
- one component-test file;
- one targeted integration or browser scenario;
- the directly affected package's tests;
- targeted linting, type checking, build checks, or static validation required by the changed files.

Do **not** run the full test suite by default.

Run the full suite, or a materially broader verification set, only when at least one of these conditions applies:

- the change alters a shared contract or behavior used across multiple surfaces;
- the change affects cross-cutting state, navigation, persistence, security, build behavior, or infrastructure;
- focused tests reveal a regression outside the immediate boundary;
- the repository's required release or checkpoint process mandates it;
- the user explicitly requests it;
- focused verification cannot provide credible evidence of safety.

When broader verification is required, state why the focused checks are insufficient. Do not expand verification merely out of habit.

Always inspect command output, exit codes, warnings, skipped tests, and failure counts. Never infer success from a command having started or from unrelated checks passing.

### 6. Implementation-pass report

When the approved implementation is complete, report:

1. **Pass status:** use **implemented, pending manual verification** until the user accepts it.
2. **What changed:** concise behavior-level summary.
3. **Files changed:** created, modified, or deleted files and their responsibilities.
4. **TDD evidence:** which test was written first, how RED failed, what minimal implementation made it GREEN, and any refactoring performed afterward.
5. **Automated verification:** exact focused commands, results, failures, warnings, or skipped coverage.
6. **Scope deviations:** anything the plan could not complete or any approved behavior intentionally deferred.
7. **Manual visual/runtime verification targets:** exact checks for the user.
8. **Proposed next pass:** a bounded next implementation plan, not an action already underway.

Do not describe the work as fully complete, accepted, or successful while manual verification is pending.

### 7. Manual visual and runtime verification gate

For user-facing, visual, interactive, performance-sensitive, platform-specific, or environment-dependent changes, give the user a concrete manual checklist.

Each target should specify, where relevant:

- exact route, screen, feature, or entry point;
- required setup, account, content, or application state;
- viewport, device class, rendering tier, theme, or platform;
- precise actions to perform;
- expected visual and behavioral result;
- regression behavior that must remain unchanged;
- responsive, keyboard, accessibility, reduced-motion, loading, and error-state checks;
- any limitation that automated tests could not verify.

Manual targets must be observable and falsifiable. Avoid vague requests such as “make sure it looks right.”

The user's live result is decisive for acceptance. Green automated tests do not override a reported visual, runtime, usability, or performance failure.

### 8. Success and next-pass authorization

If the user confirms that manual verification succeeded:

- record the pass as accepted;
- restate the proposed next-pass boundary if needed;
- wait for explicit authorization to implement that next pass.

Acceptance of the current pass and authorization of the next pass are separate decisions. A single user message may provide both only when it clearly does so, for example: “This pass succeeded; proceed with the proposed next pass.”

Never begin the next source-changing pass merely because it was included in the previous report.

### 9. Failure and fix authorization

If the user reports that manual verification failed:

- do not patch immediately;
- capture the exact symptom and environment;
- use the systematic-debugging process below;
- determine or narrow the root cause with evidence;
- propose a focused fix plan, regression test, verification commands, and manual retest targets;
- wait for the user's explicit approval or revision;
- implement the approved fix using TDD;
- report again as **implemented, pending manual verification**.

## Test-driven development (TDD)

### Definition and governing rule

TDD means writing a test for the desired behavior before writing the production code, observing that test fail for the expected reason, writing the smallest implementation that makes it pass, and then improving the code without changing behavior while keeping tests green.

The governing rule is:

> No production source code for new or changed behavior without a failing test first.

Tests written after implementation are useful coverage, but they are not TDD. A test that passes immediately does not prove that it can detect the missing behavior or regression.

### When TDD is required

Use TDD for:

- new features;
- bug fixes;
- behavior changes;
- refactoring;
- source changes to UI, graphics, animation, state, APIs, schemas, scripts, or build behavior.

If a requirement cannot reasonably be expressed through an automated test, stop and request an explicit exception from the user. Explain why automation is impractical and propose the strongest available focused automated check plus concrete manual verification. Do not silently replace test-first development with tests written afterward.

Throwaway exploration may be used to learn, but it must be discarded before the real implementation begins. Production code must then be implemented fresh through the TDD cycle.

### The Red–Green–Refactor cycle

#### RED — Write one minimal failing test

Write the smallest test that demonstrates one required behavior.

A good RED test:

- has a precise name describing the behavior;
- tests real observable behavior rather than implementation details;
- uses real code and avoids mocks unless isolation is otherwise impossible;
- contains one reason to fail;
- demonstrates the desired interface or user outcome;
- covers a regression directly when fixing a bug.

#### Verify RED — Observe the correct failure

Run the narrowest command that executes the new test and confirm:

- the test fails rather than crashing because of invalid setup;
- the failure message matches the missing behavior;
- the test does not fail because of a typo, broken fixture, unrelated error, or environment problem;
- the test would pass only after implementing the intended behavior.

If the test passes immediately, it does not establish the new requirement. Correct the test or confirm that the behavior already exists. If the test errors, fix the test setup and rerun it until it fails for the expected behavioral reason.

Do not write production implementation before valid RED evidence exists.

#### GREEN — Implement the minimum behavior

Write the simplest production change that makes the failing test pass.

During GREEN:

- implement only the tested behavior;
- do not add speculative options or future features;
- do not bundle unrelated refactors;
- prefer the smallest change consistent with the existing architecture;
- keep the approved pass boundary intact.

#### Verify GREEN — Observe the test pass

Run the focused test again and confirm:

- the new test passes;
- directly related tests still pass;
- output contains no unexplained errors or warnings;
- the command exits successfully.

If the test remains red, change the implementation, not the requirement expressed by a correct test. If related tests regress, investigate and resolve those regressions before proceeding.

#### REFACTOR — Improve structure while staying green

Only after GREEN may the agent:

- remove duplication;
- improve names;
- extract focused helpers;
- simplify control flow;
- align the implementation with established local patterns.

Refactoring must not introduce new behavior. Rerun the focused tests after refactoring and keep them green.

#### Repeat

Start a new RED–GREEN–REFACTOR cycle for the next independently testable behavior. Do not write a large batch of tests followed by a large batch of production code when smaller behavioral cycles are possible.

### TDD requirements for fixes

Every fix requires a failing regression test that reproduces the verified root cause or externally observable failure before the corrective production change is made.

The regression test must:

- fail against the unfixed behavior for the expected reason;
- pass after the minimal fix;
- remain in the suite to prevent recurrence;
- test the real failure boundary when practical.

Manual reproduction alone is not a substitute for a regression test. It supplements the automated test when the failure is visual, timing-sensitive, performance-sensitive, hardware-specific, or platform-specific.

### TDD stop conditions

Stop and correct the process if any of these occurs:

- production code was written before the failing test;
- the new test never failed;
- the failure reason was not inspected;
- the test was changed to accommodate an incorrect implementation;
- tests were deferred until after the feature or fix;
- manual testing was used as the only verification without an approved exception;
- the implementation expanded beyond the tested and approved behavior.

If production code was written before RED, discard the premature implementation and restart from the failing test. Do not retain it as a reference to be adapted.

## Systematic debugging

### Definition and governing rule

Systematic debugging means establishing the root cause through reproducible evidence before proposing or implementing a fix.

The governing rule is:

> No fix without root-cause investigation first.

Do not guess, stack speculative patches, or treat a symptom as the cause. A quick patch without a causal explanation is not an acceptable fix plan.

### When systematic debugging is required

Use this process for:

- user-reported failures;
- failing tests or builds;
- runtime errors;
- visual or interaction regressions;
- performance problems;
- environment-specific failures;
- integration and deployment failures;
- unexpected behavior discovered during implementation.

### Phase 1 — Root-cause investigation

Before proposing a fix:

1. Read the complete error, warning, stack trace, logs, and relevant output.
2. Reproduce the symptom consistently with exact steps when possible.
3. Record the environment, state, input, route, device, viewport, tier, or configuration involved.
4. Inspect relevant recent/local changes and repository state.
5. Trace the failing value or behavior backward through callers and component boundaries.
6. In multi-component systems, gather evidence at each boundary: input, output, configuration, state, and failure handling.
7. Distinguish source defects from test-runner, sandbox, dependency, network, or environment failures.

Success for Phase 1 means the agent can explain what fails, where it fails, and why, or can clearly state what evidence is still missing. Reproduction without causal understanding is not enough.

### Phase 2 — Pattern analysis

Before choosing a correction:

1. Find a working example or neighboring path in the same codebase.
2. Read the relevant reference implementation completely when one exists.
3. Compare the working and failing paths.
4. List meaningful differences, including configuration, state, timing, ownership, lifecycle, and dependencies.
5. Identify the repository pattern the fix should preserve.

Do not dismiss differences without evidence.

### Phase 3 — Single hypothesis and minimal test

State one explicit hypothesis in this form:

> I believe **X** is the root cause because **Y evidence**; changing or measuring **Z** should confirm or reject it.

Then test the hypothesis with the smallest non-destructive experiment or diagnostic possible. Change one variable at a time.

If the hypothesis is rejected, return to the evidence and form a new one. Do not layer another speculative change on top. If the behavior is not understood, say so and continue investigating rather than pretending certainty.

### Phase 4 — Approved fix through TDD

After the root cause is supported by evidence:

1. Present the diagnosis and evidence to the user.
2. Propose one focused fix plan and identify preserved behavior and risks.
3. Specify the failing regression test, focused automated checks, and manual retest targets.
4. Wait for explicit user approval.
5. Write and verify the failing regression test.
6. Implement one minimal root-cause fix.
7. Verify GREEN and directly related behavior.
8. Refactor only after tests are green.
9. Report as **implemented, pending manual verification**.

The fix must address the cause, not merely hide the symptom.

### Repeated failed fixes

Track attempted fixes. If three approved fix attempts fail for the same underlying problem:

- stop proposing incremental patch number four;
- reassess whether the architecture, shared state, ownership, lifecycle, or interface is fundamentally wrong;
- summarize the three attempts and what each revealed;
- present architectural options and trade-offs;
- wait for the user's direction before further source changes.

Difficulty, uncertainty, or a slow investigation does not justify speculative fixing.

## Focused verification policy

Focused verification is a deliberate repository rule, not a shortcut.

For each pass:

1. Begin with the exact test used for RED/GREEN.
2. Run directly related tests for the changed module or surface.
3. Add only the static, build, integration, or browser checks needed to prove the specific risk boundary.
4. Stop when the approved behavior and likely regressions have credible evidence.
5. Escalate to a broader or full suite only under the conditions defined above.

Examples:

- A pure validation change: run the named validation test and closely related schema tests.
- A component interaction change: run that component's tests and one focused browser scenario if rendering behavior matters.
- A shared navigation-state change: run focused state tests plus affected route/component scenarios; a broader suite may be required because multiple surfaces consume the state.
- A global style/token change: run affected visual scenarios across representative routes and viewports; do not run unrelated backend tests unless another dependency changed.
- A build-configuration change: run the focused config test if available plus the required build or packaging verification.

The implementation report must identify which checks were intentionally not run and why they were unnecessary for the pass.

## Required pass-report template

Use this structure after each implementation or approved fix:

```markdown
## Pass status

Implemented, pending manual verification.

## What changed

- [Behavior-level change]

## Files changed

- `path/to/file`: [responsibility of change]

## TDD evidence

- RED: [test and expected failure]
- GREEN: [minimal implementation and passing result]
- REFACTOR: [cleanup performed, or “none”]

## Focused automated verification

- `[exact command]` — [result]
- Full suite not run: [why focused verification is sufficient]

## Scope notes and limitations

- [Deferred behavior, deviation, warning, or “none”]

## Manual visual/runtime verification targets

1. [Exact setup, action, and expected result]
2. [Regression target]

## Proposed next pass

- Goal: [bounded goal]
- Proposed approach: [summary]
- Expected files/surfaces: [scope]
- Approval required before implementation.
```

If broader or full-suite verification was necessary, replace the “Full suite not run” line with the exact command, result, and reason it was required.

## Prohibited workflow shortcuts

Agents must not:

- edit source before the implementation plan is approved;
- treat plan discussion as implementation authorization;
- write production behavior before observing a valid failing test;
- call tests written after implementation “TDD”;
- fix a reported failure before investigating its root cause;
- apply multiple speculative fixes at once;
- run the full suite by default when focused verification is sufficient;
- claim success from green tests while the user reports a live failure;
- mark a pass accepted before the user's manual confirmation;
- begin a proposed next pass without explicit approval;
- expand an approved pass into unrelated cleanup or architecture work.

## Final operating principle

For source-code work, the required rhythm is:

> Investigate → propose → obtain approval → RED → verify RED → GREEN → verify GREEN → refactor → focused verification → report → manual verification → obtain approval again.

For failures, insert systematic root-cause debugging before the fix plan and restart the TDD cycle only after the user approves that plan.
