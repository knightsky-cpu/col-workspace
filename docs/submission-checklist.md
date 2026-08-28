# All Things Agentic Submission Checklist

Last reconciled: August 27, 2026.

Current roadmap authority:
[`final-checklist-planning.md`](final-checklist-planning.md).

Current source status:
[`current-state.md`](current-state.md).

This checklist tracks the actual judged submission path for the Collaborative
Partner category. Durable asynchronous artifact jobs, Google Cloud Tasks, and
private worker execution are deferred until after submission and are not
current submission requirements.

## Official Deadline

- [ ] Submit before August 31, 2026, at 5:00 PM Pacific.
- [ ] Freeze the judged build and submitted materials before final submission.
- [ ] Preserve the submitted repo, video, and hosted/testing state through the
  judging window.

## Stage One Eligibility

- [x] Category selected: Collaborative Partner.
- [x] Gemini 3.6 Flash satisfies the Gemini 3.5-or-newer requirement.
- [x] Google ADK satisfies the Google agent-framework requirement.
- [x] Google GenAI SDK is also in the allowed framework list.
- [x] Firestore satisfies the Google Cloud infrastructure requirement.
- [ ] Deploy and prove the functioning application on Google Cloud.
- [ ] Confirm every depicted feature works consistently in the judged build.
- [ ] Confirm all submitted work was created during the contest period or
  disclose any permitted pre-existing material.
- [x] Apache License, Version 2.0 is present.
- [ ] Audit third-party code, fonts, icons, libraries, and media for license
  compliance.

## Collaborative Partner Proof

- [ ] Show messy or complex user input.
- [ ] Show Agent Col asking or resolving a meaningful clarification.
- [ ] Show Agent Col synthesizing or mutating data into a useful artifact,
  plan, structured answer, or workspace output.
- [ ] Show governed workspace notes or receipt-backed continuity.
- [ ] Show Target A if implemented: correction/evidence creates a
  non-authoritative preference hypothesis, the user confirms it, and existing
  governed memory handles approval and later adaptation.
- [ ] Show Target B if implemented: Agent Col recommends or continues the next
  useful step using existing working-state understanding.
- [ ] Show memory or receipt provenance so the adaptation is inspectable.
- [ ] Show a controlled failure, limitation, or rejection path that proves
  bounded behavior without relying on background jobs.

## Production Controls

- [x] Derive user identity from a verified Google ID token in `google_oidc`
  mode.
- [ ] Require fail-closed production configuration.
- [ ] Require `google_oidc` in production.
- [ ] Replace raw-subject user identifiers with opaque production-safe user
  identity.
- [ ] Complete canonical workspace ownership and cross-owner denial checks.
- [ ] Enforce request/body size limits.
- [ ] Add bounded per-user or per-principal rate limiting.
- [ ] Add production CSP and security headers.
- [ ] Remove content-bearing validation details from logs.
- [ ] Document retention and deletion behavior.
- [ ] Configure Cloud Run maximum instances, timeouts, and budget controls.

## Repository And Reproduction

- [x] Repository contains local setup instructions.
- [x] Repository contains an architecture document and diagram source.
- [x] Repository contains a current source-state inventory.
- [x] Repository contains current finalization planning.
- [ ] Pin and verify the production Python runtime.
- [ ] Add Dockerfile and container startup instructions.
- [ ] Add `.dockerignore`.
- [ ] Add Cloud Run deployment setup.
- [x] Add local environment-variable reference without secrets.
- [ ] Add production Cloud Run environment-variable reference without secrets.
- [ ] Run the complete relevant offline suite from a clean clone.
- [ ] Run hosted smoke and security checks against the final deployment.
- [ ] Confirm `.env`, credentials, virtual environments, and generated data are
  ignored and absent from Git history.

## Devpost Materials

- [ ] Hosted project URL if available for judging/testing.
- [ ] Public repository URL, or private-repository access granted to
  `testing@devpost.com` and `cloudhackathons@google.com`.
- [ ] English project summary and value proposition.
- [ ] Features and functionality description.
- [ ] Technology and Google Cloud services description.
- [ ] Data-source and third-party integration disclosure.
- [ ] Findings and learning summary.
- [ ] Step-by-step spin-up instructions in `README.md`.
- [ ] Architecture diagram uploaded in a judge-readable format.
- [ ] Public YouTube or Vimeo demo URL.
- [ ] Confirm the video is four minutes or shorter.
- [ ] Confirm the video contains no unlicensed logos, music, footage, or other
  third-party material.

## Four-Minute Demo Runbook

- [ ] `0:00-0:20` - State the friction and Collaborative Partner value.
- [ ] `0:20-0:55` - Give Agent Col messy work and show clarification/guidance.
- [ ] `0:55-1:30` - Show synthesis or artifact work with receipts.
- [ ] `1:30-2:10` - Show notes, continuity, or retrieval-backed context.
- [ ] `2:10-2:55` - Show Target A preference-learning proof if implemented.
- [ ] `2:55-3:20` - Show Target B next-step leadership if implemented.
- [ ] `3:20-3:45` - Show memory/receipt proof and Firestore evidence.
- [ ] `3:45-4:00` - Show Cloud Run or Google Cloud proof and close.

## Optional Bonus Work

- [ ] Publish a public build article or video with the required hackathon
  disclosure.
- [ ] Publish a social post using `#AllThingsAgenticHackathon`.
- [ ] Add another eligible Google AI model only if the core judged workflow is
  already stable, deployed, polished, and documented.

Optional bonus work must not displace Collaborative Partner proof, deployment
evidence, documentation clarity, or demo quality.
