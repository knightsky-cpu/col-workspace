"""Cross-session live proof for governed synthesis personalization."""

import argparse
import asyncio
import json
import re
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

from database import MemoryEngine, MemoryEngineError
from schemas import (
    AdaptationReceipt,
    BlueprintArtifactDetailResponse,
    ChatResponse,
    MemoryProposal,
)
from tool_belt_routing_check import (
    is_repository_dirty,
    resolve_repository_commit,
)


_RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
REPORT_VERSION = "1.0"
PROOF_MESSAGE = (
    "Create a structured project blueprint from this complete brief. "
    "Goal: build a collaborative study workflow that helps learners submit "
    "materials, approve shared work, and verify progress. Users: university "
    "students and independent study groups. Required behavior: require "
    "explicit approval before shared material advances, expose verifiable "
    "milestones, retain auditable decision receipts, and organize execution "
    "into bounded planning steps. Scope: collaborative planning, material "
    "submission, approval gates, milestone tracking, progress review, and "
    "governed cross-session adaptation. Exclude: autonomous grading, hidden "
    "profiling, sensitive personal data, health advice, and unbounded agent "
    "execution. Deliverable: a locally validated FastAPI and Firestore "
    "service with a lightweight browser workspace and testable milestones."
)


@dataclass(frozen=True, slots=True)
class GovernedSynthesisProofFixture:
    run_id: str
    user_id: str
    project_id: str
    approval_session_id: str
    adapted_session_id: str
    revoked_session_id: str
    signal_id: str
    proposed_value: Literal["micro_steps"] = "micro_steps"


@dataclass(frozen=True, slots=True)
class ProofHttpObservation:
    status_code: int
    body: object


@dataclass(frozen=True, slots=True)
class ProofEvaluation:
    outcome: Literal["pass", "semantic_failure", "inconclusive"]
    classification: str
    artifact_id: str | None = None
    chat_response: ChatResponse | None = None
    artifact_detail: BlueprintArtifactDetailResponse | None = None


class MemoryProofFixture(Protocol):
    async def provision(
        self,
        fixture: GovernedSynthesisProofFixture,
        *,
        observed_at: datetime,
    ) -> AdaptationReceipt: ...

    async def revoke(
        self,
        fixture: GovernedSynthesisProofFixture,
        *,
        observed_at: datetime,
    ) -> None: ...


class MemoryEngineProofFixture:
    """Provision and revoke one isolated signal through MemoryEngine."""

    def __init__(self, engine: object) -> None:
        self._engine = engine

    async def provision(
        self,
        fixture: GovernedSynthesisProofFixture,
        *,
        observed_at: datetime,
    ) -> AdaptationReceipt:
        proposal = MemoryProposal(
            proposal_id=fixture.signal_id,
            category="planning_granularity",
            proposed_value=fixture.proposed_value,
            expected_signal_id=None,
            status="pending",
            source_session_id=fixture.approval_session_id,
            source_message_id=f"{fixture.approval_session_id}-message",
            created_at=observed_at,
            expires_at=observed_at + timedelta(hours=24),
        )
        await self._engine.create_memory_proposal(
            fixture.user_id,
            proposal,
            observed_at=observed_at,
        )
        approval = await self._engine.approve_memory_proposal(
            fixture.user_id,
            "planning_granularity",
            fixture.signal_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=observed_at,
        )
        signal = approval.profile.active_preferences.get(
            "planning_granularity"
        )
        expected = expected_adaptation_receipt(fixture)
        if signal is None:
            raise ValueError("Approved planning signal is missing.")
        receipt = AdaptationReceipt(
            signal_id=signal.signal_id,
            category=signal.category,
            value=signal.value,
            source_event_id=signal.source_event_id,
            status="provided_to_model",
        )
        if receipt != expected:
            raise ValueError("Approved planning signal is inconsistent.")
        return receipt

    async def revoke(
        self,
        fixture: GovernedSynthesisProofFixture,
        *,
        observed_at: datetime,
    ) -> None:
        result = await self._engine.revoke_memory_signal(
            fixture.user_id,
            "planning_granularity",
            fixture.signal_id,
            confirmation_channel="memory_api",
            confirmation_session_id=None,
            confirmation_message_id=None,
            observed_at=observed_at,
        )
        if (
            "planning_granularity" in result.profile.active_preferences
            or result.event.event_type != "revoked"
            or result.event.signal_id != fixture.signal_id
            or result.event.category != "planning_granularity"
        ):
            raise ValueError("Planning signal revocation is inconsistent.")


