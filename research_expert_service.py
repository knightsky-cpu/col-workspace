import asyncio
import logging
from uuid import uuid4

from google import genai
from google.adk.agents.run_config import RunConfig
from google.adk.apps import App
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import NodeTimeoutError, Workflow
from google.genai import types
from pydantic import ValidationError

from expert_contracts import ExpertStatus
from research_expert import (
    RESEARCH_EXPERT_MODEL_NAME,
    RESEARCH_EXPERT_TIMEOUT_SECONDS,
    ResearchExpertInput,
    ResearchInvalidOutputReason,
    ResearchExpertResult,
    create_research_expert,
    diagnose_grounded_research_text,
    diagnose_research_event,
)
from vertex_config import VertexAISettings


RESEARCH_EXPERT_APP_NAME = "agent_col_research"
RESEARCH_EXPERT_WORKFLOW_NAME = "research_workflow"
RESEARCH_EXPERT_SERVICE_USER_ID = "research_service"
RESEARCH_EXPERT_MAX_LLM_CALLS = 2


logger = logging.getLogger(__name__)


class ResearchExpertServiceError(RuntimeError):
    """Safe failure raised when isolated Research cannot be trusted."""

    def __init__(
        self,
        status: ExpertStatus,
        *,
        invalid_output_reason: ResearchInvalidOutputReason | None = None,
    ) -> None:
        self.status = status
        self.invalid_output_reason = invalid_output_reason
        super().__init__("Research Expert execution failed.")


