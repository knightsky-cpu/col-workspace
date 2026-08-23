"""Bounded live HTTP evaluation for Agent_Col's complete core tool belt."""

import argparse
import asyncio
import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

from agent_col_routing_provider_v3 import AGENT_COL_ROUTING_V3_MODEL_NAME
from agent_col_numeric_projection import project_routing_numeric_candidates
from agent_col_routing import project_routing_url_candidates
from agent_col_text_projection import project_routing_text_blocks
from chat_turns import derive_chat_turn_ids
from computational_expert import COMPUTATIONAL_EXPERT_MODEL_NAME
from research_expert import RESEARCH_EXPERT_MODEL_NAME
from requirements_verification_service import (
    REQUIREMENTS_VERIFICATION_MODEL_NAME,
)
from schemas import ChatResponse
from source_expert import SOURCE_EXPERT_MODEL_NAME
from supervisor import SUPERVISOR_MODEL_NAME
from tool_belt_routing_check import (
    is_repository_dirty,
    resolve_repository_commit,
)
from vertex_config import VertexAIConfigurationError, load_vertex_ai_settings


PROJECT_ID = "agent-col"
REPORT_VERSION = "1.0"
FIXTURE_VERSION = "3.0"
ROUTING_SCHEMA_VERSION = "3.0"
_RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
_CONFLICT_DETAIL = "Idempotency key conflicts with a different chat request."


@dataclass(frozen=True, slots=True)
class LiveE2ECase:
    probe_id: str
    message: str
    expected_action: str | None
    required_projection: Literal["none", "url", "numeric", "text"]
    manual_review_required: bool = True


LIVE_E2E_CASES = (
    LiveE2ECase(
        probe_id="direct-restraint",
        message=(
            "Explain in one paragraph why an agent should avoid unnecessary "
            "tool calls. Do not use tools."
        ),
        expected_action=None,
        required_projection="none",
    ),
    LiveE2ECase(
        probe_id="clarification",
        message="Calculate the percentage change for my results.",
        expected_action=None,
        required_projection="none",
    ),
    LiveE2ECase(
        probe_id="source",
        message=(
            "Analyze this supplied public URL and explain its stated purpose "
            "using only evidence from the page: https://example.com/"
        ),
        expected_action="url_context",
        required_projection="url",
    ),
    LiveE2ECase(
        probe_id="research",
        message=(
            "Use current authoritative public evidence to identify the latest "
            "stable Python release and cite your sources."
        ),
        expected_action="google_search",
        required_projection="none",
    ),
    LiveE2ECase(
        probe_id="computation",
        message=(
            "Calculate the arithmetic mean and population standard deviation "
            "of these exact values: 12, 15, 18, 21, 24, 27. Use the "
            "Computational Expert and report both results to 4 decimal places."
        ),
        expected_action="run_computation",
        required_projection="numeric",
    ),
    LiveE2ECase(
        probe_id="requirements-verification",
        message=(
            "Compare this draft against every requirement.\n\n"
            "Requirements:\n"
            "- Include one practical example.\n"
            "- State one material limitation.\n\n"
            "Subject:\n"
            "The draft includes one practical example."
        ),
        expected_action="verify_requirements",
        required_projection="text",
    ),
)


@dataclass(frozen=True, slots=True)
class LiveIdentity:
    user_id: str
    session_id: str
    idempotency_key: str
    turn_id: str
    firestore_paths: tuple[str, str, str, str]


@dataclass(frozen=True, slots=True)
class LiveHttpObservation:
    status_code: int
    body: object


@dataclass(frozen=True, slots=True)
class ProbeEvaluation:
    outcome: Literal["pass", "semantic_failure", "inconclusive"]
    classification: str
    response: ChatResponse | None = None


class LiveE2ETransportError(RuntimeError):
    """Raised when the bounded runner cannot reach the public API."""


class LiveE2EConfigurationError(ValueError):
    """Raised when a synthetic live fixture cannot reach its boundary."""

    def __init__(self, *, probe_id: str, reason: str) -> None:
        self.probe_id = probe_id
        self.reason = reason
        super().__init__("Live end-to-end fixture configuration is invalid.")


class ChatRequester(Protocol):
    async def __call__(
        self,
        probe_id: str,
        payload: dict[str, object],
        idempotency_key: str,
    ) -> LiveHttpObservation: ...


OutputWriter = Callable[[str], None]


def validate_run_id(run_id: object) -> str:
    if not isinstance(run_id, str) or _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError(
            "run_id must be 1 through 32 lowercase letters, digits, or "
            "hyphens and must begin with a letter or digit."
        )
    return run_id


