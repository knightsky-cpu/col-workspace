import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from preference_learning import (
    PreferenceHypothesis,
    PreferenceObservation,
    derive_preference_hypothesis_id,
    merge_observation_into_hypothesis,
    should_surface_hypothesis,
)
from schemas import ChatMessageText, IdentifierStr, StrictModel


logger = logging.getLogger(__name__)


class PreferenceLearningCommand(StrictModel):
    user_id: IdentifierStr
    project_id: IdentifierStr
    session_id: IdentifierStr
    turn_id: IdentifierStr
    source_message_id: IdentifierStr
    user_message: ChatMessageText
    model_response: ChatMessageText


class PreferenceLearningResult(StrictModel):
    observation: PreferenceObservation | None = None
    hypothesis: PreferenceHypothesis | None = None
    surfaced_hypothesis: PreferenceHypothesis | None = None


class PreferenceObservationExtractor(Protocol):
    async def extract(
        self,
        command: PreferenceLearningCommand,
    ) -> object | None: ...


class DeterministicPreferenceObservationExtractor:
    """Recognizes narrow explicit style corrections without background mining."""

    async def extract(
        self,
        command: PreferenceLearningCommand,
    ) -> object | None:
        normalized = re.sub(r"\s+", " ", command.user_message).strip().lower()
        concise_markers = (
            "too long",
            "be shorter",
            "shorter",
            "more concise",
            "concise please",
            "brief",
        )
        if any(marker in normalized for marker in concise_markers):
            return {
                "category": "response_length",
                "canonical_value": "concise",
                "evidence_kind": (
                    "user_correction"
                    if "too long" in normalized or "shorter" in normalized
                    else "repeated_collaboration_preference"
                ),
                "evidence_summary": (
                    "User asked for a shorter or more concise response."
                ),
                "confidence_delta": 0.35,
            }
        return None


class PreferenceLearningService:
    """Captures bounded, non-authoritative preference evidence."""

    def __init__(
        self,
        *,
        database: object,
        extractor: PreferenceObservationExtractor | None = None,
        clock: Callable[[], datetime],
    ) -> None:
        self._database = database
        self._extractor = (
            extractor or DeterministicPreferenceObservationExtractor()
        )
        self._clock = clock

    async def capture(
        self,
        command: PreferenceLearningCommand,
    ) -> PreferenceLearningResult:
        try:
            extracted = await self._extractor.extract(command)
        except Exception as exc:
            logger.error(
                "Preference learning extraction failed (%s).",
                type(exc).__name__,
            )
            return PreferenceLearningResult()
        if extracted is None:
            return PreferenceLearningResult()

        now = self._clock()
        try:
            observation = PreferenceObservation.model_validate(
                {
                    "observation_id": f"pref-obs--{command.turn_id}",
                    "user_id": command.user_id,
                    "project_id": command.project_id,
                    "session_id": command.session_id,
                    "source_turn_id": command.turn_id,
                    "source_message_id": command.source_message_id,
                    "created_at": now,
                }
                | dict(extracted)
            )
            hypothesis_id = derive_preference_hypothesis_id(observation)
            existing = await self._database.get_preference_hypothesis(
                command.user_id,
                command.project_id,
                hypothesis_id,
            )
            hypothesis = merge_observation_into_hypothesis(
                existing,
                observation,
                now=now,
            )
            await self._database.save_preference_observation(observation)
            if hypothesis is not None:
                await self._database.save_preference_hypothesis(hypothesis)
        except Exception as exc:
            logger.error(
                "Preference learning capture failed (%s).",
                type(exc).__name__,
            )
            return PreferenceLearningResult()

        surfaced = (
            hypothesis
            if hypothesis is not None
            and should_surface_hypothesis(hypothesis, now=now)
            else None
        )
        return PreferenceLearningResult(
            observation=observation,
            hypothesis=hypothesis,
            surfaced_hypothesis=surfaced,
        )
