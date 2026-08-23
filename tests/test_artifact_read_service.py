from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest


NOW = datetime(2026, 8, 23, 14, 0, tzinfo=UTC)


def blueprint_payload() -> dict[str, object]:
    return {
        "synthesized_conceptual_model": {
            "project_name": "Study Partner",
            "core_value_proposition": "Turns rubrics into executable plans.",
            "in_scope": ["Planning"],
            "out_of_scope": [],
            "assumptions": [],
        },
        "personalization_trace": {
            "adaptations": [
                {
                    "profile_key": "experience_level",
                    "architecture_change": "Adds smaller steps.",
                    "reason": "Supports the supplied profile.",
                }
            ]
        },
        "architectural_decisions": [
            {
                "component_name": "Persistence",
                "proposed_solution": "Firestore",
                "rationale": "Preserves durable project work.",
                "alternatives": [
                    {
                        "option_name": "SQLite",
                        "tradeoff": "Simpler locally but not cloud native.",
                        "reason_not_selected": "Does not match deployment.",
                    }
                ],
            }
        ],
        "socratic_clarifying_questions": [
            {
                "question_text": "Which workflow should be demonstrated?",
                "why_this_matters": "It determines the first milestone.",
                "suggested_options": [
                    {"label": "Study", "impact": "Shows learning support."},
                    {"label": "Plan", "impact": "Shows project support."},
                ],
            }
        ],
        "step_by_step_execution_roadmap": [
            {
                "phase_name": "Phase 1",
                "objective": "Create the contract.",
                "expected_deliverable": "A validated model.",
                "micro_tasks": [
                    {
                        "task_description": "Write the schema.",
                        "complexity_level": "Low",
                        "verification_steps": ["Run the focused test."],
                    }
                ],
            }
        ],
        "diagnostic_warnings": [
            {
                "affected_component": "Persistence",
                "severity": "Medium",
                "risk_identified": "Unbounded reads increase cost.",
                "preventative_guidance": "Require a strict page limit.",
            }
        ],
    }


def legacy_document() -> dict[str, object]:
    return {
        "created_at": NOW,
        "originating_session_id": "session-1",
        "user_id": "user-1",
        "model_name": "gemini-3.6-flash",
        "schema_version": "2.0",
        "blueprint": blueprint_payload(),
    }


def current_contract_document() -> dict[str, object]:
    document = legacy_document()
    document.update(
        {
            "artifact_contract_version": "1.0",
            "artifact_type": "synthesis_blueprint",
            "originating_turn_id": "turn-1",
            "parent_artifact_id": None,
            "feedback_counts": {
                "accepted": 0,
                "rejected": 0,
                "edited": 0,
            },
            "adaptation_receipts": [],
            "applied_feedback_ids": [],
        }
    )
    return document


def schema_v1_document() -> dict[str, object]:
    document = legacy_document()
    document["schema_version"] = "1.0"
    blueprint = document["blueprint"]
    assert isinstance(blueprint, dict)
    blueprint["architectural_decisions_and_feedback"] = blueprint.pop(
        "architectural_decisions"
    )
    return document


@dataclass
class FakeArtifactDatabase:
    page: object
    detail_record: object
    list_calls: list[tuple[str, int, str | None]] = field(default_factory=list)
    detail_calls: list[tuple[str, str]] = field(default_factory=list)

    async def list_blueprint_documents(
        self,
        project_id: str,
        *,
        limit: int,
        before: str | None,
    ) -> object:
        self.list_calls.append((project_id, limit, before))
        return self.page

    async def get_blueprint_document(
        self,
        project_id: str,
        blueprint_id: str,
    ) -> object:
        self.detail_calls.append((project_id, blueprint_id))
        return self.detail_record


@pytest.mark.asyncio
async def test_service_excludes_partial_contract_artifact_from_list_but_detail_remains_readable(
) -> None:
    from artifact_read_service import (
        ArtifactReadService,
        GetBlueprintArtifactCommand,
        ListBlueprintArtifactsCommand,
    )
    from database import BlueprintDocumentPage, BlueprintDocumentRecord

    record = BlueprintDocumentRecord(
        artifact_id="blueprint-1",
        document=legacy_document(),
    )
    database = FakeArtifactDatabase(
        page=BlueprintDocumentPage(records=(record,), next_before=None),
        detail_record=record,
    )
    service = ArtifactReadService(database=database)

    listing = await service.list_blueprints(
        ListBlueprintArtifactsCommand(
            project_id="project-1",
            limit=20,
            before=None,
        )
    )
    detail = await service.get_blueprint(
        GetBlueprintArtifactCommand(
            project_id="project-1",
            blueprint_id="blueprint-1",
        )
    )

    assert listing.next_before is None
    assert listing.artifacts == []
    assert detail.adaptations == []
    assert detail.applied_feedback_ids == []
    assert [target.target_kind for target in detail.feedback_targets] == [
        "whole_blueprint",
        "architectural_decision",
        "socratic_question",
        "roadmap_milestone",
        "diagnostic_warning",
    ]
    assert len({target.target_id for target in detail.feedback_targets}) == 5
    assert database.list_calls == [("project-1", 20, None)]
    assert database.detail_calls == [("project-1", "blueprint-1")]