def build_live_identity(*, run_id: str, probe_id: str) -> LiveIdentity:
    validated_run_id = validate_run_id(run_id)
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", probe_id) is None:
        raise ValueError("probe_id is invalid.")
    identifier = f"m7-e2e-{validated_run_id}-{probe_id}"
    ids = derive_chat_turn_ids(identifier)
    base = f"sessions/{identifier}"
    return LiveIdentity(
        user_id=identifier,
        session_id=identifier,
        idempotency_key=identifier,
        turn_id=ids.turn_id,
        firestore_paths=(
            base,
            f"{base}/turns/{ids.turn_id}",
            f"{base}/messages/{ids.user_message_id}",
            f"{base}/messages/{ids.model_message_id}",
        ),
    )


def preflight_live_cases(cases: tuple[LiveE2ECase, ...]) -> None:
    """Validate fixture projections without making provider or HTTP calls."""
    probe_ids = tuple(case.probe_id for case in cases)
    if not cases or len(set(probe_ids)) != len(probe_ids):
        raise LiveE2EConfigurationError(
            probe_id="catalog",
            reason="invalid_probe_catalog",
        )
    for case in cases:
        if case.required_projection == "url":
            if not project_routing_url_candidates(case.message, ()):
                raise LiveE2EConfigurationError(
                    probe_id=case.probe_id,
                    reason="missing_url_candidate",
                )
        elif case.required_projection == "numeric":
            projection = project_routing_numeric_candidates(case.message)
            if (
                projection.numeric_projection_incomplete
                or not projection.candidates
            ):
                raise LiveE2EConfigurationError(
                    probe_id=case.probe_id,
                    reason="invalid_numeric_projection",
                )
        elif case.required_projection == "text":
            projection = project_routing_text_blocks(case.message)
            if (
                projection.text_projection_incomplete
                or not projection.candidates
            ):
                raise LiveE2EConfigurationError(
                    probe_id=case.probe_id,
                    reason="invalid_text_projection",
                )


async def request_live_chat(
    *,
    client: httpx.AsyncClient,
    probe_id: str,
    payload: dict[str, object],
    idempotency_key: str,
) -> LiveHttpObservation:
    """Make exactly one public HTTP request without hidden retries."""
    del probe_id
    try:
        response = await client.post(
            "/api/chat",
            headers={"Idempotency-Key": idempotency_key},
            json=payload,
        )
    except httpx.RequestError:
        raise LiveE2ETransportError("Agent_Col transport failed.") from None
    try:
        body: object = response.json()
    except (TypeError, ValueError):
        body = None
    return LiveHttpObservation(status_code=response.status_code, body=body)


def _expected_action_matches(case: LiveE2ECase, response: ChatResponse) -> bool:
    expected = case.expected_action
    if expected is None:
        return not response.actions
    return (
        len(response.actions) == 1
        and response.actions[0].action_name == expected
        and response.actions[0].status == "completed"
    )


def _source_citation_receipt_matches(
    case: LiveE2ECase,
    response: ChatResponse,
) -> bool:
    expected_urls = {
        str(candidate.url)
        for candidate in project_routing_url_candidates(case.message, ())
    }
    citation_urls = {str(citation.uri) for citation in response.citations}
    return bool(expected_urls) and expected_urls <= citation_urls


def evaluate_case(
    case: LiveE2ECase,
    observation: LiveHttpObservation,
) -> ProbeEvaluation:
    if observation.status_code in (502, 504):
        return ProbeEvaluation("inconclusive", "provider_error")
    if observation.status_code != 200:
        return ProbeEvaluation("inconclusive", "response_contract_error")
    try:
        response = ChatResponse.model_validate(observation.body)
    except (TypeError, ValueError, ValidationError):
        return ProbeEvaluation("inconclusive", "response_contract_error")

    if response.memory_proposals or response.adaptations:
        return ProbeEvaluation(
            "semantic_failure",
            "memory_boundary_failure",
            response,
        )
    if (
        case.expected_action is not None
        and not response.actions
        and not response.citations
    ):
        return ProbeEvaluation(
            "inconclusive",
            "expert_outcome_unobservable",
            response,
        )
    if not _expected_action_matches(case, response):
        return ProbeEvaluation(
            "semantic_failure",
            "missing_completed_action"
            if case.expected_action is not None
            else "unexpected_action",
            response,
        )

    if case.probe_id in {"direct-restraint", "clarification"}:
        if response.citations:
            return ProbeEvaluation(
                "semantic_failure", "unexpected_citation", response
            )
    elif case.probe_id == "source":
        if not _source_citation_receipt_matches(case, response):
            return ProbeEvaluation(
                "semantic_failure", "citation_mismatch", response
            )
    elif case.probe_id == "research":
        if not response.citations or not any(
            "python.org" in citation.label.lower()
            for citation in response.citations
        ):
            return ProbeEvaluation(
                "semantic_failure", "citation_mismatch", response
            )
    elif case.probe_id == "computation":
        if response.citations:
            return ProbeEvaluation(
                "semantic_failure", "unexpected_citation", response
            )
        if not all(
            expected in response.response for expected in ("19.5000", "5.1235")
        ):
            return ProbeEvaluation(
                "semantic_failure", "numeric_result_mismatch", response
            )
    elif case.probe_id == "requirements-verification":
        if response.citations:
            return ProbeEvaluation(
                "semantic_failure", "unexpected_citation", response
            )

    return ProbeEvaluation("pass", "pass", response)