class ChatRequester(Protocol):
    async def __call__(
        self,
        probe_id: str,
        payload: dict[str, object],
        idempotency_key: str,
    ) -> ProofHttpObservation: ...


class ArtifactGetter(Protocol):
    async def __call__(
        self,
        project_id: str,
        artifact_id: str,
    ) -> ProofHttpObservation: ...


OutputWriter = Callable[[str], None]


def build_proof_fixture(run_id: object) -> GovernedSynthesisProofFixture:
    if not isinstance(run_id, str) or _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError(
            "run_id must be 1 through 32 lowercase letters, digits, or "
            "hyphens and must begin with a letter or digit."
        )
    base = f"m8-col-6e-{run_id}"
    return GovernedSynthesisProofFixture(
        run_id=run_id,
        user_id=f"{base}-user",
        project_id=f"{base}-project",
        approval_session_id=f"{base}-approval",
        adapted_session_id=f"{base}-adapted",
        revoked_session_id=f"{base}-revoked",
        signal_id=f"planning_granularity--{base}",
    )


def expected_adaptation_receipt(
    fixture: GovernedSynthesisProofFixture,
) -> AdaptationReceipt:
    return AdaptationReceipt(
        signal_id=fixture.signal_id,
        category="planning_granularity",
        value=fixture.proposed_value,
        source_event_id=f"{fixture.signal_id}--approved",
        status="provided_to_model",
    )


def evaluate_adapted_evidence(
    fixture: GovernedSynthesisProofFixture,
    chat_observation: ProofHttpObservation,
    detail_observation: ProofHttpObservation,
) -> ProofEvaluation:
    if chat_observation.status_code in (502, 504):
        return ProofEvaluation("inconclusive", "provider_error")
    if chat_observation.status_code != 200:
        return ProofEvaluation("inconclusive", "response_contract_error")
    try:
        response = ChatResponse.model_validate(chat_observation.body)
    except (TypeError, ValueError, ValidationError):
        return ProofEvaluation("inconclusive", "response_contract_error")
    if not response.actions and not response.artifacts:
        return ProofEvaluation(
            "semantic_failure",
            "routing_outcome_mismatch",
            chat_response=response,
        )
    expected_receipt = expected_adaptation_receipt(fixture)
    if response.adaptations != [expected_receipt]:
        return ProofEvaluation(
            "semantic_failure",
            "adaptation_receipt_mismatch",
            chat_response=response,
        )
    if (
        len(response.actions) != 1
        or response.actions[0].action_name != "synthesize_project"
        or response.actions[0].status != "completed"
        or len(response.artifacts) != 1
    ):
        return ProofEvaluation(
            "semantic_failure",
            "artifact_receipt_mismatch",
            chat_response=response,
        )
    artifact = response.artifacts[0]
    if (
        artifact.artifact_type != "synthesis_blueprint"
        or artifact.project_id != fixture.project_id
    ):
        return ProofEvaluation(
            "semantic_failure",
            "artifact_receipt_mismatch",
            chat_response=response,
        )
    if detail_observation.status_code != 200:
        return ProofEvaluation(
            "inconclusive",
            "artifact_detail_error",
            artifact_id=artifact.artifact_id,
            chat_response=response,
        )
    try:
        detail = BlueprintArtifactDetailResponse.model_validate(
            detail_observation.body
        )
    except (TypeError, ValueError, ValidationError):
        return ProofEvaluation(
            "inconclusive",
            "artifact_detail_error",
            artifact_id=artifact.artifact_id,
            chat_response=response,
        )
    trace = detail.blueprint.personalization_trace.adaptations
    if (
        detail.metadata.reference != artifact
        or detail.metadata.originating_session_id
        != fixture.adapted_session_id
        or detail.adaptations != [expected_receipt]
        or detail.metadata.adaptation_categories
        != ["planning_granularity"]
        or len(trace) != 1
        or trace[0].profile_key != "planning_granularity"
    ):
        return ProofEvaluation(
            "semantic_failure",
            "canonical_adaptation_mismatch",
            artifact_id=artifact.artifact_id,
            chat_response=response,
            artifact_detail=detail,
        )
    return ProofEvaluation(
        "pass",
        "pass",
        artifact_id=artifact.artifact_id,
        chat_response=response,
        artifact_detail=detail,
    )


