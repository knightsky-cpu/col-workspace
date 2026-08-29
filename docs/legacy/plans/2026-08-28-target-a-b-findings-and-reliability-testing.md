# Target A and Target B Findings and Reliability Testing Notes

## Purpose

This document records what was implemented and learned during the Target A and
Target B passes on August 28, 2026. The work is implemented, manually exercised,
and ready for checkpoint, but it still needs broader consistency and reliability
testing across unrelated topics, conversation shapes, and preference domains.

## Target A: Preference Learning Confirmation Loop

Target A added governed, non-authoritative preference learning from repeated
same-session correction patterns. The implementation does not silently create
active memory. It stores bounded workspace-scoped observations and hypotheses,
then opens a user confirmation choice before any durable memory proposal can be
created.

The implemented Target A behavior is:

- repeated explicit correction evidence can create a preference hypothesis;
- hypotheses remain non-authoritative and cannot adapt responses by themselves;
- confirmation presents a real memory-candidate choice and a no-save choice;
- choosing no-save produces no profile proposal;
- choosing the memory-candidate path still goes through the existing governed
  memory proposal and approval loop;
- active durable memory is still created only by explicit user approval.

Manual testing found an important distinction: an explicit phrase such as
"I prefer when you answer directly first, then give the steps" was already
valid under the old governed memory contract because it is direct current-user
preference evidence. That path is not silent memory creation and does not
conflict with the old M9 contract. The Target A-specific behavior remains the
new repeated-correction confirmation path, not the already-existing explicit
preference proposal path.

Target A therefore needs additional reliability testing that separates:

- explicit current-message memory requests;
- repeated correction patterns without explicit memory intent;
- no-op handling when the same preference is already active;
- rejection/no-save paths;
- cases where user phrasing is ambiguous or topic-specific;
- cases where model-authored text or prior history must not become evidence.

## Target B: Visible Agent Leadership From Working State

Target B strengthened the existing hidden same-session working-state prompts.
It did not add a generalized planner or new public state surface. The responder
now has explicit instructions to use `next_step_hypothesis` to recommend the
next consequential authorized step, continue obvious authorized work, identify
blockers, and guide non-blocking decisions with clear options.

The working-state provider now has explicit instructions to make
`next_step_hypothesis` action-oriented while preserving that it is not an
authorization. Working state remains hidden, same-session scoped,
non-authoritative, possibly stale, and subordinate to the current user message,
approved memory, workspace notes, persisted artifacts, routing/expert context,
and higher-priority instructions.

Manual testing across an audit-logging planning conversation showed the desired
Target B behavior:

- "ok continue" advanced the existing goal instead of asking what to do next;
- "Make that more concrete and keep going" continued from the same plan;
- "Actually assume we cannot add new infrastructure yet" incorporated the new
  constraint instead of restarting;
- "continue from there" carried forward the constrained plan;
- the model asked for operating system and database details only when those
  details became useful for a more exact implementation.

The same transcript also showed that artifact creation may occur as part of the
broader application behavior. That is separate from the Target B visible
leadership prompt change and should be watched during reliability testing if a
future pass needs stricter "chat-only" continuation behavior.

## Remaining Consistency and Reliability Testing

The Target A and Target B changes should be tested across a wider topic matrix
before treating the behavior as broadly reliable:

- technical planning, implementation, debugging, research, learning, and
  creative-writing topics;
- short, medium, and long conversations;
- direct follow-ups such as "continue", "keep going", "make it concrete", and
  "use that";
- corrections that add constraints midstream;
- blocking versus non-blocking ambiguity;
- explicit preferences versus inferred repeated corrections;
- approved, rejected, pending, duplicate, and no-save memory states;
- conversations where hidden working state is stale or partially wrong.

Successful broad testing should show that Agent Col leads when the next step is
already authorized, asks concise questions only for real blockers, preserves
user authority, and never turns hidden working state or inferred preferences
into silent durable memory.