@pytest.mark.asyncio
async def test_service_projects_only_verified_canonical_adaptations() -> None:
    from artifact_read_service import (
        ArtifactReadService,
        GetBlueprintArtifactCommand,
    )
    from database import BlueprintDocumentPage, BlueprintDocumentRecord

    document = legacy_document()
    document.update(
        {
            "artifact_contract_version": "1.0",
            "artifact_type": "synthesis_blueprint",
            "originating_turn_id": "turn-1",
            "parent_artifact_id": "blueprint-0",
            "feedback_counts": {
                "accepted": 1,
                "rejected": 2,
                "edited": 3,
            },
            "adaptation_receipts": [
                {
                    "signal_id": "planning_granularity--signal-1",
                    "category": "planning_granularity",
                    "value": "micro_steps",
                    "source_event_id": (
                        "planning_granularity--signal-1--approved"
                    ),
                    "status": "provided_to_model",
                }
            ],
            "applied_feedback_ids": ["feedback-1"],
        }
    )
    record = BlueprintDocumentRecord(
        artifact_id="blueprint-2",
        document=document,
    )
    database = FakeArtifactDatabase(
        page=BlueprintDocumentPage(records=(), next_before=None),
        detail_record=record,
    )

    detail = await ArtifactReadService(database=database).get_blueprint(
        GetBlueprintArtifactCommand(
            project_id="project-1",
            blueprint_id="blueprint-2",
        )
    )

    assert detail.metadata.originating_turn_id == "turn-1"
    assert detail.metadata.parent_artifact_id == "blueprint-0"
    assert detail.metadata.feedback_counts.model_dump() == {
        "accepted": 1,
        "rejected": 2,
        "edited": 3,
    }
    assert detail.metadata.adaptation_categories == ["planning_granularity"]
    assert detail.adaptations[0].signal_id == "planning_granularity--signal-1"
    assert detail.applied_feedback_ids == ["feedback-1"]
    assert "user_id" not in detail.model_dump()
    assert "model_name" not in detail.model_dump()


@pytest.mark.asyncio
async def test_service_rejects_corrupt_stored_artifact() -> None:
    from artifact_read_service import (
        ArtifactReadService,
        ArtifactReadStateError,
        GetBlueprintArtifactCommand,
    )
    from database import BlueprintDocumentPage, BlueprintDocumentRecord

    corrupt = legacy_document()
    corrupt["blueprint"] = {"private": "malformed"}
    record = BlueprintDocumentRecord(
        artifact_id="blueprint-1",
        document=corrupt,
    )
    database = FakeArtifactDatabase(
        page=BlueprintDocumentPage(records=(), next_before=None),
        detail_record=record,
    )

    with pytest.raises(ArtifactReadStateError):
        await ArtifactReadService(database=database).get_blueprint(
            GetBlueprintArtifactCommand(
                project_id="project-1",
                blueprint_id="blueprint-1",
            )
        )


@pytest.mark.asyncio
async def test_service_omits_schema_v1_artifacts_and_preserves_cursor() -> None:
    from artifact_read_service import (
        ArtifactReadService,
        ListBlueprintArtifactsCommand,
    )
    from database import BlueprintDocumentPage, BlueprintDocumentRecord

    current_record = BlueprintDocumentRecord(
        artifact_id="blueprint-2",
        document=current_contract_document(),
    )
    legacy_record = BlueprintDocumentRecord(
        artifact_id="blueprint-1",
        document=schema_v1_document(),
    )
    database = FakeArtifactDatabase(
        page=BlueprintDocumentPage(
            records=(current_record, legacy_record),
            next_before="blueprint-1",
        ),
        detail_record=current_record,
    )

    listing = await ArtifactReadService(database=database).list_blueprints(
        ListBlueprintArtifactsCommand(
            project_id="project-1",
            limit=2,
            before=None,
        )
    )

    assert [
        artifact.reference.artifact_id for artifact in listing.artifacts
    ] == ["blueprint-2"]
    assert listing.next_before == "blueprint-1"


@pytest.mark.asyncio
async def test_service_rejects_direct_schema_v1_detail_explicitly() -> None:
    from artifact_read_service import (
        ArtifactReadService,
        GetBlueprintArtifactCommand,
    )
    from database import BlueprintDocumentPage, BlueprintDocumentRecord

    legacy_record = BlueprintDocumentRecord(
        artifact_id="blueprint-1",
        document=schema_v1_document(),
    )
    database = FakeArtifactDatabase(
        page=BlueprintDocumentPage(records=(), next_before=None),
        detail_record=legacy_record,
    )

    with pytest.raises(
        RuntimeError,
        match="unsupported schema version",
    ):
        await ArtifactReadService(database=database).get_blueprint(
            GetBlueprintArtifactCommand(
                project_id="project-1",
                blueprint_id="blueprint-1",
            )
        )
