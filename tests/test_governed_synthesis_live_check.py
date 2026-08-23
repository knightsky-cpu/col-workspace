import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from schemas import ActiveMemorySignal, CollaborationProfile

import pytest


def blueprint_payload(*, adapted: bool) -> dict[str, object]:
    adaptations = []
    if adapted:
        adaptations = [
            {
                "profile_key": "planning_granularity",
                "architecture_change": "The roadmap uses micro-steps.",
                "reason": "The approved preference requests micro-steps.",
            }
        ]
    return {
        "synthesized_conceptual_model": {
            "project_name": "Governed Collaboration Proof",
            "core_value_proposition": "Produces bounded, verifiable plans.",
            "in_scope": ["Collaborative planning"],
        },
        "personalization_trace": {"adaptations": adaptations},
        "architectural_decisions": [
            {
                "component_name": "Approval boundary",
                "proposed_solution": "Explicit governed memory",
                "rationale": "Keeps adaptation user-controlled.",
                "alternatives": [
                    {
                        "option_name": "Inferred profile",
                        "tradeoff": "Lower friction but weaker provenance.",
                        "reason_not_selected": "Cannot prove approval.",
                    }
                ],
            }
        ],
        "socratic_clarifying_questions": [
            {
                "question_text": "Which milestone comes first?",
                "why_this_matters": "It defines the first bounded step.",
                "suggested_options": [
                    {"label": "Foundation", "impact": "Start small."},
                    {"label": "Prototype", "impact": "Start hands-on."},
                ],
            }
        ],
        "step_by_step_execution_roadmap": [
            {
                "phase_name": "Foundation",
                "objective": "Define the first milestone.",
                "expected_deliverable": "One approved milestone.",
                "micro_tasks": [
                    {
                        "task_description": "Choose the milestone.",
                        "complexity_level": "Low",
                        "verification_steps": ["Record explicit approval."],
                    }
                ],
            }
        ],
    }


def adaptation_receipt(run_id: str) -> dict[str, str]:
    signal_id = f"planning_granularity--m8-col-6e-{run_id}"
    return {
        "signal_id": signal_id,
        "category": "planning_granularity",
        "value": "micro_steps",
        "source_event_id": f"{signal_id}--approved",
        "status": "provided_to_model",
    }


def adapted_chat_body(run_id: str) -> dict[str, object]:
    project_id = f"m8-col-6e-{run_id}-project"
    return {
        "response": "The governed blueprint was created.",
        "actions": [
            {"action_name": "synthesize_project", "status": "completed"}
        ],
        "artifacts": [
            {
                "artifact_type": "synthesis_blueprint",
                "project_id": project_id,
                "artifact_id": "blueprint--adapted-turn",
                "schema_version": "2.0",
                "display_label": "Governed Collaboration Proof",
            }
        ],
        "artifact_feedback": [],
        "citations": [],
        "memory_proposals": [],
        "adaptations": [adaptation_receipt(run_id)],
    }


def unadapted_chat_body(run_id: str) -> dict[str, object]:
    project_id = f"m8-col-6e-{run_id}-project"
    return {
        "response": "The unadapted blueprint was created.",
        "actions": [
            {"action_name": "synthesize_project", "status": "completed"}
        ],
        "artifacts": [
            {
                "artifact_type": "synthesis_blueprint",
                "project_id": project_id,
                "artifact_id": "blueprint--revoked-turn",
                "schema_version": "2.0",
                "display_label": "Governed Collaboration Proof",
            }
        ],
        "artifact_feedback": [],
        "citations": [],
        "memory_proposals": [],
        "adaptations": [],
    }


def clarification_chat_body() -> dict[str, object]:
    return {
        "response": (
            "Please provide the complete project brief before I create the "
            "blueprint."
        ),
        "actions": [],
        "artifacts": [],
        "artifact_feedback": [],
        "citations": [],
        "memory_proposals": [],
        "adaptations": [],
    }


