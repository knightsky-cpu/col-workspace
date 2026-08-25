"""Deterministic governed-memory projection for synthesis."""

from dataclasses import dataclass
from typing import Literal, cast

from memory_policy import memory_instruction_for_policy
from schemas import (
    ActiveMemorySignal,
    ActiveMemorySignalV2,
    AdaptationReceipt,
    AdaptationReceiptV2,
    CollaborationProfile,
    CollaborationProfileV2,
    SynthesisBlueprint,
    VersionedActiveMemorySignal,
    VersionedAdaptationReceipt,
    VersionedCollaborationProfile,
)


PlanningGranularity = Literal["milestones", "tasks", "micro_steps"]


class SynthesisPersonalizationError(RuntimeError):
    """Raised when generated personalization lacks trusted provenance."""


@dataclass(frozen=True, slots=True)
class SynthesisPersonalizationInstruction:
    category: Literal["planning_granularity"]
    value: PlanningGranularity
    instruction: str


@dataclass(frozen=True, slots=True)
class SynthesisPersonalizationProjection:
    instructions: tuple[SynthesisPersonalizationInstruction, ...]
    supplied_signals: tuple[VersionedActiveMemorySignal, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.instructions, tuple)
            or not isinstance(self.supplied_signals, tuple)
            or len(self.instructions) != len(self.supplied_signals)
            or len(self.instructions) > 1
        ):
            raise SynthesisPersonalizationError(
                "Synthesis personalization projection is invalid."
            )
        if not self.instructions:
            return
        instruction = self.instructions[0]
        signal = self.supplied_signals[0]
        try:
            expected_instruction = memory_instruction_for_policy(
                signal.policy_version,
                "planning_granularity",
                instruction.value,
            )
        except ValueError as exc:
            raise SynthesisPersonalizationError(
                "Synthesis personalization projection is invalid."
            ) from exc
        if (
            not isinstance(
                instruction,
                SynthesisPersonalizationInstruction,
            )
            or not isinstance(
                signal,
                (ActiveMemorySignal, ActiveMemorySignalV2),
            )
            or instruction.category != "planning_granularity"
            or signal.category != "planning_granularity"
            or instruction.value != signal.value
            or expected_instruction is None
            or instruction.instruction != expected_instruction
        ):
            raise SynthesisPersonalizationError(
                "Synthesis personalization projection is invalid."
            )

    @property
    def model_context(self) -> dict[str, object]:
        return {
            item.category: {
                "value": item.value,
                "instruction": item.instruction,
            }
            for item in self.instructions
        }


class SynthesisPersonalizationAdapter:
    """Project only synthesis-approved governed memory."""

    @staticmethod
    def project(
        profile: VersionedCollaborationProfile,
    ) -> SynthesisPersonalizationProjection:
        if not isinstance(
            profile,
            (CollaborationProfile, CollaborationProfileV2),
        ):
            raise TypeError("profile must be a CollaborationProfile.")
        signal = profile.active_preferences.get("planning_granularity")
        if signal is None:
            return SynthesisPersonalizationProjection((), ())
        value = cast(PlanningGranularity, signal.value)
        instruction = memory_instruction_for_policy(
            signal.policy_version,
            "planning_granularity",
            value,
        )
        return SynthesisPersonalizationProjection(
            instructions=(
                SynthesisPersonalizationInstruction(
                    category="planning_granularity",
                    value=value,
                    instruction=instruction,
                ),
            ),
            supplied_signals=(signal,),
        )

    @staticmethod
    def validate_and_derive_receipts(
        projection: SynthesisPersonalizationProjection,
        blueprint: SynthesisBlueprint,
    ) -> tuple[VersionedAdaptationReceipt, ...]:
        if not isinstance(projection, SynthesisPersonalizationProjection):
            raise TypeError(
                "projection must be a SynthesisPersonalizationProjection."
            )
        if not isinstance(blueprint, SynthesisBlueprint):
            raise TypeError("blueprint must be a SynthesisBlueprint.")
        signal_by_category = {
            signal.category: signal
            for signal in projection.supplied_signals
        }
        receipts: list[VersionedAdaptationReceipt] = []
        seen_categories: set[str] = set()
        for adaptation in blueprint.personalization_trace.adaptations:
            if adaptation.profile_key in seen_categories:
                raise SynthesisPersonalizationError(
                    "Blueprint contains a duplicate synthesis adaptation."
                )
            seen_categories.add(adaptation.profile_key)
            signal = signal_by_category.get(adaptation.profile_key)
            if signal is None:
                raise SynthesisPersonalizationError(
                    "Blueprint claims an unsupplied synthesis adaptation."
                )
            receipt_fields = {
                "signal_id": signal.signal_id,
                "category": signal.category,
                "value": signal.value,
                "source_event_id": signal.source_event_id,
                "status": "provided_to_model",
            }
            if isinstance(signal, ActiveMemorySignalV2):
                receipts.append(AdaptationReceiptV2(**receipt_fields))
            else:
                receipts.append(AdaptationReceipt(**receipt_fields))
        return tuple(receipts)
