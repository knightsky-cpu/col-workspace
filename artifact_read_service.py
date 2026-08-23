import hashlib
import logging
from dataclasses import dataclass

from pydantic import ValidationError

from database import BlueprintDocumentRecord, MemoryEngine
from schemas import (
    ARTIFACT_CONTRACT_VERSION,
    AdaptationReceipt,
    ArtifactFeedbackCounts,
    ArtifactFeedbackTarget,
    ArtifactReference,
    BlueprintArtifactDetailResponse,
    BlueprintArtifactListResponse,
    BlueprintArtifactMetadata,
    SynthesisBlueprint,
)


logger = logging.getLogger(__name__)


class ArtifactReadStateError(RuntimeError):
    """Raised when a stored artifact violates the supported read contract."""


class ArtifactReadUnsupportedSchemaError(RuntimeError):
    """Raised when a stored artifact uses a known unsupported schema."""


@dataclass(frozen=True, slots=True)
class ListBlueprintArtifactsCommand:
    project_id: str
    limit: int = 20
    before: str | None = None


@dataclass(frozen=True, slots=True)
class GetBlueprintArtifactCommand:
    project_id: str
    blueprint_id: str


@dataclass(frozen=True, slots=True)
class _ProjectedArtifact:
    metadata: BlueprintArtifactMetadata
    blueprint: SynthesisBlueprint
    adaptations: tuple[AdaptationReceipt, ...]
    applied_feedback_ids: tuple[str, ...]


