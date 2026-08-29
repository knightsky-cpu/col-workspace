# Agent Col Submission Checklist

Last reconciled: August 29, 2026.

This checklist contains remaining work only. Current source, tests,
`repo-map.md`, `docs/architecture.md`, and `docs/current-state.md` are the
authority for implementation status. Legacy documentation is historical
provenance, not a source of active requirements.

## Required Submission And Finalization Work

- [ ] Submit before August 31, 2026 at 5:00 PM PT / 8:00 PM ET.
- [ ] Freeze the exact judged commit, hosted build, demo video, and written
  submission materials.
- [ ] Confirm the public repository URL or private judge access is ready.
- [ ] Confirm Apache License, Version 2.0 remains present.
- [ ] Audit third-party code, fonts, icons, libraries, media, and generated
  assets for license and disclosure requirements.
- [ ] Confirm every submitted feature claim is implemented in current source
  and visible in the demo or written evidence.
- [ ] Preserve the submitted repository, hosted app, video, and testing state
  through the judging window.

## Hosted And Demo Verification

- [ ] Re-verify the final Cloud Run hosted URL after the submission freeze.
- [ ] Verify Google OIDC login on the hosted build.
- [ ] Verify workspace ownership and cross-workspace access behavior on hosted
  state.
- [ ] Verify `/workspace`, `/api/auth/session`, and a representative
  idempotent `/api/chat` turn on the hosted build.
- [ ] Verify memory proposal/clarification/approval behavior on hosted state.
- [ ] Verify collaborative note proposal/decision/lifecycle behavior.
- [ ] Verify continuity retrieval or ambiguity-choice behavior.
- [ ] Verify specialist receipts/citations for at least one grounded or routed
  expert flow.
- [ ] Verify artifact creation, detail display, lifecycle, versioning, or
  feedback behavior used in the demo.
- [ ] Verify retry uses the same request/idempotency key for a recoverable chat
  failure path.
- [ ] Inspect hosted logs for submission-safe diagnostics and no secret or
  content-heavy leakage.
- [ ] Confirm Cloud Run environment/runtime settings match the frozen build.

## Documentation And Evidence Work

- [ ] Final-review `docs/architecture.md` for current architecture accuracy.
- [ ] Final-review `docs/current-state.md` for implemented capability accuracy.
- [ ] Final-review this checklist so it contains remaining work only.
- [ ] Confirm `README.md` setup, environment, and deployment notes match the
  frozen source.
- [ ] Capture source-backed evidence for Gemini, Google ADK, Google GenAI SDK,
  Firestore, Cloud Run, Google OIDC, and architecture claims.
- [ ] Capture screenshots or notes for hosted auth, chat, memory, notes,
  continuity, specialist receipts, and artifact behavior.
- [ ] Confirm stale documents remain under `docs/legacy/` and are not linked as
  current implementation truth.

## Demo Recording And Presentation Work

- [ ] Prepare a four-minute-or-shorter demo script for the Collaborative
  Partner category.
- [ ] Show messy or underspecified user input.
- [ ] Show Agent Col resolving a clarification, continuity choice, or governed
  context decision.
- [ ] Show governed memory or collaborative notes with inspectable receipts or
  provenance.
- [ ] Show a routed specialist flow with receipt/citation evidence.
- [ ] Show useful artifact creation, mutation, versioning, or feedback.
- [ ] Show an intentional bounded limitation, failure, retry, or rejection path.
- [ ] Show the final Cloud Run hosted application in the recording.
- [ ] Upload the demo to a public YouTube or Vimeo URL.
- [ ] Verify the video has no unlicensed music, logos, footage, or third-party
  material that requires additional disclosure.
- [ ] Prepare Devpost project summary, feature list, technology stack, Google
  Cloud services description, data-source disclosure, and learning summary.

## Optional Polish

- [ ] Tighten demo copy or UI presentation only if the judged build is already
  stable.
- [ ] Add extra evidence screenshots for judges.
- [ ] Run additional smoke scenarios that support the exact demo path.
- [ ] Publish an optional build article or social post after core materials are
  frozen.

## Post-Submission Technical Debt

- [ ] Add distributed rate limiting.
- [ ] Expand indexed pagination/query support.
- [ ] Broaden preference extraction beyond explicit concise/shorter feedback.
- [ ] Add durable asynchronous/background execution.
- [ ] Improve blueprint/generic artifact lifecycle parity.
- [ ] Clean up compatibility, tests-only, live-check-only, and apparently unused
  legacy source after the freeze.
- [ ] Deepen retention, deletion, privacy, and operational hardening.
