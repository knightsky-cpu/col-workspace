from datetime import UTC, datetime

import pytest


class FakeDatabase:
    def __init__(self) -> None:
        self.saved_observations = []
        self.saved_hypotheses = []
        self.hypothesis = None

    async def save_preference_observation(self, observation):
        self.saved_observations.append(observation)

    async def get_preference_hypothesis(self, user_id, project_id, hypothesis_id):
        return self.hypothesis

    async def save_preference_hypothesis(self, hypothesis):
        self.saved_hypotheses.append(hypothesis)
        self.hypothesis = hypothesis

    async def capture_preference_observation(
        self,
        observation,
        *,
        observed_at,
    ):
        from preference_learning import (
            PreferenceLearningCaptureOutcome,
            merge_observation_into_hypothesis,
            should_surface_hypothesis,
        )

        hypothesis = merge_observation_into_hypothesis(
            self.hypothesis,
            observation,
            now=observed_at,
        )
        self.saved_observations.append(observation)
        if hypothesis is not None:
            self.saved_hypotheses.append(hypothesis)
            self.hypothesis = hypothesis
        return PreferenceLearningCaptureOutcome(
            observation=observation,
            hypothesis=hypothesis,
            surfaced_hypothesis=(
                hypothesis
                if hypothesis is not None
                and should_surface_hypothesis(
                    hypothesis,
                    now=observed_at,
                )
                else None
            ),
        )


class FakeExtractor:
    async def extract(self, command):
        return {
            "category": "response_length",
            "canonical_value": "concise",
            "evidence_kind": "user_correction",
            "evidence_summary": "User corrected the answer to be shorter.",
            "confidence_delta": 0.35,
        }


def command(**updates: object):
    from preference_learning_service import PreferenceLearningCommand

    payload = {
        "user_id": "user-1",
        "project_id": "project-1",
        "session_id": "session-1",
        "turn_id": "turn-1",
        "source_message_id": "message-1",
        "user_message": "That was too long; be shorter.",
        "model_response": "A long response.",
    }
    payload.update(updates)
    return PreferenceLearningCommand(**payload)


@pytest.mark.asyncio
async def test_recognize_is_deterministic_and_does_not_persist() -> None:
    from preference_learning_service import PreferenceLearningService

    database = FakeDatabase()
    service = PreferenceLearningService(
        database=database,
        extractor=FakeExtractor(),
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )

    recognized = await service.recognize(command())

    assert recognized is not None
    assert recognized.observation_id == "pref-obs--turn-1"
    assert recognized.category == "response_length"
    assert database.saved_observations == []
    assert database.saved_hypotheses == []


@pytest.mark.asyncio
async def test_recognized_evidence_persists_without_running_extractor_again() -> None:
    from preference_learning_service import PreferenceLearningService

    class CountingExtractor(FakeExtractor):
        def __init__(self) -> None:
            self.calls = 0

        async def extract(self, capture_command):
            self.calls += 1
            if self.calls > 1:
                raise AssertionError("accepted evidence must not be re-extracted")
            return await super().extract(capture_command)

    database = FakeDatabase()
    extractor = CountingExtractor()
    service = PreferenceLearningService(
        database=database,
        extractor=extractor,
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )

    recognized = await service.recognize(command())
    result = await service.capture_observation_strict(recognized)

    assert extractor.calls == 1
    assert result.observation == recognized
    assert database.saved_observations == [recognized]


@pytest.mark.asyncio
async def test_capture_stores_validated_observation_without_active_memory():
    from preference_learning_service import PreferenceLearningService

    database = FakeDatabase()
    service = PreferenceLearningService(
        database=database,
        extractor=FakeExtractor(),
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )

    result = await service.capture(command())

    assert result.observation is not None
    assert result.observation.can_adapt_response is False
    assert database.saved_observations == [result.observation]
    assert result.surfaced_hypothesis is None