def artifact_detail_body(run_id: str, *, adapted: bool) -> dict[str, object]:
    receipts = [adaptation_receipt(run_id)] if adapted else []
    suffix = "adapted" if adapted else "revoked"
    session_id = f"m8-col-6e-{run_id}-{suffix}"
    return {
        "artifact_contract_version": "1.0",
        "metadata": {
            "reference": {
                "artifact_type": "synthesis_blueprint",
                "project_id": f"m8-col-6e-{run_id}-project",
                "artifact_id": f"blueprint--{suffix}-turn",
                "schema_version": "2.0",
                "display_label": "Governed Collaboration Proof",
            },
            "created_at": "2026-08-23T20:00:00Z",
            "originating_session_id": session_id,
            "originating_turn_id": f"{suffix}-turn",
            "parent_artifact_id": None,
            "feedback_counts": {"accepted": 0, "rejected": 0, "edited": 0},
            "adaptation_categories": (
                ["planning_granularity"] if adapted else []
            ),
        },
        "blueprint": blueprint_payload(adapted=adapted),
        "feedback_targets": [],
        "adaptations": receipts,
        "applied_feedback_ids": [],
    }


def load_check_module():
    try:
        return importlib.import_module("governed_synthesis_live_check")
    except ModuleNotFoundError:
        pytest.fail("governed_synthesis_live_check has not been implemented")


def test_fixture_uses_one_synthetic_user_and_separate_bounded_sessions() -> None:
    module = load_check_module()

    fixture = module.build_proof_fixture("manual-20260823-01")

    assert fixture.run_id == "manual-20260823-01"
    assert fixture.user_id == "m8-col-6e-manual-20260823-01-user"
    assert fixture.project_id == "m8-col-6e-manual-20260823-01-project"
    assert fixture.approval_session_id.endswith("-approval")
    assert fixture.adapted_session_id.endswith("-adapted")
    assert fixture.revoked_session_id.endswith("-revoked")
    assert len(
        {
            fixture.approval_session_id,
            fixture.adapted_session_id,
            fixture.revoked_session_id,
        }
    ) == 3
    assert fixture.signal_id == (
        "planning_granularity--m8-col-6e-manual-20260823-01"
    )
    assert fixture.proposed_value == "micro_steps"


@pytest.mark.parametrize(
    "run_id",
    ("", "contains space", "UPPERCASE", "x" * 33, "../escape"),
)
def test_fixture_rejects_unsafe_run_ids(run_id: str) -> None:
    module = load_check_module()

    with pytest.raises(ValueError, match="run_id"):
        module.build_proof_fixture(run_id)


def test_adapted_evidence_requires_exact_chat_canonical_and_trace_receipts(
) -> None:
    module = load_check_module()
    run_id = "manual-20260823-01"
    fixture = module.build_proof_fixture(run_id)

    result = module.evaluate_adapted_evidence(
        fixture,
        module.ProofHttpObservation(200, adapted_chat_body(run_id)),
        module.ProofHttpObservation(
            200,
            artifact_detail_body(run_id, adapted=True),
        ),
    )

    assert result.outcome == "pass"
    assert result.classification == "pass"
    assert result.artifact_id == "blueprint--adapted-turn"


def test_adapted_evidence_rejects_missing_chat_receipt() -> None:
    module = load_check_module()
    run_id = "manual-20260823-01"
    body = adapted_chat_body(run_id)
    body["adaptations"] = []

    result = module.evaluate_adapted_evidence(
        module.build_proof_fixture(run_id),
        module.ProofHttpObservation(200, body),
        module.ProofHttpObservation(
            200,
            artifact_detail_body(run_id, adapted=True),
        ),
    )

    assert result.outcome == "semantic_failure"
    assert result.classification == "adaptation_receipt_mismatch"


def test_revoked_evidence_requires_no_public_canonical_or_trace_claim() -> None:
    module = load_check_module()
    run_id = "manual-20260823-01"

    result = module.evaluate_revoked_evidence(
        module.build_proof_fixture(run_id),
        module.ProofHttpObservation(200, unadapted_chat_body(run_id)),
        module.ProofHttpObservation(
            200,
            artifact_detail_body(run_id, adapted=False),
        ),
    )

    assert result.outcome == "pass"
    assert result.classification == "pass"
    assert result.artifact_id == "blueprint--revoked-turn"


def test_revoked_evidence_rejects_lingering_canonical_receipt() -> None:
    module = load_check_module()
    run_id = "manual-20260823-01"
    detail = artifact_detail_body(run_id, adapted=False)
    detail["adaptations"] = [adaptation_receipt(run_id)]

    result = module.evaluate_revoked_evidence(
        module.build_proof_fixture(run_id),
        module.ProofHttpObservation(200, unadapted_chat_body(run_id)),
        module.ProofHttpObservation(200, detail),
    )

    assert result.outcome == "semantic_failure"
    assert result.classification == "revoked_adaptation_leak"