class ResearchExpertService:
    """Run the bounded Research Expert in an isolated ADK workflow."""

    def __init__(
        self,
        *,
        app: App,
        runner: object,
        session_service: object,
        direct_client: object | None = None,
        timeout_seconds: float = RESEARCH_EXPERT_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self._app = app
        self._runner = runner
        self._session_service = session_service
        self._direct_client = direct_client
        self._timeout_seconds = timeout_seconds

    @property
    def app(self) -> App:
        """Return the ADK application topology owned by this service."""
        return self._app

    @property
    def direct_client(self) -> object | None:
        """Return the direct Gen AI client used for grounded Research."""
        return self._direct_client

    @classmethod
    def from_vertex_settings(
        cls,
        vertex_settings: VertexAISettings,
    ) -> "ResearchExpertService":
        """Construct an isolated one-node Research workflow."""
        research_expert = create_research_expert(
            vertex_settings=vertex_settings
        )
        workflow = Workflow(
            name=RESEARCH_EXPERT_WORKFLOW_NAME,
            edges=[("START", research_expert)],
        )
        app = App(name=RESEARCH_EXPERT_APP_NAME, root_agent=workflow)
        sessions = InMemorySessionService()
        return cls(
            app=app,
            runner=Runner(app=app, session_service=sessions),
            session_service=sessions,
            direct_client=genai.Client(**vertex_settings.client_kwargs()),
        )

    async def research(
        self,
        request: ResearchExpertInput,
    ) -> ResearchExpertResult:
        """Return one locally validated, provider-grounded Research result."""
        if self._direct_client is not None:
            return await self._research_direct(request)
        invocation_session_id = uuid4().hex
        session_kwargs = {
            "app_name": RESEARCH_EXPERT_APP_NAME,
            "user_id": RESEARCH_EXPERT_SERVICE_USER_ID,
            "session_id": invocation_session_id,
        }
        session_created = False
        try:
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    await self._session_service.create_session(
                        **session_kwargs
                    )
                    session_created = True
                    return await self._run_invocation(
                        request=request,
                        invocation_session_id=invocation_session_id,
                    )
            except ResearchExpertServiceError:
                raise
            except ValidationError as exc:
                self._log_failure(exc)
                raise ResearchExpertServiceError(
                    ExpertStatus.REJECTED_INPUT
                ) from exc
            except (TimeoutError, NodeTimeoutError) as exc:
                self._log_failure(exc)
                raise ResearchExpertServiceError(
                    ExpertStatus.TIMED_OUT
                ) from exc
            except Exception as exc:
                self._log_failure(exc)
                raise ResearchExpertServiceError(
                    ExpertStatus.UNAVAILABLE
                ) from exc
        finally:
            if session_created:
                await self._session_service.delete_session(**session_kwargs)

    async def _research_direct(
        self,
        request: ResearchExpertInput,
    ) -> ResearchExpertResult:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._run_direct_invocation(request)
        except ResearchExpertServiceError:
            raise
        except ValidationError as exc:
            self._log_failure(exc)
            raise ResearchExpertServiceError(
                ExpertStatus.REJECTED_INPUT
            ) from exc
        except (TimeoutError, NodeTimeoutError) as exc:
            self._log_failure(exc)
            raise ResearchExpertServiceError(
                ExpertStatus.TIMED_OUT
            ) from exc
        except Exception as exc:
            self._log_failure(exc)
            raise ResearchExpertServiceError(
                ExpertStatus.UNAVAILABLE
            ) from exc

    async def _run_direct_invocation(
        self,
        request: ResearchExpertInput,
    ) -> ResearchExpertResult:
        final_reason: ResearchInvalidOutputReason | None = None
        for attempt_index in range(2):
            response = await self._direct_client.aio.models.generate_content(
                model=RESEARCH_EXPERT_MODEL_NAME,
                contents=_direct_research_prompt(request),
                config=types.GenerateContentConfig(
                    tools=[
                        types.Tool(google_search=types.GoogleSearch()),
                    ],
                    temperature=0.0,
                    max_output_tokens=2_048,
                ),
            )
            response_text = (
                response.text if isinstance(response.text, str) else ""
            )
            outcome = diagnose_grounded_research_text(
                response_text=response_text,
                metadata=_direct_response_grounding_metadata(response),
            )
            if outcome.result.status is ExpertStatus.COMPLETED:
                return outcome.result
            final_reason = (
                outcome.invalid_output_reason
                or ResearchInvalidOutputReason.NORMALIZED_RESULT_VALIDATION_FAILED
            )
            if attempt_index == 0 and final_reason in {
                ResearchInvalidOutputReason.MISSING_GROUNDING_METADATA,
                ResearchInvalidOutputReason.MISSING_GROUNDING_CHUNKS,
                ResearchInvalidOutputReason.MISSING_GROUNDING_SUPPORTS,
            }:
                continue
            break
        self._raise_invalid_output(
            final_reason
            or ResearchInvalidOutputReason.NORMALIZED_RESULT_VALIDATION_FAILED
        )

    async def _run_invocation(
        self,
        *,
        request: ResearchExpertInput,
        invocation_session_id: str,
    ) -> ResearchExpertResult:
        final_events: list[Event] = []
        message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=request.model_dump_json())],
        )
        async for event in self._runner.run_async(
            user_id=RESEARCH_EXPERT_SERVICE_USER_ID,
            session_id=invocation_session_id,
            new_message=message,
            run_config=RunConfig(
                max_llm_calls=RESEARCH_EXPERT_MAX_LLM_CALLS
            ),
        ):
            if (
                event.author == "research_expert"
                and event.is_final_response()
            ):
                final_events.append(event)
        if not final_events:
            self._raise_invalid_output(
                ResearchInvalidOutputReason.MISSING_FINAL_EVENT
            )
        if len(final_events) > 1:
            self._raise_invalid_output(
                ResearchInvalidOutputReason.MULTIPLE_FINAL_EVENTS
            )
        outcome = diagnose_research_event(
            final_events[0].model_copy(update={"output": None})
        )
        if outcome.result.status is not ExpertStatus.COMPLETED:
            self._raise_invalid_output(
                outcome.invalid_output_reason
                or ResearchInvalidOutputReason.NORMALIZED_RESULT_VALIDATION_FAILED
            )
        return outcome.result

    @staticmethod
    def _raise_invalid_output(
        reason: ResearchInvalidOutputReason,
    ) -> None:
        logger.warning(
            "Research Expert output rejected (%s).",
            reason.value,
        )
        raise ResearchExpertServiceError(
            ExpertStatus.INVALID_OUTPUT,
            invalid_output_reason=reason,
        )

    @staticmethod
    def _log_failure(exc: Exception) -> None:
        logger.error(
            "Research Expert invocation failed (%s).",
            type(exc).__name__,
        )


def _direct_research_prompt(request: ResearchExpertInput) -> str:
    constraints = "\n".join(f"- {constraint}" for constraint in request.constraints)
    if not constraints:
        constraints = "- None supplied."
    return (
        "Use Google Search grounding for current public web evidence.\n"
        "Answer only with factual claims supported by the returned grounding "
        "metadata.\n"
        "State uncertainty if sources disagree or are incomplete.\n"
        f"Question: {request.question}\n"
        f"Objective: {request.objective}\n"
        f"Constraints:\n{constraints}\n"
    )


def _direct_response_grounding_metadata(
    response: object,
) -> types.GroundingMetadata | None:
    candidates = tuple(getattr(response, "candidates", None) or ())
    if not candidates:
        return None
    return getattr(candidates[0], "grounding_metadata", None)
