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
- The left drawer, center chat, and Artifacts drawer should behave as
  independent same-layer application surfaces. Resizing, hiding, expanding, or
  scrolling one surface should not push, scroll, or otherwise corrupt the other
  two surfaces.
- Replace the user-facing `Activity` section with `Chats`.
- The product should store and expose chat sessions, not a non-interactive log
  of every low-level interaction.
- Chat session history should be human-facing and navigable.
- Chat session history names should be concise. Cards should use a short
  phrase that generally describes the chat or the first prompt, not a long
  paragraph-like preview that becomes hard to scan as history grows.
- Future chat history controls should let users rename, delete, and archive
  chat sessions from the UI.
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
- A request such as “create a blueprint for a simple Pomodoro timer” should not
  create avoidable friction. If the user asks for a simple/common artifact, the
  system should either produce a bounded simple version from safe ordinary
  assumptions or intentionally route to research/source in a separately
  approved capability flow, rather than repeatedly asking for specifications.
- Users should be able to speak to Agent Col naturally without needing a prompt
  guide or rigid command language. The collaboration layer should feel like
  working with a capable colleague: ordinary requests should be interpreted
  flexibly, missing details should be inferred when safe and low-risk, and
  clarification should be reserved for materially ambiguous or unsafe cases.
- Users need a clear way to inspect, modify, delete, add, approve, reject, and
  correct memory/preferences from the UI. Agent Col should also be able to
  honor explicit basic memory lifecycle requests in conversation when the
  underlying governed-memory contract supports the action. If explicit memory
  deletion or correction fails or has no visible interaction surface, that is
  user-facing friction.
- The frontend should remain focused on finishing backend-to-frontend wiring
  before excessive visual polish.
- Polish issues should be tracked without derailing completion of core
  functional wiring.
- Pass proposals should prioritize baseline application mechanics and
  functionality before conversational-friction or cosmetic polish work. Core
  controls still needing functional closure include artifact interaction,
  memory lifecycle controls, chat session controls, authentication/ownership,
  and any remaining backend-to-frontend contract wiring.
- Memory-request wording should be normalized in a later pass. Users should not have to know the exact trigger word `remember`; explicit requests like `save to memory`, `store this preference`, or `keep this preference` should route to the same governed memory proposal flow when policy allows it.
- User-facing names for memory, Work, Artifacts, and Chats should use human
  language conventions instead of source-code or database conventions. For
  example, show `Preferred name`, not `preferred_name`, and avoid making long
  signal, artifact, or session identifiers primary visible labels. Internal
  field names and storage identifiers can confuse users and may leak useful
  implementation detail to attackers. If identifiers are needed, expose them
  only as secondary metadata or explicit copy/debug controls.
- Authentication work should separate the verified identity boundary from
  project ownership. The workspace should not expose raw Google ID token entry.
  Authenticated mode should show Google-controlled sign-in first, verify the
  returned token with the backend, then use the backend-derived user identity
  for requests. The existing user/session/project prompt context remains a
  secondary validation and scoping layer, not proof of identity. The product
  still needs server-side project/session/artifact ownership records.