def test_revoked_evidence_classifies_clarification_as_routing_mismatch() -> None:
    module = load_check_module()

    result = module.evaluate_revoked_evidence(
        module.build_proof_fixture("manual-20260823-01"),
        module.ProofHttpObservation(200, clarification_chat_body()),
        module.ProofHttpObservation(0, None),
    )

    assert result.outcome == "semantic_failure"
    assert result.classification == "routing_outcome_mismatch"
    assert result.artifact_id is None


def test_adapted_evidence_classifies_clarification_as_routing_mismatch() -> None:
    module = load_check_module()

    result = module.evaluate_adapted_evidence(
        module.build_proof_fixture("manual-20260823-01"),
        module.ProofHttpObservation(200, clarification_chat_body()),
        module.ProofHttpObservation(0, None),
    )

    assert result.outcome == "semantic_failure"
    assert result.classification == "routing_outcome_mismatch"
    assert result.artifact_id is None


def test_replay_and_changed_key_conflict_are_exact() -> None:
    module = load_check_module()
    body = adapted_chat_body("manual-20260823-01")
    original = module.ProofHttpObservation(200, body)

    replay = module.evaluate_replay(
        original,
        module.ProofHttpObservation(200, body),
    )
    conflict = module.evaluate_conflict(
        module.ProofHttpObservation(
            409,
            {"detail": "Idempotency key conflicts with a different chat request."},
        )
    )

    assert (replay.outcome, replay.classification) == ("pass", "pass")
    assert (conflict.outcome, conflict.classification) == ("pass", "pass")


class PassingMemoryFixtureManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def provision(self, fixture: object, *, observed_at: datetime):
        module = load_check_module()
        self.calls.append(("provision", fixture))
        return module.expected_adaptation_receipt(fixture)

    async def revoke(self, fixture: object, *, observed_at: datetime) -> None:
        self.calls.append(("revoke", fixture))


class PassingProofHttpBoundary:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.calls: list[tuple[str, dict[str, object], str]] = []
        self.adapted_failure = False

    async def request_chat(
        self,
        probe_id: str,
        payload: dict[str, object],
        idempotency_key: str,
    ):
        module = load_check_module()
        self.calls.append((probe_id, payload, idempotency_key))
        if probe_id in {"adapted", "adapted-replay"}:
            if self.adapted_failure:
                return module.ProofHttpObservation(
                    502,
                    {"detail": "private provider error"},
                )
            return module.ProofHttpObservation(
                200,
                adapted_chat_body(self.run_id),
            )
        if probe_id == "adapted-conflict":
            return module.ProofHttpObservation(
                409,
                {
                    "detail": (
                        "Idempotency key conflicts with a different chat "
                        "request."
                    )
                },
            )
        if probe_id == "revoked":
            return module.ProofHttpObservation(
                200,
                unadapted_chat_body(self.run_id),
            )
        raise AssertionError(f"unexpected probe: {probe_id}")

    async def get_artifact(self, project_id: str, artifact_id: str):
        module = load_check_module()
        self.calls.append(
            (
                "adapted-detail" if "adapted" in artifact_id else "revoked-detail",
                {"project_id": project_id, "artifact_id": artifact_id},
                "",
            )
        )
        return module.ProofHttpObservation(
            200,
            artifact_detail_body(
                self.run_id,
                adapted="adapted" in artifact_id,
            ),
        )


class SourceSufficiencyAwareProofHttpBoundary(PassingProofHttpBoundary):
    async def request_chat(
        self,
        probe_id: str,
        payload: dict[str, object],
        idempotency_key: str,
    ):
        message = payload.get("message")
        required_sections = (
            "Goal:",
            "Users:",
            "Required behavior:",
            "Scope:",
            "Exclude:",
            "Deliverable:",
        )
        if (
            probe_id != "adapted-conflict"
            and (
                not isinstance(message, str)
                or not all(section in message for section in required_sections)
            )
        ):
            module = load_check_module()
            self.calls.append((probe_id, payload, idempotency_key))
            return module.ProofHttpObservation(200, clarification_chat_body())
        return await super().request_chat(probe_id, payload, idempotency_key)


