import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
import json
import logging
import re
import time
from uuid import uuid4

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from expert_delegation import (
    ExpertDelegationBudget,
    ExpertDelegationRegistry,
)
from collaborative_note_tool import (
    PendingCollaborativeNoteToolResponse,
    parse_collaborative_note_tool_response,
)
from memory_proposals import ProposalTurnLease
from memory_proposal_tool import (
    ClarificationMemoryProposalToolResponse,
    PendingMemoryProposalToolResponse,
    QueuedMemoryProposalToolResponse,
    parse_memory_proposal_tool_response,
)
from research_expert_runtime import ResearchExpertTurnTracker
from schemas import (
    AgentActionReceipt,
    ArtifactReference,
    CitationReference,
    CollaborativeNoteEvent,
    CollaborativeNoteProposal,
    MemoryClarificationReceipt,
    QueuedActionReceipt,
    VersionedMemoryProposalReceipt,
)
from supervisor import SUPERVISOR_APP_NAME
from source_expert_runtime import SourceExpertTurnTracker


logger = logging.getLogger(__name__)
SUPERVISOR_MAX_LLM_CALLS = 4
_QUEUED_MEMORY_REPLACEMENT_TEXT = (
    "Memory work has been queued for background processing. Check the Memory "
    "UI or job reports for the final result."
)
_MEMORY_STATUS_HEADINGS = frozenset(
    {
        "memory request status",
        "memory proposal status",
        "pending memory proposal",
        "pending memory proposal status",
    }
)
_QUEUED_MEMORY_COMPLETION_CLAIM_PATTERN = re.compile(
    r"\b("
    r"submitted a pending proposal|"
    r"pending memory proposal|"
    r"memory proposal (?:has been |was )?(?:created|generated|submitted)|"
    r"proposal (?:has been |was )?(?:created|generated|submitted)|"
    r"approve or reject (?:this|the) proposal|"
    r"(?:saved|stored|remembered|recorded) (?:your|the) preference"
    r")\b",
    re.IGNORECASE,
)


def _has_queued_memory_work(
    queued_actions: list[QueuedActionReceipt] | tuple[QueuedActionReceipt, ...],
) -> bool:
    return any(
        action.action_kind == "propose_memory_signal"
        for action in queued_actions
    )


def _is_memory_status_heading(paragraph: str) -> bool:
    normalized = re.sub(r"^[#>*_\-\s`]+", "", paragraph.strip())
    normalized = re.sub(r"[*_`:\s]+$", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).lower()
    return normalized in _MEMORY_STATUS_HEADINGS


def _contains_queued_memory_completion_claim(paragraph: str) -> bool:
    normalized = paragraph.lower()
    if "memory" not in normalized and "preference" not in normalized:
        return False
    return _QUEUED_MEMORY_COMPLETION_CLAIM_PATTERN.search(paragraph) is not None


def _sanitize_queued_memory_response_text(
    text: str,
    *,
    queued_actions: list[QueuedActionReceipt],
    memory_proposals: list[VersionedMemoryProposalReceipt],
) -> str:
    if (
        not _has_queued_memory_work(queued_actions)
        or memory_proposals
        or not _contains_queued_memory_completion_claim(text)
    ):
        return text

    retained_paragraphs = []
    removed_claim = False
    for paragraph in re.split(r"\n\s*\n", text):
        if _is_memory_status_heading(paragraph):
            removed_claim = True
            continue
        if _contains_queued_memory_completion_claim(paragraph):
            removed_claim = True
            continue
        retained_paragraphs.append(paragraph)

    if removed_claim and _QUEUED_MEMORY_REPLACEMENT_TEXT not in text:
        retained_paragraphs.append(_QUEUED_MEMORY_REPLACEMENT_TEXT)
    return "\n\n".join(
        paragraph for paragraph in retained_paragraphs if paragraph.strip()
    ).strip()
SUPERVISOR_TIMEOUT_SECONDS = 90
_DURABLE_PRECOMPLETED_ACTION_NAMES = frozenset(
    {
        "synthesize_project",
        "create_artifact",
        "record_blueprint_feedback",
    }
)