def evaluate_revoked_evidence(
    fixture: GovernedSynthesisProofFixture,
    chat_observation: ProofHttpObservation,
    detail_observation: ProofHttpObservation,
) -> ProofEvaluation:
    if chat_observation.status_code in (502, 504):
        return ProofEvaluation("inconclusive", "provider_error")
    if chat_observation.status_code != 200:
        return ProofEvaluation("inconclusive", "response_contract_error")
    try:
        response = ChatResponse.model_validate(chat_observation.body)
    except (TypeError, ValueError, ValidationError):
        return ProofEvaluation("inconclusive", "response_contract_error")
    if response.adaptations:
        return ProofEvaluation(
            "semantic_failure",
            "revoked_adaptation_leak",
            chat_response=response,
        )
    if not response.actions and not response.artifacts:
        return ProofEvaluation(
            "semantic_failure",
            "routing_outcome_mismatch",
            chat_response=response,
        )
    if (
        len(response.actions) != 1
        or response.actions[0].action_name != "synthesize_project"
        or response.actions[0].status != "completed"
        or len(response.artifacts) != 1
    ):
        return ProofEvaluation(
            "semantic_failure",
            "artifact_receipt_mismatch",
            chat_response=response,
        )
    artifact = response.artifacts[0]
    if (
        artifact.artifact_type != "synthesis_blueprint"
        or artifact.project_id != fixture.project_id
    ):
        return ProofEvaluation(
            "semantic_failure",
            "artifact_receipt_mismatch",
            chat_response=response,
        )
    if detail_observation.status_code != 200:
        return ProofEvaluation(
            "inconclusive",
            "artifact_detail_error",
            artifact_id=artifact.artifact_id,
            chat_response=response,
        )
    try:
        detail = BlueprintArtifactDetailResponse.model_validate(
            detail_observation.body
        )
    except (TypeError, ValueError, ValidationError):
        return ProofEvaluation(
            "inconclusive",
            "artifact_detail_error",
            artifact_id=artifact.artifact_id,
            chat_response=response,
        )
    if (
        detail.metadata.reference != artifact
        or detail.metadata.originating_session_id
        != fixture.revoked_session_id
    ):
        return ProofEvaluation(
            "semantic_failure",
            "canonical_artifact_mismatch",
            artifact_id=artifact.artifact_id,
            chat_response=response,
            artifact_detail=detail,
        )
    if (
        detail.adaptations
        or detail.metadata.adaptation_categories
        or detail.blueprint.personalization_trace.adaptations
    ):
        return ProofEvaluation(
            "semantic_failure",
            "revoked_adaptation_leak",
            artifact_id=artifact.artifact_id,
            chat_response=response,
            artifact_detail=detail,
        )
    return ProofEvaluation(
        "pass",
        "pass",
        artifact_id=artifact.artifact_id,
        chat_response=response,
        artifact_detail=detail,
    )


