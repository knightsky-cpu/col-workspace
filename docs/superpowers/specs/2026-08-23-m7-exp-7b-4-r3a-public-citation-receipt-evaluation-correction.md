# M7-EXP.7B.4-R3A Public Citation Receipt Evaluation Correction

## Status

Approved for implementation on 2026-08-23.

## Decision

The bounded live evaluator treats the public `ChatResponse.citations` array as
the authoritative citation-receipt boundary. It does not require each raw
citation URI to be repeated inside the model-authored response text.

For the fixed Source probe, automated evaluation requires:

- exactly one completed `url_context` action receipt;
- at least the exact public URL selected from the server-owned routing
  projection among the returned citation receipts;
- no memory proposal or adaptation created by the expert result.

For the fixed Research probe, automated evaluation requires:

- exactly one completed `google_search` action receipt;
- one or more validated citation receipts;
- an authoritative `python.org` source label for the fixed Python-release
  question;
- no memory proposal or adaptation created by the expert result.

## Root cause

The first live evaluator classified a completed Source response as
`citation_mismatch` even though it returned the exact validated citation
receipt for `https://example.com/`. The responder referred to the source by
its label, `Example Domain`, without repeating the literal URI in its prose.

The previous helper checked only whether every raw URI string occurred
somewhere in the response text. That check was both too strict and too weak:

- it rejected valid public citation receipts when Agent_Col used a source
  label instead of a raw URL;
- a URI appearing anywhere in prose does not prove that it supports a
  particular externally sourced claim.

The application already derives citations from locally validated expert
results and exposes them separately from model-authored prose. The public
receipt is therefore the deterministic evidence available to this automated
layer.

## Qualitative citation review

Whether Agent_Col clearly associates an external claim with the correct source
remains a `manual_review_required` question. The repository owner reviews the
response text together with the authoritative citation receipts. The evaluator
must not claim that simple string containment proves semantic claim grounding.

## Preserved invariants

- Agent_Col remains the sole user-facing responder.
- Source and Research citations remain application-derived receipts.
- A Source citation for an unselected URL fails with `citation_mismatch`.
- Research without validated citations or the expected authoritative source
  label fails with `citation_mismatch`.
- Direct, clarification, Computation, and Requirements Verification responses
  cannot acquire external citations through this correction.
- No production responder, routing, expert, schema, persistence, retry, or
  provider behavior changes.

## Exclusions

- No computation-routing correction.
- No response rewriting or deterministic citation footer.
- No model prompt change.
- No new public response field.
- No live provider retry.

## Verification contract

- A completed Source response with the exact citation receipt passes even when
  the literal URI is absent from prose.
- A Source response citing an unselected URL fails.
- A completed Research response with an authoritative citation receipt passes
  even when the raw URI is absent from prose.
- Existing action, citation, memory, replay, conflict, report, and exit
  semantics remain green.