class SupervisorRuntimeError(RuntimeError):
    """Raised when Agent_Col cannot produce a valid final response."""

    def __init__(
        self,
        message: str,
        *,
        actions: tuple[AgentActionReceipt, ...] = (),
        memory_proposals: tuple[VersionedMemoryProposalReceipt, ...] = (),
        memory_clarifications: tuple[MemoryClarificationReceipt, ...] = (),
        collaborative_note_proposals: tuple[
            CollaborativeNoteProposal, ...
        ] = (),
        collaborative_note_events: tuple[CollaborativeNoteEvent, ...] = (),
        queued_actions: tuple[QueuedActionReceipt, ...] = (),
    ) -> None:
        super().__init__(message)
        self.actions = actions
        self.memory_proposals = memory_proposals
        self.memory_clarifications = memory_clarifications
        self.collaborative_note_proposals = collaborative_note_proposals
        self.collaborative_note_events = collaborative_note_events
        self.queued_actions = queued_actions


class SupervisorTimeoutError(SupervisorRuntimeError):
    """Raised when an Agent_Col turn exceeds its deadline."""


@dataclass(frozen=True)
class SupervisorTurnContext:
    project_id: str
    session_id: str
    user_id: str
    message: str
    model_input_context: tuple[types.Content, ...] = ()
    source_message_id: str | None = None
    memory_decision_present: bool = False
    collaborative_note_decision_present: bool = False
    artifact_feedback_decision_present: bool = False
    turn_lease: ProposalTurnLease | None = None
    precompleted_actions: tuple[AgentActionReceipt, ...] = ()
    precompleted_memory_proposals: tuple[
        VersionedMemoryProposalReceipt, ...
    ] = ()
    precompleted_memory_clarifications: tuple[
        MemoryClarificationReceipt, ...
    ] = ()
    precompleted_collaborative_note_proposals: tuple[
        CollaborativeNoteProposal, ...
    ] = ()
    precompleted_collaborative_note_events: tuple[
        CollaborativeNoteEvent, ...
    ] = ()


