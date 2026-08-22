"""Isolated provider lifecycle for the bounded Computational Expert."""

import asyncio
import logging
from uuid import uuid4

from google.adk.agents.run_config import RunConfig
from google.adk.apps import App
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import NodeTimeoutError
from google.genai import types

from computational_expert import (
    COMPUTATIONAL_EXPERT_APP_NAME,
    ComputationExpertInput,
    ComputationExpertResult,
    create_computational_expert_app,
    normalize_computation_events,
)
from expert_contracts import ExpertStatus
from vertex_config import VertexAISettings


COMPUTATIONAL_EXPERT_SERVICE_USER_ID = "computational_expert_service"
COMPUTATIONAL_EXPERT_MAX_LLM_CALLS = 2
COMPUTATIONAL_EXPERT_SERVICE_TIMEOUT_SECONDS = 60.0

logger = logging.getLogger(__name__)


class ComputationalExpertServiceError(RuntimeError):
    """Safe failure raised when computation cannot be trusted."""

    def __init__(self, status: ExpertStatus) -> None:
        self.status = status
        super().__init__("Computational Expert execution failed.")


class ComputationalExpertService:
    """Run the Computational Expert in one temporary invocation session."""

    def __init__(
        self,
        *,
        app: App,
        runner: object,
        session_service: object,
        timeout_seconds: float = COMPUTATIONAL_EXPERT_SERVICE_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self._app = app
        self._runner = runner
        self._session_service = session_service
        self._timeout_seconds = timeout_seconds

    @property
    def app(self) -> App:
        return self._app

    @classmethod
    def from_vertex_settings(
        cls,
        vertex_settings: VertexAISettings,
    ) -> "ComputationalExpertService":
        app = create_computational_expert_app(vertex_settings)
        sessions = InMemorySessionService()
        return cls(
            app=app,
            runner=Runner(app=app, session_service=sessions),
            session_service=sessions,
        )

    async def compute(
        self,
        request: ComputationExpertInput,
    ) -> ComputationExpertResult:
        invocation_session_id = uuid4().hex
        session_kwargs = {
            "app_name": COMPUTATIONAL_EXPERT_APP_NAME,
            "user_id": COMPUTATIONAL_EXPERT_SERVICE_USER_ID,
            "session_id": invocation_session_id,
        }
        session_created = False
        events: list[Event] = []
        try:
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    await self._session_service.create_session(
                        **session_kwargs
                    )
                    session_created = True
                    message = types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text=request.model_dump_json()
                            )
                        ],
                    )
                    async for event in self._runner.run_async(
                        user_id=COMPUTATIONAL_EXPERT_SERVICE_USER_ID,
                        session_id=invocation_session_id,
                        new_message=message,
                        run_config=RunConfig(
                            max_llm_calls=COMPUTATIONAL_EXPERT_MAX_LLM_CALLS
                        ),
                    ):
                        events.append(event)
                    result = normalize_computation_events(
                        request, tuple(events)
                    )
                    if result.status is not ExpertStatus.COMPLETED:
                        raise ComputationalExpertServiceError(result.status)
                    return result
            except ComputationalExpertServiceError:
                raise
            except (TimeoutError, NodeTimeoutError) as exc:
                logger.error(
                    "Computational Expert invocation failed (%s).",
                    type(exc).__name__,
                )
                raise ComputationalExpertServiceError(
                    ExpertStatus.TIMED_OUT
                ) from exc
            except Exception as exc:
                logger.error(
                    "Computational Expert invocation failed (%s).",
                    type(exc).__name__,
                )
                raise ComputationalExpertServiceError(
                    ExpertStatus.UNAVAILABLE
                ) from exc
        finally:
            if session_created:
                await self._session_service.delete_session(**session_kwargs)