def evaluate_replay(
    original: LiveHttpObservation,
    replay: LiveHttpObservation,
) -> ProbeEvaluation:
    if replay.status_code in (502, 504):
        return ProbeEvaluation("inconclusive", "provider_error")
    if original.status_code != 200 or replay.status_code != 200:
        return ProbeEvaluation("inconclusive", "replay_dependency_error")
    if replay.body != original.body:
        return ProbeEvaluation("semantic_failure", "idempotency_failure")
    try:
        response = ChatResponse.model_validate(replay.body)
    except (TypeError, ValueError, ValidationError):
        return ProbeEvaluation("inconclusive", "response_contract_error")
    return ProbeEvaluation("pass", "pass", response)


def evaluate_conflict(observation: LiveHttpObservation) -> ProbeEvaluation:
    if observation.status_code in (502, 504):
        return ProbeEvaluation("inconclusive", "provider_error")
    if observation.status_code != 409:
        return ProbeEvaluation("semantic_failure", "idempotency_failure")
    if not isinstance(observation.body, Mapping) or observation.body.get(
        "detail"
    ) != _CONFLICT_DETAIL:
        return ProbeEvaluation("semantic_failure", "conflict_contract_error")
    return ProbeEvaluation("pass", "pass")


def _probe_report(
    *,
    probe_id: str,
    payload: Mapping[str, object],
    identity: LiveIdentity,
    observation: LiveHttpObservation,
    evaluation: ProbeEvaluation,
    manual_review_required: bool,
) -> dict[str, object]:
    return {
        "probe_id": probe_id,
        "request": dict(payload),
        "idempotency_key": identity.idempotency_key,
        "http_status": observation.status_code,
        "outcome": evaluation.outcome,
        "classification": evaluation.classification,
        "manual_review_required": (
            manual_review_required and evaluation.outcome == "pass"
        ),
        "response": (
            evaluation.response.model_dump(mode="json")
            if evaluation.response is not None
            else observation.body
        ),
        "firestore_paths": list(identity.firestore_paths),
    }


def _metadata_line(
    probe_id: str,
    observation: LiveHttpObservation,
    evaluation: ProbeEvaluation,
    manual_review_required: bool,
) -> str:
    line = f"{probe_id} http={observation.status_code} {evaluation.classification}"
    if manual_review_required and evaluation.outcome == "pass":
        line += " manual_review_required"
    return line


