from collections.abc import Iterable
from dataclasses import dataclass

from memory_policy import (
    IDENTITY_CONTEXT_INSTRUCTIONS,
    IdentityContextPolicy,
    PREFERENCE_VALUES_BY_CATEGORY,
    PreferencePolicy,
    memory_signal_sort_key,
)
from schemas import (
    ActiveMemorySignal,
    AdaptationReceipt,
    CollaborationProfile,
)


@dataclass(frozen=True)
class RenderedMemoryContext:
    instruction_text: str
    adaptations: tuple[AdaptationReceipt, ...]


class MemoryContextRenderer:
    @staticmethod
    def render(profile: CollaborationProfile) -> RenderedMemoryContext:
        if not isinstance(profile, CollaborationProfile):
            raise TypeError("profile must be a CollaborationProfile.")
        sections: list[str] = []
        receipts: list[AdaptationReceipt] = []

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
        signals: Iterable[ActiveMemorySignal],
        receipts: list[AdaptationReceipt],
    ) -> list[str]:
        lines: list[str] = []
        for signal in sorted(
            signals,
            key=lambda item: memory_signal_sort_key(item.category),
        ):
            if signal.category in PREFERENCE_VALUES_BY_CATEGORY:
                instruction = PreferencePolicy.instruction(
                    signal.category,
                    signal.value,
                )
            elif signal.category in IDENTITY_CONTEXT_INSTRUCTIONS:
                instruction = IdentityContextPolicy.instruction(
                    signal.category,
                    signal.value,
                )
            else:
                raise ValueError("Unknown active memory category.")

            if isinstance(signal.value, list):
                formatted_value = f"[{', '.join(signal.value)}]"
            else:
                formatted_value = signal.value
            lines.append(
                f"- {signal.category}={formatted_value}: {instruction}"
            )
            receipts.append(
                AdaptationReceipt(
                    signal_id=signal.signal_id,
                    category=signal.category,
                    value=signal.value,
                    source_event_id=signal.source_event_id,
                    status="provided_to_model",
                )
            )
        return lines
