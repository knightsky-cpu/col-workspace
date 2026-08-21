import asyncio
from dataclasses import dataclass
import json
import logging
from uuid import uuid4

from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from memory_proposals import ProposalTurnLease
from memory_proposal_tool import (
    PendingMemoryProposalToolResponse,
    parse_memory_proposal_tool_response,
)
from schemas import (
    AgentActionReceipt,
    ArtifactReference,
    CitationReference,
    MemoryProposalReceipt,
)
from supervisor import SUPERVISOR_APP_NAME


logger = logging.getLogger(__name__)
SUPERVISOR_MAX_LLM_CALLS = 4
SUPERVISOR_TIMEOUT_SECONDS = 90


class SupervisorRuntimeError(RuntimeError):
    """Raised when Agent_Col cannot produce a valid final response."""

    def __init__(
        self,
        message: str,
        *,
        actions: tuple[AgentActionReceipt, ...] = (),
        memory_proposals: tuple[MemoryProposalReceipt, ...] = (),
    ) -> None:
        super().__init__(message)
        self.actions = actions
        self.memory_proposals = memory_proposals


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
    turn_lease: ProposalTurnLease | None = None
    precompleted_actions: tuple[AgentActionReceipt, ...] = ()
    precompleted_memory_proposals: tuple[MemoryProposalReceipt, ...] = ()


@dataclass(frozen=True)
class SupervisorTurnResult:
    response: str
    actions: tuple[AgentActionReceipt, ...] = ()
    artifacts: tuple[ArtifactReference, ...] = ()
    citations: tuple[CitationReference, ...] = ()
    memory_proposals: tuple[MemoryProposalReceipt, ...] = ()


class SupervisorRuntime:
    def __init__(self, *, runner: object, session_service: object) -> None:
        self._runner = runner
        self._session_service = session_service

    @classmethod
    def from_app(cls, app: object) -> "SupervisorRuntime":
        sessions = InMemorySessionService()
        return cls(
            runner=Runner(app=app, session_service=sessions),
            session_service=sessions,
        )

    async def run_turn(
        self,
        context: SupervisorTurnContext,
    ) -> SupervisorTurnResult:
        invocation_session_id = uuid4().hex
        session_created = False
        final_responses: list[str] = []
        actions = list(context.precompleted_actions)
        memory_proposals = list(context.precompleted_memory_proposals)
        self._validate_proposal_effects(actions, memory_proposals)
        try:
            async with asyncio.timeout(SUPERVISOR_TIMEOUT_SECONDS):
                session_state: dict[str, object] = {
                    "project_id": context.project_id,
                    "session_id": context.session_id,
                    "user_id": context.user_id,
                }
                if context.source_message_id is not None:
                    session_state.update(
                        {
                            "memory_user_id": context.user_id,
                            "memory_session_id": context.session_id,
                            "memory_source_message_id": (
                                context.source_message_id
                            ),
                            "memory_source_message_text": context.message,
                            "memory_decision_present": (
                                context.memory_decision_present
                            ),
                        }
                    )
                    if context.turn_lease is not None:
                        session_state.update(
                            {
                                "memory_turn_id": context.turn_lease.turn_id,
                                "memory_turn_owner_token": (
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
                )
                if operational_context is not None:
                    model_input_context.append(operational_context)
                config = RunConfig(
                    max_llm_calls=SUPERVISOR_MAX_LLM_CALLS,
                    model_input_context=model_input_context,
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
                    for function_response in event.get_function_responses():
                        if function_response.name != "propose_memory_signal":
                            continue
                        parsed = parse_memory_proposal_tool_response(
                            function_response.response
                        )
                        if isinstance(
                            parsed,
                            PendingMemoryProposalToolResponse,
                        ):
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
                                )
                    if event.is_final_response():
                        text = self._extract_text(event)
                        if text:
                            final_responses.append(text)
                if len(final_responses) != 1:
                    raise SupervisorRuntimeError(
                        "Agent_Col did not produce exactly one final response.",
                        actions=tuple(actions),
                        memory_proposals=tuple(memory_proposals),
                    )
                return SupervisorTurnResult(
                    response=final_responses[0],
                    actions=tuple(actions),
                    memory_proposals=tuple(memory_proposals),
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
            ) from exc
        finally:
            if session_created:
                await self._session_service.delete_session(
                    app_name=SUPERVISOR_APP_NAME,
                    user_id=context.user_id,
                    session_id=invocation_session_id,
                )

    @staticmethod
    def _validate_proposal_effects(
        actions: list[AgentActionReceipt],
        memory_proposals: list[MemoryProposalReceipt],
    ) -> None:
        proposal_actions = [
            action
            for action in actions
            if action.action_name == "propose_memory_signal"
        ]
        if (
            len(memory_proposals) > 1
            or bool(proposal_actions) != bool(memory_proposals)
            or (memory_proposals and len(proposal_actions) != 1)
        ):
            raise SupervisorRuntimeError(
                "Agent_Col received invalid precompleted proposal effects."
            )

    @staticmethod
    def _precompleted_effect_context(
        actions: list[AgentActionReceipt],
        memory_proposals: list[MemoryProposalReceipt],
    ) -> types.Content | None:
        if not actions:
            return None
        payload = {
            "actions": [
                action.model_dump(mode="json") for action in actions
            ],
            "memory_proposals": [
                proposal.model_dump(mode="json")
                for proposal in memory_proposals
            ],
        }
        text = (
            "The following application actions already completed for this "
            "logical turn. Do not claim rollback or repeat them. If a memory "
            "proposal is present, do not call propose_memory_signal again; "
            "tell the user it remains pending and ask them to approve or "
            "reject it.\n"
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
        ).strip()
