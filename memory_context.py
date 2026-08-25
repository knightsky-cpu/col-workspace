from collections.abc import Iterable
from dataclasses import dataclass

from memory_policy import (
    memory_instruction_for_policy,
    memory_signal_sort_key_for_policy,
)
from schemas import (
    ActiveMemorySignal,
    ActiveMemorySignalV2,
    AdaptationReceipt,
    AdaptationReceiptV2,
    CollaborationProfile,
    CollaborationProfileV2,
    VersionedActiveMemorySignal,
    VersionedAdaptationReceipt,
    VersionedCollaborationProfile,
)


@dataclass(frozen=True)
class RenderedMemoryContext:
    instruction_text: str
    adaptations: tuple[VersionedAdaptationReceipt, ...]


class MemoryContextRenderer:
    @staticmethod
    def _plain_value(value: object) -> object:
        if isinstance(value, list):
            return [MemoryContextRenderer._plain_value(item) for item in value]
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="python")
        return value

    @staticmethod
    def render(
        profile: VersionedCollaborationProfile,
    ) -> RenderedMemoryContext:
        if not isinstance(
            profile,
            (CollaborationProfile, CollaborationProfileV2),
        ):
            raise TypeError("profile must be a CollaborationProfile.")
        sections: list[str] = []
        receipts: list[VersionedAdaptationReceipt] = []

        identity_lines = MemoryContextRenderer._render_signals(
            profile.identity_context.values(),
            receipts,
        )
        if identity_lines:
            sections.append(
                "\n".join(
                    (
                        "[APPROVED_IDENTITY_CONTEXT]",
                        *identity_lines,
                        "[/APPROVED_IDENTITY_CONTEXT]",
                    )
                )
            )

        preference_lines = MemoryContextRenderer._render_signals(
            profile.active_preferences.values(),
            receipts,
        )
        if preference_lines:
            sections.append(
                "\n".join(
                    (
                        "[APPROVED_COLLABORATION_PREFERENCES]",
                        *preference_lines,
                        "[/APPROVED_COLLABORATION_PREFERENCES]",
                    )
                )
            )

        return RenderedMemoryContext(
            instruction_text="\n".join(sections),
            adaptations=tuple(receipts),
        )

    @staticmethod
    def _render_signals(
        signals: Iterable[VersionedActiveMemorySignal],
        receipts: list[VersionedAdaptationReceipt],
    ) -> list[str]:
        lines: list[str] = []
        for signal in sorted(
            signals,
            key=lambda item: memory_signal_sort_key_for_policy(
                "2.0",
                item.category,
            ),
        ):
            plain_value = MemoryContextRenderer._plain_value(signal.value)
            instruction = memory_instruction_for_policy(
                signal.policy_version,
                signal.category,
                plain_value,
            )

            if isinstance(plain_value, list):
                formatted_items = []
                for item in plain_value:
                    if isinstance(item, str):
                        formatted_items.append(item)
                    elif isinstance(item, dict):
                        formatted_items.append(
                            ":".join(str(value) for value in item.values())
                        )
                    else:
                        formatted_items.append(str(item))
                formatted_value = f"[{', '.join(formatted_items)}]"
            else:
                formatted_value = plain_value
            lines.append(
                f"- {signal.category}={formatted_value}: {instruction}"
            )
            receipt_fields = {
                "signal_id": signal.signal_id,
                "category": signal.category,
                "value": plain_value,
                "source_event_id": signal.source_event_id,
                "status": "provided_to_model",
            }
            if isinstance(signal, ActiveMemorySignalV2):
                receipts.append(AdaptationReceiptV2(**receipt_fields))
            else:
                receipts.append(AdaptationReceipt(**receipt_fields))
        return lines