def evaluate_replay(
    original: ProofHttpObservation,
    replay: ProofHttpObservation,
) -> ProofEvaluation:
    if replay.status_code in (502, 504):
        return ProofEvaluation("inconclusive", "provider_error")
    if original.status_code != 200 or replay.status_code != 200:
        return ProofEvaluation("inconclusive", "replay_dependency_error")
    if replay.body != original.body:
        return ProofEvaluation("semantic_failure", "idempotency_failure")
    try:
        response = ChatResponse.model_validate(replay.body)
    except (TypeError, ValueError, ValidationError):
        return ProofEvaluation("inconclusive", "response_contract_error")
    return ProofEvaluation("pass", "pass", chat_response=response)


def evaluate_conflict(observation: ProofHttpObservation) -> ProofEvaluation:
    if observation.status_code != 409:
        return ProofEvaluation("semantic_failure", "idempotency_failure")
    if not isinstance(observation.body, Mapping) or observation.body.get(
        "detail"
    ) != "Idempotency key conflicts with a different chat request.":
        return ProofEvaluation("semantic_failure", "conflict_contract_error")
    return ProofEvaluation("pass", "pass")


def _artifact_id(observation: ProofHttpObservation) -> str | None:
    if observation.status_code != 200:
        return None
    try:
        response = ChatResponse.model_validate(observation.body)
    except (TypeError, ValueError, ValidationError):
        return None
    if len(response.artifacts) != 1:
        return None
    return response.artifacts[0].artifact_id


def _report_evaluation(evaluation: ProofEvaluation) -> dict[str, object]:
    return {
        "evaluation": evaluation.classification,
        "outcome": evaluation.outcome,
        "artifact_id": evaluation.artifact_id,
        "chat_response": (
            evaluation.chat_response.model_dump(mode="json")
            if evaluation.chat_response is not None
            else None
        ),
        "artifact_detail": (
            evaluation.artifact_detail.model_dump(mode="json")
            if evaluation.artifact_detail is not None
            else None
        ),
    }