class ArtifactReadService:
    """Project validated Firestore artifacts into bounded public read models."""

    def __init__(self, *, database: MemoryEngine) -> None:
        self._database = database

    async def list_blueprints(
        self,
        command: ListBlueprintArtifactsCommand,
    ) -> BlueprintArtifactListResponse:
        page = await self._database.list_blueprint_documents(
            command.project_id,
            limit=command.limit,
            before=command.before,
        )
        artifacts: list[BlueprintArtifactMetadata] = []
        for record in page.records:
            if self._uses_legacy_schema(record):
                continue
            artifacts.append(
                self._project_record(command.project_id, record).metadata
            )
        return BlueprintArtifactListResponse(
            artifacts=artifacts,
            next_before=page.next_before,
        )

    async def get_blueprint(
        self,
        command: GetBlueprintArtifactCommand,
    ) -> BlueprintArtifactDetailResponse:
        record = await self._database.get_blueprint_document(
            command.project_id,
            command.blueprint_id,
        )
        if self._uses_legacy_schema(record):
            raise ArtifactReadUnsupportedSchemaError(
                "Blueprint artifact uses an unsupported schema version."
            )
        projected = self._project_record(command.project_id, record)
        return BlueprintArtifactDetailResponse(
            metadata=projected.metadata,
            blueprint=projected.blueprint,
            feedback_targets=self._feedback_targets(
                record.artifact_id,
                projected.blueprint,
            ),
            adaptations=list(projected.adaptations),
            applied_feedback_ids=list(projected.applied_feedback_ids),
        )

    @staticmethod
    def _uses_legacy_schema(record: BlueprintDocumentRecord) -> bool:
        document = record.document
        return (
            isinstance(document, dict)
            and document.get("schema_version") == "1.0"
        )

    @classmethod
    def _project_record(
        cls,
        project_id: str,
        record: BlueprintDocumentRecord,
    ) -> _ProjectedArtifact:
        try:
            document = record.document
            if not isinstance(document, dict):
                raise ValueError("Stored artifact document must be a mapping.")
            contract_version = document.get("artifact_contract_version")
            if contract_version not in (None, ARTIFACT_CONTRACT_VERSION):
                raise ValueError("Stored artifact contract is unsupported.")
            artifact_type = document.get("artifact_type")
            if artifact_type not in (None, "synthesis_blueprint"):
                raise ValueError("Stored artifact type is unsupported.")

            blueprint = SynthesisBlueprint.model_validate(
                document.get("blueprint")
            )
            adaptations = tuple(
                AdaptationReceipt.model_validate(item)
                for item in cls._list_field(document, "adaptation_receipts")
            )
            adaptation_categories = list(
                dict.fromkeys(receipt.category for receipt in adaptations)
            )
            applied_feedback_ids = tuple(
                cls._string_list_field(document, "applied_feedback_ids")
            )
            feedback_counts = ArtifactFeedbackCounts.model_validate(
                document.get("feedback_counts", {})
            )
            reference = ArtifactReference(
                artifact_type="synthesis_blueprint",
                project_id=project_id,
                artifact_id=record.artifact_id,
                schema_version=document.get("schema_version"),
                display_label=(
                    blueprint.synthesized_conceptual_model.project_name
                ),
            )
            metadata = BlueprintArtifactMetadata(
                reference=reference,
                created_at=document.get("created_at"),
                originating_session_id=document.get(
                    "originating_session_id"
                ),
                originating_turn_id=document.get("originating_turn_id"),
                parent_artifact_id=document.get("parent_artifact_id"),
                feedback_counts=feedback_counts,
                adaptation_categories=adaptation_categories,
            )
        except (TypeError, ValueError, ValidationError) as exc:
            logger.error(
                "Stored blueprint artifact is invalid (%s).",
                type(exc).__name__,
            )
            raise ArtifactReadStateError(
                "Stored blueprint artifact is invalid."
            ) from exc
        return _ProjectedArtifact(
            metadata=metadata,
            blueprint=blueprint,
            adaptations=adaptations,
            applied_feedback_ids=applied_feedback_ids,
        )

    @staticmethod
    def _list_field(
        document: dict[str, object],
        field_name: str,
    ) -> list[object]:
        value = document.get(field_name, [])
        if not isinstance(value, list):
            raise ValueError(f"Stored {field_name} must be a list.")
        return value

    @classmethod
    def _string_list_field(
        cls,
        document: dict[str, object],
        field_name: str,
    ) -> list[str]:
        values = cls._list_field(document, field_name)
        if not all(isinstance(value, str) for value in values):
            raise ValueError(f"Stored {field_name} must contain strings.")
        return values

    @classmethod
    def _feedback_targets(
        cls,
        artifact_id: str,
        blueprint: SynthesisBlueprint,
    ) -> list[ArtifactFeedbackTarget]:
        targets: list[ArtifactFeedbackTarget] = [
            cls._target(
                artifact_id,
                "whole_blueprint",
                0,
                blueprint.synthesized_conceptual_model.project_name,
            )
        ]
        targets.extend(
            cls._target(
                artifact_id,
                "architectural_decision",
                index,
                decision.component_name,
            )
            for index, decision in enumerate(blueprint.architectural_decisions)
        )
        targets.extend(
            cls._target(
                artifact_id,
                "socratic_question",
                index,
                question.question_text,
            )
            for index, question in enumerate(
                blueprint.socratic_clarifying_questions
            )
        )
        targets.extend(
            cls._target(
                artifact_id,
                "roadmap_milestone",
                index,
                milestone.phase_name,
            )
            for index, milestone in enumerate(
                blueprint.step_by_step_execution_roadmap
            )
        )
        targets.extend(
            cls._target(
                artifact_id,
                "diagnostic_warning",
                index,
                warning.affected_component,
            )
            for index, warning in enumerate(blueprint.diagnostic_warnings)
        )
        return targets

    @classmethod
    def _target(
        cls,
        artifact_id: str,
        target_kind: str,
        index: int,
        display_label: str,
    ) -> ArtifactFeedbackTarget:
        digest = hashlib.sha256(
            f"{artifact_id}:{target_kind}:{index}".encode("utf-8")
        ).hexdigest()[:24]
        return ArtifactFeedbackTarget(
            target_id=f"target--{digest}",
            target_kind=target_kind,
            display_label=cls._bounded_label(display_label),
        )

    @staticmethod
    def _bounded_label(value: str) -> str:
        normalized = value.strip()
        if len(normalized) <= 160:
            return normalized
        return f"{normalized[:157]}..."