@pytest.mark.asyncio
async def test_capture_surfaces_only_confirmable_hypothesis_after_repeated_evidence():
    from preference_learning_service import PreferenceLearningService

    database = FakeDatabase()
    service = PreferenceLearningService(
        database=database,
        extractor=FakeExtractor(),
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )

    await service.capture(command())
    result = await service.capture(
        command(
            turn_id="turn-2",
            source_message_id="message-2",
            user_message="Again, concise please.",
        )
    )

    assert result.surfaced_hypothesis is not None
    assert (
        result.surfaced_hypothesis.authority
        == "non_authoritative_hypothesis"
    )
    assert result.surfaced_hypothesis.can_adapt_response is False


@pytest.mark.asyncio
async def test_extraction_failure_is_no_effect(caplog):
    from preference_learning_service import PreferenceLearningService

    class FailingExtractor:
        async def extract(self, command):
            raise RuntimeError("private response text")

    service = PreferenceLearningService(
        database=FakeDatabase(),
        extractor=FailingExtractor(),
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )
    caplog.set_level("ERROR", logger="preference_learning_service")

    result = await service.capture(
        command(
            user_id="google--109876543210",
            project_id="private-project",
            session_id="private-session",
            turn_id="private-turn",
            source_message_id="private-source-message",
            user_message="private user message",
            model_response="private model response",
        )
    )

    assert result.observation is None
    assert result.surfaced_hypothesis is None
    assert "RuntimeError" in caplog.text
    for private_marker in [
        "google--109876543210",
        "private-project",
        "private-session",
        "private-turn",
        "private-source-message",
        "private user message",
        "private model response",
        "private response text",
    ]:
        assert private_marker not in caplog.text


@pytest.mark.asyncio
async def test_capture_failure_logs_without_private_identifiers_or_content(
    caplog,
):
    from preference_learning_service import PreferenceLearningService

    class FailingDatabase(FakeDatabase):
        async def capture_preference_observation(
            self,
            observation,
            *,
            observed_at,
        ):
            raise RuntimeError("private database detail")

    service = PreferenceLearningService(
        database=FailingDatabase(),
        extractor=FakeExtractor(),
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )
    caplog.set_level("ERROR", logger="preference_learning_service")

    result = await service.capture(
        command(
            user_id="google--109876543210",
            project_id="private-project",
            session_id="private-session",
            turn_id="private-turn",
            source_message_id="private-source-message",
            user_message="private user message",
            model_response="private model response",
        )
    )

    assert result.observation is None
    assert result.surfaced_hypothesis is None
    assert "RuntimeError" in caplog.text
    for private_marker in [
        "google--109876543210",
        "private-project",
        "private-session",
        "private-turn",
        "private-source-message",
        "private user message",
        "private model response",
        "private database detail",
    ]:
        assert private_marker not in caplog.text


@pytest.mark.asyncio
async def test_capture_strict_propagates_persistence_failure() -> None:
    from preference_learning_service import PreferenceLearningService

    class FailingDatabase(FakeDatabase):
        async def capture_preference_observation(
            self,
            observation,
            *,
            observed_at,
        ):
            raise RuntimeError("preference persistence unavailable")

    service = PreferenceLearningService(
        database=FailingDatabase(),
        extractor=FakeExtractor(),
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )

    with pytest.raises(
        RuntimeError,
        match="preference persistence unavailable",
    ):
        await service.capture_strict(command())


@pytest.mark.asyncio
async def test_default_extractor_detects_explicit_concise_correction():
    from preference_learning_service import PreferenceLearningService

    database = FakeDatabase()
    service = PreferenceLearningService(
        database=database,
        clock=lambda: datetime(2026, 8, 28, tzinfo=UTC),
    )

    result = await service.capture(command())

    assert result.observation is not None
    assert result.observation.category == "response_length"
    assert result.observation.canonical_value == "concise"
    assert result.observation.evidence_kind == "user_correction"
    assert result.observation.can_adapt_response is False