@pytest.mark.asyncio
async def test_runner_uses_complete_source_material_for_each_artifact_session(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    run_id = "complete-source"
    memory = PassingMemoryFixtureManager()
    http = SourceSufficiencyAwareProofHttpBoundary(run_id)

    exit_code = await module.run_cross_session_proof(
        run_id=run_id,
        memory_fixture=memory,
        request_chat=http.request_chat,
        get_artifact=http.get_artifact,
        report_path=tmp_path / "complete-source.json",
        output=lambda _line: None,
        repository_commit="c" * 40,
        repository_dirty=True,
    )

    assert exit_code == 0
    adapted_message = http.calls[0][1]["message"]
    revoked_message = next(
        call[1]["message"] for call in http.calls if call[0] == "revoked"
    )
    assert revoked_message == adapted_message


@pytest.mark.asyncio
async def test_runner_proves_cross_session_revocation_and_writes_safe_report(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    run_id = "manual-20260823-01"
    memory = PassingMemoryFixtureManager()
    http = PassingProofHttpBoundary(run_id)
    output: list[str] = []
    report_path = tmp_path / "proof.json"

    exit_code = await module.run_cross_session_proof(
        run_id=run_id,
        memory_fixture=memory,
        request_chat=http.request_chat,
        get_artifact=http.get_artifact,
        report_path=report_path,
        output=output.append,
        repository_commit="a" * 40,
        repository_dirty=False,
        now=lambda: datetime(2026, 8, 23, 20, 0, tzinfo=UTC),
        monotonic_values=iter((10.0, 10.5)),
    )

    assert exit_code == 0
    assert [call[0] for call in memory.calls] == ["provision", "revoke"]
    assert [call[0] for call in http.calls] == [
        "adapted",
        "adapted-detail",
        "adapted-replay",
        "adapted-conflict",
        "revoked",
        "revoked-detail",
    ]
    adapted_call = http.calls[0]
    replay_call = http.calls[2]
    conflict_call = http.calls[3]
    revoked_call = http.calls[4]
    assert replay_call[1:] == adapted_call[1:]
    assert conflict_call[2] == adapted_call[2]
    assert conflict_call[1]["message"] != adapted_call[1]["message"]
    assert adapted_call[1]["session_id"].endswith("-adapted")
    assert revoked_call[1]["session_id"].endswith("-revoked")
    assert revoked_call[1]["session_id"] != adapted_call[1]["session_id"]

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report_version"] == "1.0"
    assert report["summary"] == {
        "http_requests": 6,
        "semantic_failures": 0,
        "inconclusive_failures": 0,
        "manual_review_cases": 2,
        "elapsed_ms": 500,
        "exit_code": 0,
    }
    assert report["memory"]["status"] == "revoked"
    assert report["adapted_artifact"]["evaluation"] == "pass"
    assert report["revoked_artifact"]["evaluation"] == "pass"
    assert report_path.stat().st_mode & 0o777 == 0o600

    terminal = "\n".join(output)
    assert "The governed blueprint was created" not in terminal
    assert "The unadapted blueprint was created" not in terminal
    assert "planned_http_requests=6" in terminal
    assert "manual_review_cases=2" in terminal
    assert str(report_path) in terminal


@pytest.mark.asyncio
async def test_provider_failure_still_revokes_and_reports_actual_request_count(
    tmp_path: Path,
) -> None:
    module = load_check_module()
    run_id = "provider-failure"
    memory = PassingMemoryFixtureManager()
    http = PassingProofHttpBoundary(run_id)
    http.adapted_failure = True
    report_path = tmp_path / "provider-failure.json"

    exit_code = await module.run_cross_session_proof(
        run_id=run_id,
        memory_fixture=memory,
        request_chat=http.request_chat,
        get_artifact=http.get_artifact,
        report_path=report_path,
        output=lambda _line: None,
        repository_commit="b" * 40,
        repository_dirty=True,
    )

    assert exit_code == 2
    assert [call[0] for call in memory.calls] == ["provision", "revoke"]
    assert [call[0] for call in http.calls] == [
        "adapted",
        "adapted-replay",
        "adapted-conflict",
        "revoked",
        "revoked-detail",
    ]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["http_requests"] == 5
    assert report["summary"]["inconclusive_failures"] > 0


class FakeMemoryEngine:
    def __init__(self, fixture: object) -> None:
        self.fixture = fixture
        self.calls: list[tuple[str, object]] = []
        self.signal = ActiveMemorySignal.model_validate(
            {
                "signal_id": fixture.signal_id,
                "category": "planning_granularity",
                "value": "micro_steps",
                "policy_version": "1.0",
                "source_event_id": f"{fixture.signal_id}--approved",
                "approved_at": "2026-08-23T20:00:00Z",
            }
        )

    async def create_memory_proposal(
        self,
        user_id: str,
        proposal: object,
        *,
        observed_at: datetime,
    ) -> object:
        self.calls.append(("create", proposal))
        return proposal

    async def approve_memory_proposal(
        self,
        user_id: str,
        category: str,
        proposal_id: str,
        **kwargs: object,
    ) -> object:
        self.calls.append(("approve", kwargs))
        return SimpleNamespace(
            profile=CollaborationProfile(
                memory_revision=1,
                active_preferences={"planning_granularity": self.signal},
            )
        )

    async def revoke_memory_signal(
        self,
        user_id: str,
        category: str,
        signal_id: str,
        **kwargs: object,
    ) -> object:
        self.calls.append(("revoke", kwargs))
        return SimpleNamespace(
            profile=CollaborationProfile(memory_revision=2),
            event=SimpleNamespace(
                event_type="revoked",
                signal_id=signal_id,
                category=category,
            ),
        )


@pytest.mark.asyncio
async def test_memory_adapter_derives_receipt_from_approved_signal_and_revokes(
) -> None:
    module = load_check_module()
    fixture = module.build_proof_fixture("manual-20260823-01")
    engine = FakeMemoryEngine(fixture)
    adapter = module.MemoryEngineProofFixture(engine)
    observed_at = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)

    receipt = await adapter.provision(fixture, observed_at=observed_at)
    await adapter.revoke(fixture, observed_at=observed_at)

    assert receipt == module.expected_adaptation_receipt(fixture)
    assert [call[0] for call in engine.calls] == [
        "create",
        "approve",
        "revoke",
    ]
    proposal = engine.calls[0][1]
    assert proposal.proposal_id == fixture.signal_id
    assert proposal.category == "planning_granularity"
    assert proposal.proposed_value == "micro_steps"
    assert proposal.source_session_id == fixture.approval_session_id
    assert proposal.expires_at - proposal.created_at == timedelta(hours=24)
    assert engine.calls[1][1]["confirmation_channel"] == "memory_api"
    assert engine.calls[1][1]["confirmation_session_id"] is None
    assert engine.calls[1][1]["confirmation_message_id"] is None
    assert engine.calls[2][1]["confirmation_session_id"] is None
    assert engine.calls[2][1]["confirmation_message_id"] is None


class FakeHttpResponse:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        return self._body


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    async def post(self, path: str, **kwargs: object) -> FakeHttpResponse:
        self.calls.append(("post", path, kwargs))
        return FakeHttpResponse(200, adapted_chat_body("manual-20260823-01"))

    async def get(self, path: str, **kwargs: object) -> FakeHttpResponse:
        self.calls.append(("get", path, kwargs))
        return FakeHttpResponse(
            200,
            artifact_detail_body("manual-20260823-01", adapted=True),
        )


@pytest.mark.asyncio
async def test_live_http_adapter_uses_exact_public_paths_without_retries(
) -> None:
    module = load_check_module()
    client = FakeHttpClient()
    payload = {
        "project_id": "m8-col-6e-manual-20260823-01-project",
        "session_id": "m8-col-6e-manual-20260823-01-adapted",
        "user_id": "m8-col-6e-manual-20260823-01-user",
        "message": module.PROOF_MESSAGE,
    }

    chat = await module.request_live_chat(
        client=client,
        payload=payload,
        idempotency_key="proof-key",
    )
    detail = await module.request_live_artifact(
        client=client,
        project_id=payload["project_id"],
        artifact_id="blueprint--adapted-turn",
    )

    assert chat.status_code == 200
    assert detail.status_code == 200
    assert client.calls == [
        (
            "post",
            "/api/chat",
            {
                "headers": {"Idempotency-Key": "proof-key"},
                "json": payload,
            },
        ),
        (
            "get",
            (
                "/api/projects/m8-col-6e-manual-20260823-01-project/"
                "blueprints/blueprint--adapted-turn"
            ),
            {},
        ),
    ]


def test_cli_requires_run_id_and_defaults_to_local_api() -> None:
    module = load_check_module()
    parser = module.build_parser()

    args = parser.parse_args(["--run-id", "manual-20260823-01"])

    assert args.run_id == "manual-20260823-01"
    assert args.base_url == "http://127.0.0.1:8000"
    assert args.report_path is None
