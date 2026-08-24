# Frontend notes

This file captures user-facing frontend concerns and requests that should be
kept visible during Phase 4A workspace development. These notes are not a
source of implementation authority by themselves; approved pass plans remain
the implementation boundary.

## 2026-08-24 workspace usability notes

- Avoid blind, open-ended manual testing. Manual test targets should be
  concrete, bounded, and tied to specific UI behavior.
- The center chat interface must be independently scrollable and must auto
  scroll to new responses while still allowing the user to scroll back through
  conversation history.
- Scrolling the center chat must not scroll either drawer.
- The right-side Work review drawer should be user-facing `Artifacts`.
- The Artifacts drawer must be independently scrollable.
- The Artifacts drawer should have a hard border line between itself and the
  chat area, matching the left drawer boundary.
- The Artifacts drawer must be hideable/showable and expandable to a wide
  document-reading mode, approximately 80 percent of the application window
  real estate when expanded.
- Expanded Artifacts text must reflow elegantly to the expanded width. Text
  must not remain constrained to the skinny drawer width, overflow borders, or
  truncate large readable content unnecessarily.
- The left drawer Work, Memory, and future Chats sections should have smaller
  controls. Expand, collapse, and refresh buttons should be closer to the
  small Hide/Show button size.
- The left drawer should use one drawer-level refresh control that refreshes
  all left drawer data instead of separate large refresh buttons per section.
- The left drawer must be independently scrollable without moving the center
  chat or the Artifacts drawer.
- Work, Memory, and Chats sections should collapse to section cards and expand
  their contents/subcards.
- Expandable drawers and cards should be collapsed by default, not expanded by
  default.
- The Memory section should order its subcategories as Pending proposals first,
  Active preferences second, and Recent memories third.
- The left drawer information architecture needs a cleanup pass after core
  wiring is complete so Work, Memory, and Chats feel human-facing rather than
  implementation-shaped.
- Hiding either drawer must never hide, move offscreen, or make unusable the
  center chat composer.
- Replace the user-facing `Activity` section with `Chats`.
- The product should store and expose chat sessions, not a non-interactive log
  of every low-level interaction.
- Chat session history should be human-facing and navigable.
- User-facing lists should avoid exposing large machine IDs as primary labels.
  IDs may remain available as secondary details, copyable metadata, or debug
  information, but humans should primarily see readable names, titles, dates,
  statuses, and concise summaries.
- Artifact creation language should be broader than only “create a structured
  blueprint artifact.” The user should be able to ask for a `blueprint`,
  `artifact`, `deliverable`, `txt file`, `markdown`, `pdf`, or `json` when
  requesting downloadable artifacts.
- Agent Col should support conversational artifact creation from the current
  conversation when sufficient prior chat content exists, instead of requiring
  the user to paste explicit source text every time.
- The frontend should remain focused on finishing backend-to-frontend wiring
  before excessive visual polish.
- Polish issues should be tracked without derailing completion of core
  functional wiring.