@dataclass(frozen=True)
class SupervisorTurnResult:
    response: str
    actions: tuple[AgentActionReceipt, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    citations: tuple[CitationReference, ...] = ()
    memory_proposals: tuple[VersionedMemoryProposalReceipt, ...] = ()
    memory_clarifications: tuple[MemoryClarificationReceipt, ...] = ()
    collaborative_note_proposals: tuple[CollaborativeNoteProposal, ...] = ()
    collaborative_note_events: tuple[CollaborativeNoteEvent, ...] = ()
    queued_actions: tuple[QueuedActionReceipt, ...] = ()


@dataclass(frozen=True)
class SupervisorTextDelta:
    text: str


@dataclass(frozen=True)
class SupervisorTurnCompleted:
    result: SupervisorTurnResult


class _AppendOnlyTextNormalizer:
    def __init__(self) -> None:
        self._delta_text = ""
        self._snapshot_text: str | None = ""
        self._emitted = ""

    def append(self, text: str) -> str:
        if not text:
            return ""
        self._delta_text += text
        if self._snapshot_text is not None:
            if text.startswith(self._snapshot_text):
                self._snapshot_text = text
            else:
                self._snapshot_text = None
        candidates = [self._delta_text]
        if self._snapshot_text is not None:
            candidates.append(self._snapshot_text)
        return self._emit(self._common_prefix(candidates))

    def finish(self, text: str) -> str:
        return self._emit(text)

    def _emit(self, text: str) -> str:
        if not text.startswith(self._emitted):
            return ""
        delta = text[len(self._emitted) :]
        self._emitted = text
        return delta

    @staticmethod
    def _common_prefix(candidates: list[str]) -> str:
        prefix = candidates[0]
        for candidate in candidates[1:]:
            limit = min(len(prefix), len(candidate))
            index = 0
            while index < limit and prefix[index] == candidate[index]:
                index += 1
            prefix = prefix[:index]
        return prefix


class SupervisorRuntime:
    def __init__(
        self,
        *,
        runner: object,
        session_service: object,
        delegation_registry: ExpertDelegationRegistry | None = None,
    ) -> None:
        self._runner = runner
        self._session_service = session_service
        self._delegation_registry = (
            delegation_registry or ExpertDelegationRegistry()
        )

    @classmethod
    def from_app(
        cls,
        app: object,
        *,
        delegation_registry: ExpertDelegationRegistry | None = None,
    ) -> "SupervisorRuntime":
        sessions = InMemorySessionService()
        return cls(
            runner=Runner(app=app, session_service=sessions),
            session_service=sessions,
            delegation_registry=delegation_registry,
        )

    async def run_turn(
        self,
        context: SupervisorTurnContext,
    ) -> SupervisorTurnResult:
        result: SupervisorTurnResult | None = None
        async for event in self._run_turn_events(
            context,
            streaming_mode=StreamingMode.NONE,
        ):
            if isinstance(event, SupervisorTurnCompleted):
                result = event.result
        if result is None:
            raise SupervisorRuntimeError(
                "Agent_Col did not produce a completed turn."
            )
        return result

    async def stream_turn(
        self,
        context: SupervisorTurnContext,
    ) -> AsyncIterator[SupervisorTextDelta | SupervisorTurnCompleted]:
        async for event in self._run_turn_events(
            context,
            streaming_mode=StreamingMode.SSE,
        ):
            yield event

    async def _run_turn_events(
        self,
        context: SupervisorTurnContext,
        *,
        streaming_mode: StreamingMode,
    ) -> AsyncIterator[SupervisorTextDelta | SupervisorTurnCompleted]:
        invocation_session_id = uuid4().hex
        session_created = False
        final_responses: list[str] = []
        actions = list(context.precompleted_actions)
        citations: list[CitationReference] = []
        memory_proposals = list(context.precompleted_memory_proposals)
        memory_clarifications = list(
            context.precompleted_memory_clarifications
        )
        collaborative_note_proposals = list(
            context.precompleted_collaborative_note_proposals
        )
        collaborative_note_events = list(
            context.precompleted_collaborative_note_events
        )
        queued_actions: list[QueuedActionReceipt] = []
        text_normalizer = _AppendOnlyTextNormalizer()
        delegation_budget = ExpertDelegationBudget()
        delegation_token = self._delegation_registry.register_turn(
            budget=delegation_budget,
            deadline=time.monotonic() + SUPERVISOR_TIMEOUT_SECONDS,
        )
        research_tracker = ResearchExpertTurnTracker(
            budget=delegation_budget
        )
        source_tracker = SourceExpertTurnTracker()
        self._validate_memory_effects(
            actions,
            memory_proposals,
            memory_clarifications,
            collaborative_note_proposals,
            collaborative_note_events,
        )
        try:
            async with asyncio.timeout(SUPERVISOR_TIMEOUT_SECONDS):
                session_state: dict[str, object] = {
                    "project_id": context.project_id,
                    "session_id": context.session_id,
                    "user_id": context.user_id,
                    "expert_delegation_token": delegation_token,
                }
                if context.source_message_id is not None:
                    has_precompleted_durable_effect = (
                        self._has_precompleted_durable_effect(
                            actions,
                            memory_proposals,
                            memory_clarifications,
                            collaborative_note_proposals,
                            collaborative_note_events,
                        )
                    )
                    session_state.update(
                        {
                            "memory_user_id": context.user_id,
                            "memory_workspace_id": context.project_id,
                            "memory_session_id": context.session_id,
                            "memory_source_message_id": (
                                context.source_message_id
                            ),
                            "memory_source_message_text": context.message,
                            "memory_decision_present": (
                                context.memory_decision_present
                            ),
                            "artifact_feedback_decision_present": (
                                context.artifact_feedback_decision_present
                            ),
                            "note_user_id": context.user_id,
                            "note_workspace_id": context.project_id,
                            "note_session_id": context.session_id,
                            "note_source_message_id": (
                                context.source_message_id
                            ),
                            "note_source_message_text": context.message,
                            "collaborative_note_decision_present": (
                                context.collaborative_note_decision_present
                            ),
                        }
                    )
                    if has_precompleted_durable_effect:
                        session_state[
                            "governed_turn_has_precompleted_durable_effect"
                        ] = True
                    if context.turn_lease is not None:
                        session_state.update(
                            {
                                "memory_turn_id": context.turn_lease.turn_id,
                                "memory_turn_owner_token": (
                                    context.turn_lease.owner_token
                                ),
                                "note_turn_id": context.turn_lease.turn_id,
                                "note_turn_owner_token": (
                                    context.turn_lease.owner_token
                                ),
                            }
                        )
                await self._session_service.create_session(
                    app_name=SUPERVISOR_APP_NAME,
                    user_id=context.user_id,
                    session_id=invocation_session_id,
                    state=session_state,
                )
                session_created = True
                model_input_context = list(context.model_input_context)
                operational_context = self._precompleted_effect_context(
                    actions,
                    memory_proposals,
                    memory_clarifications,
                    collaborative_note_proposals,
                    collaborative_note_events,
                )
                if operational_context is not None:
                    model_input_context.append(operational_context)
                config = RunConfig(
                    max_llm_calls=SUPERVISOR_MAX_LLM_CALLS,
                    model_input_context=model_input_context,
                    streaming_mode=streaming_mode,
                )
                message = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=context.message)],
                )
                async for event in self._runner.run_async(
                    user_id=context.user_id,
                    session_id=invocation_session_id,
                    new_message=message,
                    run_config=config,
                ):
                    await research_tracker.observe(event)
                    source_tracker.observe(event)
                    for function_response in event.get_function_responses():
                        if function_response.name == "propose_collaborative_note":
                            parsed_note = parse_collaborative_note_tool_response(
                                function_response.response
                            )
                            if isinstance(
                                parsed_note,
                                PendingCollaborativeNoteToolResponse,
                            ):
                                if not collaborative_note_proposals:
                                    actions.append(parsed_note.action)
                                    collaborative_note_proposals.append(
                                        parsed_note.collaborative_note_proposal
                                    )
                                elif (
                                    [
                                        action
                                        for action in actions
                                        if action.action_name
                                        == "propose_collaborative_note"
                                    ]
                                    != [parsed_note.action]
                                    or collaborative_note_proposals
                                    != [
                                        parsed_note
                                        .collaborative_note_proposal
                                    ]
                                ):
                                    raise SupervisorRuntimeError(
                                        "Agent_Col produced conflicting "
                                        "collaborative note proposal receipts.",
                                        actions=tuple(actions),
                                        memory_proposals=tuple(
                                            memory_proposals
                                        ),
                                        memory_clarifications=tuple(
                                            memory_clarifications
                                        ),
                                        collaborative_note_proposals=tuple(
                                            collaborative_note_proposals
                                        ),
                                        collaborative_note_events=tuple(
                                            collaborative_note_events
                                        ),
                                    )
                            if memory_proposals or memory_clarifications:
                                raise SupervisorRuntimeError(
                                    "Agent_Col produced conflicting memory "
                                    "and collaborative note proposal receipts.",
                                    actions=tuple(actions),
                                    memory_proposals=tuple(memory_proposals),
                                    memory_clarifications=tuple(
                                        memory_clarifications
                                    ),
                                    collaborative_note_proposals=tuple(
                                        collaborative_note_proposals
                                    ),
                                    collaborative_note_events=tuple(
                                        collaborative_note_events
                                    ),
                                )
                            continue
                        if function_response.name != "propose_memory_signal":
                            continue
                        parsed = parse_memory_proposal_tool_response(
                            function_response.response
                        )
                        if isinstance(
                            parsed,
                            PendingMemoryProposalToolResponse,
                        ):
                            if any(
                                action.action_kind == "propose_memory_signal"
                                for action in queued_actions
                            ):
                                continue
                            if not memory_proposals:
                                actions.append(parsed.action)
                                memory_proposals.append(
                                    parsed.memory_proposal
                                )
                            elif (
                                [
                                    action
                                    for action in actions
                                    if action.action_name
                                    == "propose_memory_signal"
                                ]
                                != [parsed.action]
                                or memory_proposals
                                != [parsed.memory_proposal]
                            ):
                                raise SupervisorRuntimeError(
                                    "Agent_Col produced conflicting memory "
                                    "proposal receipts.",
                                    actions=tuple(actions),
                                    memory_proposals=tuple(memory_proposals),
                                    memory_clarifications=tuple(
                                        memory_clarifications
                                    ),
                                    collaborative_note_proposals=tuple(
                                        collaborative_note_proposals
                                    ),
                                    collaborative_note_events=tuple(
                                        collaborative_note_events
                                    ),
                                )
                        elif isinstance(
                            parsed,
                            ClarificationMemoryProposalToolResponse,
                        ):
                            if memory_proposals:
                                raise SupervisorRuntimeError(
                                    "Agent_Col produced conflicting memory "
                                    "proposal and clarification receipts.",
                                    actions=tuple(actions),
                                    memory_proposals=tuple(memory_proposals),
                                    memory_clarifications=tuple(
                                        memory_clarifications
                                    ),
                                    collaborative_note_proposals=tuple(
                                        collaborative_note_proposals
                                    ),
                                    collaborative_note_events=tuple(
                                        collaborative_note_events
                                    ),
                                )
                            if not memory_clarifications:
                                memory_clarifications.append(
                                    parsed.memory_clarification
                                )
                            elif memory_clarifications != [
                                parsed.memory_clarification
                            ]:
                                raise SupervisorRuntimeError(
                                    "Agent_Col produced conflicting memory "
                                    "clarification receipts.",
                                    actions=tuple(actions),
                                    memory_clarifications=tuple(
                                        memory_clarifications
                                    ),
                                    collaborative_note_proposals=tuple(
                                        collaborative_note_proposals
                                    ),
                                    collaborative_note_events=tuple(
                                        collaborative_note_events
                                    ),
                                )
                        elif isinstance(
                            parsed,
                            QueuedMemoryProposalToolResponse,
                        ):
                            if parsed.queued_action not in queued_actions:
                                queued_actions.append(parsed.queued_action)
                        if collaborative_note_proposals:
                            raise SupervisorRuntimeError(
                                "Agent_Col produced conflicting memory and "
                                "collaborative note proposal receipts.",
                                actions=tuple(actions),
                                memory_proposals=tuple(memory_proposals),
                                memory_clarifications=tuple(
                                    memory_clarifications
                                ),
                                collaborative_note_proposals=tuple(
                                    collaborative_note_proposals
                                ),
                                collaborative_note_events=tuple(
                                    collaborative_note_events
                                ),
                                queued_actions=tuple(queued_actions),
                            )
                    if (
                        getattr(event, "author", "Agent_Col") == "Agent_Col"
                        and event.is_final_response()
                    ):
                        text = self._extract_text(event)
                        if text:
                            text = _sanitize_queued_memory_response_text(
                                text,
                                queued_actions=queued_actions,
                                memory_proposals=memory_proposals,
                            )
                            final_responses.append(text)
                            if streaming_mode is StreamingMode.SSE:
                                delta = text_normalizer.finish(text)
                                if delta:
                                    yield SupervisorTextDelta(text=delta)
                    elif (
                        streaming_mode is StreamingMode.SSE
                        and getattr(event, "author", "Agent_Col")
                        == "Agent_Col"
                        and getattr(event, "partial", False)
                        and not event.get_function_calls()
                        and not event.get_function_responses()
                    ):
                        text = self._extract_stream_text(event)
                        delta = text_normalizer.append(text)
                        if delta:
                            yield SupervisorTextDelta(text=delta)
                research_receipts = research_tracker.finalize()
                actions.extend(research_receipts.actions)
                citations.extend(research_receipts.citations)
                source_receipts = source_tracker.finalize()
                actions.extend(source_receipts.actions)
                citations.extend(source_receipts.citations)
                if len(final_responses) != 1:
                    raise SupervisorRuntimeError(
                        "Agent_Col did not produce exactly one final response.",
                        actions=tuple(actions),
                        memory_proposals=tuple(memory_proposals),
                        memory_clarifications=tuple(memory_clarifications),
                        collaborative_note_proposals=tuple(
                            collaborative_note_proposals
                        ),
                        collaborative_note_events=tuple(
                            collaborative_note_events
                        ),
                        queued_actions=tuple(queued_actions),
                    )
                yield SupervisorTurnCompleted(
                    result=SupervisorTurnResult(
                        response=final_responses[0],
                        actions=tuple(actions),
                        citations=tuple(citations),
                        memory_proposals=tuple(memory_proposals),
                        memory_clarifications=tuple(memory_clarifications),
                        collaborative_note_proposals=tuple(
                            collaborative_note_proposals
                        ),
                        collaborative_note_events=tuple(
                            collaborative_note_events
                        ),
                        queued_actions=tuple(queued_actions),
                    )
                )
        except TimeoutError as exc:
            logger.error(
                "Agent_Col invocation failed (%s).",
                type(exc).__name__,
            )
            raise SupervisorTimeoutError(
                "Agent_Col invocation timed out.",
                actions=tuple(actions),
                memory_proposals=tuple(memory_proposals),
                memory_clarifications=tuple(memory_clarifications),
                collaborative_note_proposals=tuple(
                    collaborative_note_proposals
                ),
                collaborative_note_events=tuple(collaborative_note_events),
                queued_actions=tuple(queued_actions),
            ) from exc
        except SupervisorRuntimeError:
            raise
        except Exception as exc:
            logger.error(
                "Agent_Col invocation failed (%s).",
                type(exc).__name__,
            )
            raise SupervisorRuntimeError(
                "Agent_Col invocation failed.",
                actions=tuple(actions),
                memory_proposals=tuple(memory_proposals),
                memory_clarifications=tuple(memory_clarifications),
                queued_actions=tuple(queued_actions),
            ) from exc
        finally:
            try:
                if session_created:
                    await self._session_service.delete_session(
                        app_name=SUPERVISOR_APP_NAME,
                        user_id=context.user_id,
                        session_id=invocation_session_id,
                    )
            finally:
                self._delegation_registry.release_turn(
                    delegation_token
                )

    @staticmethod
    def _validate_memory_effects(
        actions: list[AgentActionReceipt],
        memory_proposals: list[VersionedMemoryProposalReceipt],
        memory_clarifications: list[MemoryClarificationReceipt],
        collaborative_note_proposals: list[CollaborativeNoteProposal],
        collaborative_note_events: list[CollaborativeNoteEvent],
    ) -> None:
        proposal_actions = [
            action
            for action in actions
            if action.action_name == "propose_memory_signal"
        ]
        if (
            len(memory_proposals) > 1
            or len(memory_clarifications) > 1
            or bool(memory_proposals) and bool(memory_clarifications)
            or bool(proposal_actions) != bool(memory_proposals)
            or (memory_proposals and len(proposal_actions) != 1)
        ):
            raise SupervisorRuntimeError(
                "Agent_Col received invalid precompleted proposal effects."
            )
        note_actions = [
            action
            for action in actions
            if action.action_name
            in {
                "propose_collaborative_note",
                "approve_collaborative_note",
                "reject_collaborative_note",
            }
        ]
        note_proposal_actions = [
            action
            for action in actions
            if action.action_name == "propose_collaborative_note"
        ]
        note_decision_actions = [
            action
            for action in actions
            if action.action_name
            in {"approve_collaborative_note", "reject_collaborative_note"}
        ]
        if (
            len(collaborative_note_proposals) > 1
            or len(collaborative_note_events) > 1
            or bool(collaborative_note_proposals)
            and bool(collaborative_note_events)
            or bool(note_proposal_actions) != bool(collaborative_note_proposals)
            or bool(note_decision_actions) != bool(collaborative_note_events)
            or note_proposal_actions
            and len(note_proposal_actions) != 1
            or (
                collaborative_note_events
                and len(note_decision_actions)
                != len(collaborative_note_events)
            )
        ):
            raise SupervisorRuntimeError(
                "Agent_Col received invalid precompleted note effects."
            )

    @staticmethod
    def _has_precompleted_durable_effect(
        actions: list[AgentActionReceipt],
        memory_proposals: list[VersionedMemoryProposalReceipt],
        memory_clarifications: list[MemoryClarificationReceipt],
        collaborative_note_proposals: list[CollaborativeNoteProposal],
        collaborative_note_events: list[CollaborativeNoteEvent],
    ) -> bool:
        return (
            any(
                action.action_name in _DURABLE_PRECOMPLETED_ACTION_NAMES
                for action in actions
            )
            or bool(memory_proposals)
            or bool(memory_clarifications)
            or bool(collaborative_note_proposals)
            or bool(collaborative_note_events)
        )

    @staticmethod
    def _precompleted_effect_context(
        actions: list[AgentActionReceipt],
        memory_proposals: list[VersionedMemoryProposalReceipt],
        memory_clarifications: list[MemoryClarificationReceipt],
        collaborative_note_proposals: list[CollaborativeNoteProposal],
        collaborative_note_events: list[CollaborativeNoteEvent],
    ) -> types.Content | None:
        if (
            not actions
            and not memory_clarifications
            and not collaborative_note_proposals
            and not collaborative_note_events
        ):
            return None
        payload = {
            "actions": [
                {
                    "action_name": action.action_name,
                    "status": action.status,
                }
                for action in actions
            ],
            "memory_proposals": [
                {
                    "category": proposal.category,
                    "proposed_value": proposal.proposed_value,
                }
                for proposal in memory_proposals
            ],
            "memory_clarifications": [
                {
                    "choices": [
                        choice.model_dump(mode="json")
                        for choice in clarification.choices
                    ],
                }
                for clarification in memory_clarifications
            ],
            "collaborative_note_proposals": [
                {
                    "note_kind": proposal.note_kind,
                    "title": proposal.title,
                    "body": proposal.body,
                    "status": proposal.status,
                }
                for proposal in collaborative_note_proposals
            ],
            "collaborative_note_events": [
                {
                    "event_type": event.event_type,
                    **(
                        {"note_kind": event.note_kind}
                        if event.note_kind is not None
                        else {}
                    ),
                    **(
                        {"title": event.title}
                        if event.title is not None
                        else {}
                    ),
                    **(
                        {"body": event.body}
                        if event.body is not None
                        else {}
                    ),
                    "revision": event.revision,
                }
                for event in collaborative_note_events
            ],
        }
        text = (
            "The following application actions already completed for this "
            "logical turn. Do not claim rollback or repeat them; do not call "
            "propose_collaborative_note after any precompleted action or "
            "effect in this context. If a memory proposal is present, do not "
            "call propose_memory_signal again; tell the user it remains "
            "pending and ask them to approve or reject it.\n"
            "[SERVER_VALIDATED_PRECOMPLETED_ACTIONS]\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n"
            "[/SERVER_VALIDATED_PRECOMPLETED_ACTIONS]"
        )
        return types.Content(
            role="user",
            parts=[types.Part.from_text(text=text)],
        )

    @staticmethod
    def _extract_text(event: object) -> str:
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        return "".join(
            part.text
            for part in parts
            if isinstance(getattr(part, "text", None), str)
            and not getattr(part, "thought", False)
        ).strip()

    @staticmethod
    def _extract_stream_text(event: object) -> str:
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        return "".join(
            part.text
            for part in parts
            if isinstance(getattr(part, "text", None), str)
            and not getattr(part, "thought", False)
        )
