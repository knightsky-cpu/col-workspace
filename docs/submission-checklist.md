# All Things Agentic Submission Checklist

## Deadlines

- [ ] Request available Google Cloud credits before August 28, 2026, at
  12:00 PM Pacific if credits are needed.
- [ ] Freeze the judged build by August 30, 2026.
- [ ] Submit before August 31, 2026, at 5:00 PM Pacific.

## Stage One Eligibility

- [x] Category selected: Collaborative Partner.
- [x] Gemini 3.6 Flash satisfies the Gemini 3.5-or-newer requirement.
- [x] Google GenAI SDK is an allowed Google agent framework.
- [x] Firestore satisfies the Google Cloud infrastructure requirement.
- [ ] Deploy the functioning application to Google Cloud.
- [ ] Confirm every depicted feature works consistently in the judged build.
- [ ] Confirm all submitted work was created during the contest period or
  disclose any pre-existing material.
- [x] Select and add the Apache License, Version 2.0.
- [ ] Audit third-party code, fonts, icons, libraries, and media for license
  compliance.

## Repository and Reproduction

- [x] Repository contains local setup instructions.
- [x] Repository contains an architecture document and diagram source.
- [ ] Pin and verify the production Python runtime.
- [ ] Add Dockerfile and container startup instructions.
- [ ] Add Cloud Run, Firestore, Cloud Tasks, and authentication setup steps.
- [ ] Add environment-variable reference without secrets.
- [ ] Run the complete offline suite from a clean clone.
- [ ] Run a hosted smoke test against the final deployment.
- [ ] Confirm `.env`, credentials, virtual environments, and generated data are
  ignored and absent from Git history.

## Collaborative Partner Proof

- [ ] Ingest a messy project or academic document.
- [ ] Ask a consequential clarifying question with meaningful options.
- [ ] Generate a strict structured blueprint rather than plain prose.
- [ ] Persist the blueprint and execution state to Firestore.
- [ ] Capture accepted, rejected, or edited feedback.
- [ ] Show the resulting approved profile change.
- [ ] Generate a later blueprint that visibly uses that profile signal.
- [ ] Show failure handling for invalid model output or a failed job.

## Production Controls

- [ ] Derive user identity from a verified authentication token.
- [ ] Enforce project and session ownership.
- [ ] Enforce text, upload, and request-rate limits.
- [ ] Make synthesis requests idempotent.
- [ ] Authenticate Cloud Tasks to the private worker.
- [ ] Configure Cloud Run maximum instances and budget alerts.
- [ ] Verify logs exclude source text, chat text, profile values, feedback, and
  generated blueprint content.
- [ ] Document data retention and deletion behavior.

## Devpost Submission

- [ ] Hosted project URL.
- [ ] Public repository URL, or grant the required private-repository access.
- [ ] English project summary and value proposition.
- [ ] Features and functionality description.
- [ ] Technology and Google Cloud services description.
- [ ] Data-source and third-party integration disclosure.
- [ ] Findings and learning summary.
- [ ] Architecture diagram uploaded in a judge-readable format.
- [ ] Public YouTube or Vimeo demo URL.
- [ ] Confirm the video is four minutes or shorter.
- [ ] Confirm the video contains no unlicensed logos, music, footage, or other
  third-party material.

## Four-Minute Demo Runbook

- [ ] `0:00-0:25` — State the user friction and value proposition.
- [ ] `0:25-0:55` — Load a messy rubric, notes file, or PDF.
- [ ] `0:55-1:20` — Show Agent_Col ask and receive one critical clarification.
- [ ] `1:20-1:50` — Start synthesis and show the job-state transition.
- [ ] `1:50-2:30` — Inspect the generated structured blueprint.
- [ ] `2:30-3:05` — Reject or edit one recommendation and show the profile
  signal change.
- [ ] `3:05-3:30` — Show a later result adapting to that signal.
- [ ] `3:30-3:50` — Show Firestore and Cloud Run execution evidence.
- [ ] `3:50-4:00` — Show the hosted URL and close with the value proposition.

## Optional Bonus Work

- [ ] Publish a public build article or video with the required hackathon
  disclosure.
- [ ] Publish a social post using `#AllThingsAgenticHackathon`.
- [ ] Add another eligible Google AI model only if the core judged workflow is
  already stable and polished.

Optional bonus work must not displace reliability, feedback adaptation,
deployment evidence, or demo quality.
