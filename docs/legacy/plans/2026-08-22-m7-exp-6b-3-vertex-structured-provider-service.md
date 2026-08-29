# M7-EXP.6B.3 — Vertex Structured Provider Service

## Goal

Add one isolated, tool-free Vertex structured-generation service that produces
a `RequirementsVerificationCandidate` and immediately submits it to the
authoritative deterministic validator from M7-EXP.6B.2.

This pass does not connect Requirements Verification to production routing,
FastAPI, Firestore, receipts, or Agent_Col's responder.

## Provider boundary

- Model: `gemini-3.6-flash`
- Provider: existing Vertex AI Google GenAI client
- Location: `global`, supplied by the shared Vertex configuration
- Requests per verification: exactly one
- Temperature: `0`
- Thinking level: `LOW`
- Maximum output tokens: `16,384`
- Service timeout: `45` seconds
- Response MIME type: `application/json`
- Schema: provider-safe adaptation of
  `RequirementsVerificationCandidate.model_json_schema()`
- Tools, automatic function calling, repair retries, and semantic retries: none

## Trust boundary

The provider receives only the bounded `RequirementsVerificationInput`,
serialized inside explicit untrusted-data delimiters. It receives no user or
session identifiers, history, memory, credentials, Firestore references,
artifacts, or persistence authority.

The provider must return exactly one assessment per supplied requirement, use
only supplied requirement and subject identifiers, and copy evidence excerpts
exactly from the supplied subject text. Provider schema conformance is not
authoritative: the M7-EXP.6B.2 validator must accept the candidate before the
service returns a completed result.

## Failure contract

`RequirementsVerificationServiceError` exposes only safe status metadata:

- invalid input: `rejected_input`
- provider or transport failure: `unavailable`
- timeout: `timed_out`
- unusable provider output: `invalid_output`

Invalid output is further classified as `missing_response_text`,
`invalid_json`, `schema_validation_failed`, or `local_validation_failed`.
Logs and exceptions must not copy request or provider content.

## TDD and verification

RED tests cover the successful one-request path first, then configuration and
schema restraints, pre-provider input rejection, safe output classifications,
deterministic-validator rejection, timeouts, provider failures, absence of
content leaks, and absence of semantic retries. A fake-provider smoke command
proves the offline boundary. One bounded live Vertex smoke request is the
manual runtime acceptance target.

## Stop conditions

Stop and revise this design if Vertex rejects the adapted schema, if success
requires weakening the canonical 6B.2 contracts, if bounded output cannot
represent the candidate, if a repair loop is required, or if implementation
requires modifying production routing or application state.