async def run_bounded_live_e2e(
    *,
    run_id: str,
    request_chat: ChatRequester,
    report_path: Path,
    output: OutputWriter,
    repository_commit: str,
    repository_dirty: bool,
    configured_project: str,
    configured_location: str,
    base_url: str = "http://127.0.0.1:8000",
    now: Callable[[], datetime] | None = None,
    monotonic_values: Iterator[float] | None = None,
    cases: tuple[LiveE2ECase, ...] = LIVE_E2E_CASES,
) -> int:
    """Run the exact bounded live sample and persist its synthetic report."""
    validated_run_id = validate_run_id(run_id)
    if _COMMIT_PATTERN.fullmatch(repository_commit) is None:
        raise ValueError("repository_commit is invalid.")
    if not configured_project or configured_location != "global":
        raise ValueError("configured Vertex AI metadata is invalid.")
    if report_path.exists():
        raise ValueError("report_path must not already exist.")
    preflight_live_cases(cases)
    planned_http_requests = len(cases) + 2
    current_time = now or (lambda: datetime.now(UTC))
    times = monotonic_values
    started = next(times) if times is not None else time.monotonic()
    report_started_at = current_time().isoformat()
    output(
        " ".join(
            (
                "tool-belt-live-e2e-check",
                f"fixture={FIXTURE_VERSION}",
                f"schema={ROUTING_SCHEMA_VERSION}",
                f"commit={repository_commit}",
                f"worktree={'dirty' if repository_dirty else 'clean'}",
                "provider=vertex_ai",
                f"model={AGENT_COL_ROUTING_V3_MODEL_NAME}",
                f"planned_http_requests={planned_http_requests}",
            )
        )
    )

    probes: list[dict[str, object]] = []
    semantic_failures = 0
    inconclusive_failures = 0
    manual_review_cases = 0
    source_observation: LiveHttpObservation | None = None
    source_identity: LiveIdentity | None = None
    source_payload: dict[str, object] | None = None

    async def execute(
        *,
        probe_id: str,
        payload: dict[str, object],
        identity: LiveIdentity,
    ) -> LiveHttpObservation:
        try:
            return await request_chat(
                probe_id,
                payload,
                identity.idempotency_key,
            )
        except LiveE2ETransportError:
            return LiveHttpObservation(status_code=0, body=None)

    for case in cases:
        identity = build_live_identity(
            run_id=validated_run_id,
            probe_id=case.probe_id,
        )
        payload: dict[str, object] = {
            "project_id": PROJECT_ID,
            "session_id": identity.session_id,
            "user_id": identity.user_id,
            "message": case.message,
        }
        observation = await execute(
            probe_id=case.probe_id,
            payload=payload,
            identity=identity,
        )
        evaluation = (
            ProbeEvaluation("inconclusive", "transport_error")
            if observation.status_code == 0
            else evaluate_case(case, observation)
        )
        if evaluation.outcome == "semantic_failure":
            semantic_failures += 1
        elif evaluation.outcome == "inconclusive":
            inconclusive_failures += 1
        elif case.manual_review_required:
            manual_review_cases += 1
        output(
            _metadata_line(
                case.probe_id,
                observation,
                evaluation,
                case.manual_review_required,
            )
        )
        probes.append(
            _probe_report(
                probe_id=case.probe_id,
                payload=payload,
                identity=identity,
                observation=observation,
                evaluation=evaluation,
                manual_review_required=case.manual_review_required,
            )
        )
        if case.probe_id == "source":
            source_observation = observation
            source_identity = identity
            source_payload = payload

    if (
        source_observation is None
        or source_identity is None
        or source_payload is None
    ):
        raise RuntimeError("Source replay state was not created.")

    replay = await execute(
        probe_id="source-replay",
        payload=source_payload,
        identity=source_identity,
    )
    replay_evaluation = (
        ProbeEvaluation("inconclusive", "transport_error")
        if replay.status_code == 0
        else evaluate_replay(source_observation, replay)
    )
    if replay_evaluation.outcome == "semantic_failure":
        semantic_failures += 1
    elif replay_evaluation.outcome == "inconclusive":
        inconclusive_failures += 1
    output(
        _metadata_line(
            "source-replay", replay, replay_evaluation, False
        )
    )
    probes.append(
        _probe_report(
            probe_id="source-replay",
            payload=source_payload,
            identity=source_identity,
            observation=replay,
            evaluation=replay_evaluation,
            manual_review_required=False,
        )
    )

    conflict_payload = dict(source_payload)
    conflict_payload["message"] = (
        "This changed synthetic request must conflict with the existing key."
    )
    conflict = await execute(
        probe_id="source-conflict",
        payload=conflict_payload,
        identity=source_identity,
    )
    conflict_evaluation = (
        ProbeEvaluation("inconclusive", "transport_error")
        if conflict.status_code == 0
        else evaluate_conflict(conflict)
    )
    if conflict_evaluation.outcome == "semantic_failure":
        semantic_failures += 1
    elif conflict_evaluation.outcome == "inconclusive":
        inconclusive_failures += 1
    output(
        _metadata_line(
            "source-conflict", conflict, conflict_evaluation, False
        )
    )
    probes.append(
        _probe_report(
            probe_id="source-conflict",
            payload=conflict_payload,
            identity=source_identity,
            observation=conflict,
            evaluation=conflict_evaluation,
            manual_review_required=False,
        )
    )

    finished = next(times) if times is not None else time.monotonic()
    elapsed_ms = round((finished - started) * 1_000)
    exit_code = 2 if inconclusive_failures else (1 if semantic_failures else 0)
    report = {
        "report_version": REPORT_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "routing_schema_version": ROUTING_SCHEMA_VERSION,
        "run_id": validated_run_id,
        "started_at": report_started_at,
        "repository": {
            "commit": repository_commit,
            "worktree": "dirty" if repository_dirty else "clean",
        },
        "provider": {
            "mode": "vertex_ai",
            "project": configured_project,
            "location": configured_location,
            "provider_calls": "not_observable_at_http_boundary",
        },
        "models": {
            "router": AGENT_COL_ROUTING_V3_MODEL_NAME,
            "responder": SUPERVISOR_MODEL_NAME,
            "source": SOURCE_EXPERT_MODEL_NAME,
            "research": RESEARCH_EXPERT_MODEL_NAME,
            "computation": COMPUTATIONAL_EXPERT_MODEL_NAME,
            "requirements_verification": (
                REQUIREMENTS_VERIFICATION_MODEL_NAME
            ),
        },
        "base_url": base_url,
        "probes": probes,
        "summary": {
            "http_requests": planned_http_requests,
            "automatable_failures": semantic_failures,
            "inconclusive_failures": inconclusive_failures,
            "manual_review_cases": manual_review_cases,
            "elapsed_ms": elapsed_ms,
            "exit_code": exit_code,
        },
        "reproduction_command": (
            "venv/bin/python tool_belt_live_e2e_check.py "
            f"--run-id {validated_run_id} --base-url {base_url}"
        ),
        "notes": [
            (
                "Internal expert evidence and downstream-call suppression are "
                "validated by M7-EXP.7B.3; they are not observable through "
                "the public ChatResponse contract."
            ),
            (
                "A noncompleted expert has no success receipt by design. The "
                "live HTTP contract therefore classifies a missing expected "
                "expert receipt as unobservable, while M7-EXP.7B.3 remains "
                "the deterministic failed-expert gate."
            ),
            "The runner never deletes synthetic Firestore evidence.",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as report_file:
        report_file.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    report_path.chmod(0o600)
    output(
        " ".join(
            (
                "tool-belt-live-e2e-check summary",
                f"http_requests={planned_http_requests}",
                f"automatable_failures={semantic_failures}",
                f"inconclusive_failures={inconclusive_failures}",
                f"manual_review_cases={manual_review_cases}",
                f"elapsed_ms={elapsed_ms}",
                f"report={report_path}",
                f"exit={exit_code}",
            )
        )
    )
    return exit_code


async def run_live(
    *,
    run_id: str,
    base_url: str,
    report_path: Path,
    output: OutputWriter = print,
    environment: Mapping[str, str] | None = None,
) -> int:
    """Load bounded metadata and execute the live HTTP sample."""
    load_dotenv()
    try:
        validated_run_id = validate_run_id(run_id)
        preflight_live_cases(LIVE_E2E_CASES)
        settings = load_vertex_ai_settings(
            os.environ if environment is None else environment
        )
        commit = resolve_repository_commit()
        dirty = is_repository_dirty()
    except LiveE2EConfigurationError as exc:
        output(
            "tool-belt-live-e2e-check configuration_error "
            f"probe={exc.probe_id} reason={exc.reason}"
        )
        return 2
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        VertexAIConfigurationError,
    ):
        output("tool-belt-live-e2e-check configuration_error")
        return 2

    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=150.0,
        ) as client:

            async def requester(
                probe_id: str,
                payload: dict[str, object],
                idempotency_key: str,
            ) -> LiveHttpObservation:
                return await request_live_chat(
                    client=client,
                    probe_id=probe_id,
                    payload=payload,
                    idempotency_key=idempotency_key,
                )

            return await run_bounded_live_e2e(
                run_id=validated_run_id,
                request_chat=requester,
                report_path=report_path,
                output=output,
                repository_commit=commit,
                repository_dirty=dirty,
                configured_project=settings.project,
                configured_location=settings.location,
                base_url=base_url,
            )
    except (OSError, ValueError):
        output("tool-belt-live-e2e-check configuration_error")
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Agent_Col's bounded live end-to-end evaluation."
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Unique lowercase synthetic run identifier (maximum 32 chars).",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the running Agent_Col API.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        help="Synthetic JSON review report path (defaults under /tmp).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    report_path = arguments.report_path or Path(
        f"/tmp/agent-col-m7-exp-7b-4-{arguments.run_id}.json"
    )
    return asyncio.run(
        run_live(
            run_id=arguments.run_id,
            base_url=arguments.base_url,
            report_path=report_path,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
