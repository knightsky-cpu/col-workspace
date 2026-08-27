# Phase 2 Workspace Notes Closure Evidence

## Status

Phase 2 was manually accepted on August 26, 2026 after live Google OIDC
verification and accepted correction checkpoint
`624c6bbf2e65112655e63624b843387bcbbfb81c`.

This document reconciles the accepted Phase 2 behavior against
[`superpowers/plans/2026-08-25-winning-core-phase-2-workspace-notes.md`](superpowers/plans/2026-08-25-winning-core-phase-2-workspace-notes.md),
especially Pass 2H.

## Source-backed implementation

- Workspace notes are stored as governed collaborative-note proposals, active
  projections, events, and lifecycle state in Firestore.
- `POST /api/chat` is the only chat-authorized write path for note proposals,
  note approval/rejection decisions, and continuity selections.
- Notes have dedicated user/project routes for list, detail, correction,
  archive, restore, and deletion.
- The browser workspace has a left-drawer Notes surface separate from Memory.
- Pending proposals are browser-visible and require explicit approval before
  becoming active.
- Active notes can be inspected, corrected, archived, restored, and deleted.
- Continuity receipts distinguish workspace notes from prior chats.
- Ambiguous note or chat matches return source choices without note bodies or
  prior-chat transcript bodies.
- Prior-chat continuity is deterministic and receipt-backed. It searches
  bounded persisted chat sessions for explicit chat-history intent using local
  terms plus up to three sanitized model-expanded related terms.

## Live evidence sequence

1. Workspace note proposal creation was verified. A wording boundary was
   observed: prompts that looked like password/key policy could be rejected by
   the sensitive-storage gate, while explicitly workspace-scoped generator
   script requirements produced a pending workspace note. This boundary was
   accepted and not loosened.
2. Approval and active note inspection were verified in the Notes drawer.
3. Cross-session active note retrieval was verified with `Used note` receipts.
4. Prior-chat retrieval was initially insufficient, then implemented as
   deterministic receipt-backed search across bounded recent sessions. Live
   retest verified `Used prior chat` receipts.
5. Ambiguous prior-chat choices were verified to appear without body leakage.
   A 422 selection failure was found and corrected by bounding the selected
   chat detail preview before schema construction.
6. Note correction was verified. A stale selected-detail refresh issue was
   found and corrected in the frontend state refresh behavior.
7. Archive, restore, and delete were verified. A stale expanded-card issue
   after archive/restore was found and corrected.
8. Rejected proposals were verified not to become active notes.
9. Post-effect failure and exact retry behavior were verified as truthful and
   nonduplicating for the Phase 2 note/continuity path.
10. Cross-workspace lookup was verified to avoid carrying workspace notes into
    another workspace. The alternate workspace returned unavailable/bounded
    behavior without disclosing the original workspace note.

## Committed screenshot evidence

- `scrnshot-evidence/phase-2e-manual-blocked-no-note-surface-*.png`
- `scrnshot-evidence/phase-2g-manual-*.png`
- `scrnshot-evidence/phase-2g-correction-refresh-*.png`
- `scrnshot-evidence/phase-2g-note-lifecycle-refresh-*.png`
- `scrnshot-evidence/phase-2g-note-lifecycle-refresh-fix-*.png`
- `scrnshot-evidence/phase-2h-live-failure-*.png`
- `scrnshot-evidence/phase-2h-prior-chat-choice-fix-*.png`

The committed screenshots are bounded manual evidence. They intentionally do
not include tokens, raw Google ID tokens, credentials, or private account
secrets.

## Corrections made during closure

- Added the Notes drawer surface required to manually verify Phase 2E.
- Cleared stale pending proposals after note approval/rejection events.
- Refreshed selected active-note detail after correction approval.
- Cleared selected note detail when archive/restore moves the note out of the
  current list filter.
- Added deterministic prior-chat retrieval beyond only the immediately previous
  chat, with bounded keyword search and sanitized model term expansion.
- Fixed selected prior-chat ambiguity choices so long prior model replies do
  not produce `422 Continuity request is invalid`.
- Corrected ambiguous prior-chat wording so it says prior chats rather than
  saved workspace notes.

## Remaining boundaries

- Intentional Phase 2 boundary: Phase 2 does not implement a general
  unrestricted chat-history search engine. It performs bounded receipt-backed
  retrieval over recent persisted sessions.
- Intentional Phase 2 boundary: Phase 2 does not loosen the memory/note
  sensitive-storage gate for password, key, credential, address, or other
  unsafe-storage-looking prompts.
- Product scope: Agent Col remains a single-user collaborative agent. Shared
  multi-user workspace membership is not a Phase 2 gap because it was not an
  approved product requirement.
- Useful deferred addition: account-level deletion and broader
  collaboration-history retention controls beyond bounded memory/note deletion.
- Useful deferred addition: automatic sensitive-data detection or redaction for
  raw persisted chat messages.
- Phase 2 does not create durable asynchronous artifact work. That is Phase 3.
- Phase 2 does not replace profile Memory. Workspace Notes remain separate from
  durable profile preferences.

## Accepted checkpoint

Accepted correction checkpoint:

```bash
git show --stat --oneline 624c6bbf2e65112655e63624b843387bcbbfb81c
```

Rollback to the checkpoint before this accepted Phase 2H chat-continuity
correction:

```bash
git reset --hard ee12ca6c9fa1e93ace160d70a1113d93015d3838
```