async def run_cross_session_proof(
    *,
    run_id: str,
    memory_fixture: MemoryProofFixture,
    request_chat: ChatRequester,
    get_artifact: ArtifactGetter,
    report_path: Path,
    output: OutputWriter,
    repository_commit: str,
    repository_dirty: bool,
    base_url: str = "http://127.0.0.1:8000",
    now: Callable[[], datetime] | None = None,
    monotonic_values: Iterator[float] | None = None,
) -> int:
    fixture = build_proof_fixture(run_id)
    if _COMMIT_PATTERN.fullmatch(repository_commit) is None:
        raise ValueError("repository_commit is invalid.")
    if report_path.exists():
        raise ValueError("report_path must not already exist.")
    current_time = now or (lambda: datetime.now(UTC))
    times = monotonic_values
    started = next(times) if times is not None else time.monotonic()
    observed_at = current_time()
    expected_receipt = expected_adaptation_receipt(fixture)
    supplied_receipt = await memory_fixture.provision(
        fixture,
        observed_at=observed_at,
    )
    if supplied_receipt != expected_receipt:
        raise ValueError("Provisioned memory receipt is inconsistent.")

    output(
        " ".join(
            (
                "governed-synthesis-live-check",
                f"commit={repository_commit}",
                f"worktree={'dirty' if repository_dirty else 'clean'}",
                "planned_http_requests=6",
            )
        )
    )
    http_requests = 0

    async def execute_chat(
        probe_id: str,
        payload: dict[str, object],
        idempotency_key: str,
    ) -> ProofHttpObservation:
        nonlocal http_requests
        observation = await request_chat(
            probe_id,
            payload,
            idempotency_key,
        )
        http_requests += 1
        return observation

    async def execute_get(artifact_id: str) -> ProofHttpObservation:
        nonlocal http_requests
        observation = await get_artifact(
            fixture.project_id,
            artifact_id,
        )
        http_requests += 1
        return observation

    adapted_payload: dict[str, object] = {
        "project_id": fixture.project_id,
        "session_id": fixture.adapted_session_id,
        "user_id": fixture.user_id,
        "message": PROOF_MESSAGE,
    }
    adapted_key = f"{fixture.adapted_session_id}-key"
    try:
        adapted_observation = await execute_chat(
            "adapted",
            adapted_payload,
            adapted_key,
        )
        adapted_artifact_id = _artifact_id(adapted_observation)
        adapted_detail_observation = (
            await execute_get(adapted_artifact_id)
            if adapted_artifact_id is not None
            else ProofHttpObservation(0, None)
        )
        adapted_evaluation = evaluate_adapted_evidence(
            fixture,
            adapted_observation,
            adapted_detail_observation,
        )
        replay_observation = await execute_chat(
            "adapted-replay",
            adapted_payload,
            adapted_key,
        )
        replay_evaluation = evaluate_replay(
            adapted_observation,
            replay_observation,
        )
        conflict_payload = dict(adapted_payload)
        conflict_payload["message"] = (
            "This changed synthetic request must conflict with the existing "
            "key."
        )
        conflict_evaluation = evaluate_conflict(
            await execute_chat(
                "adapted-conflict",
                conflict_payload,
                adapted_key,
            )
        )
    finally:
        await memory_fixture.revoke(
            fixture,
            observed_at=current_time(),
        )

    revoked_payload: dict[str, object] = {
        "project_id": fixture.project_id,
        "session_id": fixture.revoked_session_id,
        "user_id": fixture.user_id,
        "message": PROOF_MESSAGE,
    }
    revoked_observation = await execute_chat(
        "revoked",
        revoked_payload,
        f"{fixture.revoked_session_id}-key",
    )
    revoked_artifact_id = _artifact_id(revoked_observation)
    revoked_detail_observation = (
        await execute_get(revoked_artifact_id)
        if revoked_artifact_id is not None
        else ProofHttpObservation(0, None)
    )
    revoked_evaluation = evaluate_revoked_evidence(
        fixture,
        revoked_observation,
        revoked_detail_observation,
    )

    evaluations = (
        adapted_evaluation,
        replay_evaluation,
        conflict_evaluation,
        revoked_evaluation,
    )
    semantic_failures = sum(
        evaluation.outcome == "semantic_failure"
        for evaluation in evaluations
    )
    inconclusive_failures = sum(
        evaluation.outcome == "inconclusive"
        for evaluation in evaluations
    )
    manual_review_cases = sum(
        evaluation.outcome == "pass"
        for evaluation in (adapted_evaluation, revoked_evaluation)
    )
    finished = next(times) if times is not None else time.monotonic()
    elapsed_ms = round((finished - started) * 1_000)
    exit_code = 2 if inconclusive_failures else (1 if semantic_failures else 0)
    report = {
        "report_version": REPORT_VERSION,
        "run_id": fixture.run_id,
        "started_at": observed_at.isoformat(),
        "repository": {
            "commit": repository_commit,
            "worktree": "dirty" if repository_dirty else "clean",
        },
        "base_url": base_url,
        "memory": {
            "status": "revoked",
            "user_id": fixture.user_id,
            "approval_session_id": fixture.approval_session_id,
            "signal": expected_receipt.model_dump(mode="json"),
            "firestore_paths": [
                f"users/{fixture.user_id}",
                (
                    f"users/{fixture.user_id}/memory_events/"
                    f"{expected_receipt.source_event_id}"
                ),
                (
                    f"users/{fixture.user_id}/memory_events/"
                    f"{fixture.signal_id}--revoked"
                ),
            ],
        },
        "adapted_artifact": _report_evaluation(adapted_evaluation),
        "replay": _report_evaluation(replay_evaluation),
        "conflict": _report_evaluation(conflict_evaluation),
        "revoked_artifact": _report_evaluation(revoked_evaluation),
        "summary": {
            "http_requests": http_requests,
            "semantic_failures": semantic_failures,
            "inconclusive_failures": inconclusive_failures,
            "manual_review_cases": manual_review_cases,
            "elapsed_ms": elapsed_ms,
            "exit_code": exit_code,
        },
        "notes": [
            "The synthetic memory signal remains revoked for Firestore audit.",
            (
                "Manual review must compare roadmap granularity without "
                "treating stylistic variation as provenance."
            ),
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as report_file:
        report_file.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    report_path.chmod(0o600)
    output(
        " ".join(
            (
                "governed-synthesis-live-check summary",
                f"http_requests={http_requests}",
                f"semantic_failures={semantic_failures}",
                f"inconclusive_failures={inconclusive_failures}",
                f"manual_review_cases={manual_review_cases}",
                f"elapsed_ms={elapsed_ms}",
                f"report={report_path}",
                f"exit={exit_code}",
            )
        )
    )
    return exit_code


async def request_live_chat(
    *,
    client: httpx.AsyncClient,
    payload: dict[str, object],
    idempotency_key: str,
) -> ProofHttpObservation:
    try:
        response = await client.post(
            "/api/chat",
            headers={"Idempotency-Key": idempotency_key},
            json=payload,
        )
    except httpx.RequestError:
        return ProofHttpObservation(0, None)
    try:
        body: object = response.json()
    except (TypeError, ValueError):
        body = None
    return ProofHttpObservation(response.status_code, body)


async def request_live_artifact(
    *,
    client: httpx.AsyncClient,
    project_id: str,
    artifact_id: str,
) -> ProofHttpObservation:
    try:
        response = await client.get(
            f"/api/projects/{project_id}/blueprints/{artifact_id}"
        )
    except httpx.RequestError:
        return ProofHttpObservation(0, None)
    try:
        body: object = response.json()
    except (TypeError, ValueError):
        body = None
    return ProofHttpObservation(response.status_code, body)


async def run_live(
    *,
    run_id: str,
    base_url: str,
    report_path: Path,
    output: OutputWriter = print,
) -> int:
    load_dotenv()
    try:
        fixture = build_proof_fixture(run_id)
        commit = resolve_repository_commit()
        dirty = is_repository_dirty()
    except (OSError, subprocess.SubprocessError, ValueError):
        output("governed-synthesis-live-check configuration_error")
        return 2

    engine = MemoryEngine()
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=150.0,
        ) as client:

            async def requester(
                probe_id: str,
                payload: dict[str, object],
                idempotency_key: str,
            ) -> ProofHttpObservation:
                del probe_id
                return await request_live_chat(
                    client=client,
                    payload=payload,
                    idempotency_key=idempotency_key,
                )

            async def artifact_getter(
                project_id: str,
                artifact_id: str,
            ) -> ProofHttpObservation:
                return await request_live_artifact(
                    client=client,
                    project_id=project_id,
                    artifact_id=artifact_id,
                )

            return await run_cross_session_proof(
                run_id=fixture.run_id,
                memory_fixture=MemoryEngineProofFixture(engine),
                request_chat=requester,
                get_artifact=artifact_getter,
                report_path=report_path,
                output=output,
                repository_commit=commit,
                repository_dirty=dirty,
                base_url=base_url,
            )
    except (MemoryEngineError, OSError, ValueError):
        output("governed-synthesis-live-check runtime_error")
        return 2
    finally:
        engine.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Agent_Col's cross-session governed synthesis proof."
        )
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
        help="Private JSON review report path (defaults under /tmp).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fixture = build_proof_fixture(args.run_id)
    except ValueError:
        print("governed-synthesis-live-check configuration_error")
        return 2
    report_path = args.report_path or Path(
        f"/tmp/agent-col-m8-col-6e-{fixture.run_id}.json"
    )
    return asyncio.run(
        run_live(
            run_id=fixture.run_id,
            base_url=args.base_url,
            report_path=report_path,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
