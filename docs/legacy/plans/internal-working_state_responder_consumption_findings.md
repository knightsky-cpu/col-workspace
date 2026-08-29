# Internal Working State Responder Consumption Findings

Date: 2026-08-27

## Pass Status

Accepted by manual and backend verification.

## Implemented Pass

The pass added responder instructions for `[SERVER_VALIDATED_WORKING_STATE]`
without changing working-state schema, routing, persistence, public API shape,
frontend display, artifacts, notes, or memory behavior.

Changed files:

- `agent_col_responder.py`
- `tests/test_agent_col_turn_service.py`
- `docs/superpowers/plans/internal-working_state_responder_consumption_plan.md`

## Automated Verification

- `venv/bin/pytest tests/test_agent_col_turn_service.py::test_responder_instruction_defines_hidden_working_state_policy -q`
  - Result: 1 passed, 1 existing ADK `BaseAgentConfig` deprecation warning.
- `venv/bin/pytest tests/test_agent_col_turn_service.py::test_turn_service_injects_hidden_working_state_for_responder -q`
  - Result: 1 passed, 1 existing ADK `BaseAgentConfig` deprecation warning.
- `venv/bin/pytest tests/test_main.py::test_chat_uses_hidden_working_state_without_public_response_fields -q`
  - Result: 1 passed, 1 existing ADK `BaseAgentConfig` deprecation warning.
- `git diff --check`
  - Result: no whitespace errors.

## Manual Verification Evidence

The user ran the approved four-prompt same-session flow in workspace
`collab-test`:

1. `I want to develop a deployment plan, probably Cloud Run, but security matters more than speed.`
2. `Actually, artifact generation only takes 10 seconds.`
3. `I'm not sure whether browser disconnects matter yet, but I want the plan to stay simple.`
4. `Can you turn the current plan into a short checklist without deciding the unresolved deployment questions for me?`

Observed behavior:

- Agent Col continued the same Cloud Run deployment-planning thread.
- It carried forward security priority, Cloud Run, simple architecture, and
  fast artifact generation.
- It generated a checklist artifact while preserving unresolved deployment
  questions for user decision.
- The public response did not expose `SERVER_VALIDATED_WORKING_STATE`, raw
  JSON, `model_thoughts`, hidden context, or private reasoning.

## Backend Verification Evidence

Read-only Firestore inspection found the relevant session:

- Project: `project--eb3e1d02bb1c9e01c59957622341f107--collab-test`
- Session: `session--cad05a41-06ed-42c2-8fe2-129b944f7e2b`
- Working state document: present at `sessions/{session_id}/working_state/current`

Current hidden working state:

- `status`: `active`
- `authority`: `non_authoritative`
- `schema_version`: `1.0`
- `request_summary`: user requested converting the deployment plan into a
  short checklist while leaving open deployment decisions for the user.
- `current_goal`: develop a simple and secure Cloud Run deployment blueprint.
- `intent_hypothesis`: user wants an actionable checklist while maintaining
  control over open architecture choices.
- `active_constraints`:
  - prioritize security
  - use Google Cloud Run
  - keep architecture simple
  - do not decide unresolved deployment questions for user
- `clarification_status`: `useful`
- `unresolved_questions`:
  - useful: choose ingress/perimeter architecture, direct native URL vs.
    Cloud Armor WAF with Global Load Balancer
  - not blocking: determine whether explicit server-side cleanup or state
    management is required for client disconnects
- `next_step_hypothesis`: assist the user in selecting architectural options
  or writing CI/CD deployment scripts once choices are made.
- `confidence`: `high`

Conclusion: the working-state pipeline stored and updated the right
same-session collaboration facts, and the responder consumed them well enough
to preserve unresolved decisions in the user-facing checklist.

## Caveat: Cloud Run Disconnect Claim

The responder made a too-confident domain claim that browser disconnects are
handled automatically by Cloud Run. That is not a working-state persistence or
injection failure. The hidden state correctly preserved disconnect handling as
unresolved/non-blocking after the turn.

Official Google Cloud Run documentation says:

- HTTP/1.1 client disconnect events are not propagated to the Cloud Run
  container; WebSockets or HTTP/2 are needed if disconnect propagation matters.
  Source: https://docs.cloud.google.com/run/docs/troubleshooting
- Request timeout closes the network connection, but the serving container
  instance is not terminated and code may keep processing. For longer timeouts,
  Google recommends retries and idempotent or resumable request handlers.
  Source: https://docs.cloud.google.com/run/docs/configuring/request-timeout

Interpretation: this was mainly model answer-quality risk on a platform-specific
architecture detail. Engineering can reduce this risk by tightening responder
policy for unresolved working-state questions and by routing current platform
claims to source/research paths when factual accuracy matters.

## Recommended Next Pass TLDR

Add backend-only working-state debug visibility for local development and tests:
structured logs on load/inject/update/save that include session/project ids,
state presence, clarification status, unresolved-question counts, and source
message id, while never logging hidden state content or exposing it through the
public API.
