import asyncio
from dataclasses import dataclass
import logging
from uuid import uuid4

from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from supervisor import SUPERVISOR_APP_NAME


logger = logging.getLogger(__name__)
SUPERVISOR_MAX_LLM_CALLS = 4
SUPERVISOR_TIMEOUT_SECONDS = 90


class SupervisorRuntimeError(RuntimeError):
    """Raised when Agent_Col cannot produce a valid final response."""


class SupervisorTimeoutError(SupervisorRuntimeError):
    """Raised when an Agent_Col turn exceeds its deadline."""


@dataclass(frozen=True)
class SupervisorTurnContext:
    project_id: str
    session_id: str
    user_id: str
    message: str
    model_input_context: tuple[types.Content, ...] = ()


@dataclass(frozen=True)
class SupervisorTurnResult:
    response: str


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
        try:
            async with asyncio.timeout(SUPERVISOR_TIMEOUT_SECONDS):
                await self._session_service.create_session(
                    app_name=SUPERVISOR_APP_NAME,
                    user_id=context.user_id,
                    session_id=invocation_session_id,
                    state={
                        "project_id": context.project_id,
                        "session_id": context.session_id,
                        "user_id": context.user_id,
                    },
                )
                session_created = True
                config = RunConfig(
                    max_llm_calls=SUPERVISOR_MAX_LLM_CALLS,
                    model_input_context=list(context.model_input_context),
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
                    if event.is_final_response():
                        text = self._extract_text(event)
                        if text:
                            final_responses.append(text)
                if len(final_responses) != 1:
                    raise SupervisorRuntimeError(
                        "Agent_Col did not produce exactly one final response."
                    )
                return SupervisorTurnResult(response=final_responses[0])
        except TimeoutError as exc:
            logger.error(
                "Agent_Col invocation failed (%s).",
                type(exc).__name__,
            )
            raise SupervisorTimeoutError(
                "Agent_Col invocation timed out."
            ) from exc
        except SupervisorRuntimeError:
            raise
        except Exception as exc:
            logger.error(
                "Agent_Col invocation failed (%s).",
                type(exc).__name__,
            )
            raise SupervisorRuntimeError(
                "Agent_Col invocation failed."
            ) from exc
        finally:
            if session_created:
                await self._session_service.delete_session(
                    app_name=SUPERVISOR_APP_NAME,
                    user_id=context.user_id,
                    session_id=invocation_session_id,
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
