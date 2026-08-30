# Agent Col Submission Checklist

Last reconciled: August 30, 2026.

This checklist is based on the official All Things Agentic Hackathon Devpost
rules and FAQ reviewed on August 30, 2026. Current source, tests,
`docs/repo-map.md`, `docs/architecture.md`, and `docs/current-state.md` are the
authority for repository evidence. Legacy documentation is historical
provenance, not a source of active requirements.

Status key:

- Satisfied: repository evidence exists.
- Needs final manual verification: must be checked against Devpost, the hosted
  deployment, demo video, or final submission form.
- Still outstanding: not done in the repository or not yet evidenced.
- Not applicable: not required for this project/submission path.

## Devpost Submission Requirements

| Requirement | Status | Evidence or next check |
| --- | --- | --- |
| Submit during the official window ending August 31, 2026 at 5:00 PM PT | Needs final manual verification | Submit on Devpost before the deadline. |
| Select exactly one category | Satisfied | README and current docs target Collaborative Partner. Confirm the same selection in Devpost. |
| Use Gemini 3.5 or newer through Gemini API or Vertex AI | Satisfied | Source uses `gemini-3.6-flash` through Vertex AI / Google GenAI SDK. |
| Use at least one Google agent framework | Satisfied | Source uses Google ADK and Google GenAI SDK. |
| Use at least one Google Cloud infrastructure service | Satisfied | Source/docs use Cloud Run and Firestore. |
| Provide repository URL | Needs final manual verification | Use the GitHub repository URL. If private, grant Devpost/Google judge access. |
| README includes spin-up instructions | Satisfied | `README.md` includes local setup and Cloud Run deployment steps. |
| Include architecture diagram | Satisfied | `README.md` and `docs/architecture.md` include Mermaid architecture diagrams. |
| Include hosted project URL if available | Needs final manual verification | README documents the Cloud Run URL; re-check live access before submission. |
| Include text description with features, technologies, data sources, findings, and learnings | Needs final manual verification | Repository docs contain source material; final Devpost text still needs manual entry. |
| Include demo video | Still outstanding | Record and upload a public YouTube or Vimeo video. |
| Keep demo video at or under 4 minutes | Still outstanding | Verify after recording. |
| Demo video shows the problem, value proposition, and app in action | Still outstanding | Include Collaborative Partner workflow proof. |
| Demo video proves backend runs on Google Cloud | Still outstanding | Show Cloud Run dashboard/logs, Vertex logs, or the `.run.app` URL during the demo. |
| Submission materials are in English or have English subtitles | Needs final manual verification | Verify final Devpost text and video. |
| Project remains accessible through judging window | Needs final manual verification | Freeze judged commit, hosted build, video, repo access, and instructions. |

## Repository Evidence

| Evidence item | Status | Location |
| --- | --- | --- |
| Project description and Collaborative Partner positioning | Satisfied | `README.md`, `docs/current-state.md` |
| Implemented feature list and limitations | Satisfied | `README.md`, `docs/current-state.md` |
| Source-derived architecture and trust boundaries | Satisfied | `docs/architecture.md`, `docs/repo-map.md` |
| Google technologies list | Satisfied | `README.md`, `docs/architecture.md` |
| Local setup and run instructions | Satisfied | `README.md`, `docs/development/local-setup.md` |
| Cloud Run deployment instructions | Satisfied | `README.md`, `docs/deployment/google-cloud-run-deployment-instructions.md` |
| Testing commands | Satisfied | `README.md`, `docs/development/testing.md` |
| License and attribution | Satisfied | `LICENSE`, `NOTICE`, `README.md` |
| Historical docs separated from current authority | Satisfied | `docs/legacy/`, `docs/notes/`, `docs/README.md` |

## Hosted And Demo Verification

| Check | Status | Required final evidence |
| --- | --- | --- |
| Cloud Run URL loads `/workspace` | Needs final manual verification | Browser or curl proof against the final hosted URL. |
| Google OIDC login works on hosted build | Needs final manual verification | Browser proof after final OAuth origin/state check. |
| `/api/auth/session` rejects unauthenticated access in Google OIDC mode | Needs final manual verification | Hosted curl or browser-network proof. |
| Representative chat turn works on hosted build | Needs final manual verification | Hosted browser proof with model response and receipts. |
| Ordinary chat streams through `/api/chat/stream` | Needs final manual verification | Hosted browser proof if streaming is shown in demo. |
| Structured decisions use `/api/chat` | Needs final manual verification | Memory, note, continuity, or artifact-feedback decision proof. |
| Memory proposal, clarification, approval, or rejection works | Needs final manual verification | Demo or screenshots with receipts. |
| Collaborative note proposal/decision/lifecycle works | Needs final manual verification | Demo or screenshots with note events. |
| Continuity retrieval or ambiguity-choice behavior works | Needs final manual verification | Demo or screenshots with continuity receipts/choices. |
| Routed specialist flow works | Needs final manual verification | Demo or screenshots with Research, Source, Computation, or Requirements receipt. |
| Artifact creation/detail/lifecycle/versioning/feedback works | Needs final manual verification | Demo or screenshots for the chosen artifact workflow. |
| Hosted logs are submission-safe | Needs final manual verification | Inspect Cloud Run logs around final demo window. |
| Cloud Run env/runtime settings match final docs | Needs final manual verification | Final Cloud Run settings screenshot or CLI output. |

## Optional Contributions

| Optional item | Status | Notes |
| --- | --- | --- |
| Public build article/blog/podcast/video | Still outstanding | Optional bonus only. |
| Public social post with required hashtag | Still outstanding | Optional bonus only. |
| Additional Google AI model such as Gemma, Veo, or Lyria | Not applicable | Current implementation uses Gemini only. Do not claim this bonus. |

## Post-Submission Technical Debt

These are not required for the current submission unless the demo claims them:

- Distributed rate limiting.
- Indexed pagination/query expansion.
- Broader preference extraction beyond explicit concise/shorter feedback.
- Durable asynchronous/background execution.
- Blueprint/generic artifact lifecycle parity beyond current implemented
  surfaces.
- Cleanup of compatibility, tests-only, live-check-only, and retained legacy
  source after the freeze.
- Deeper retention, deletion, privacy, and operational hardening.
