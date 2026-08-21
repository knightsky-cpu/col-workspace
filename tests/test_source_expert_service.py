import asyncio
import json

import pytest
from google.genai import types


class FakeAsyncChat:
    def __init__(
        self,
        *,
        response: types.GenerateContentResponse | None = None,
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.response = response
        self.error = error
        self.delay = delay
        self.messages: list[str] = []

    async def send_message(
        self,
        message: str,
    ) -> types.GenerateContentResponse:
        self.messages.append(message)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class FakeAsyncChats:
    def __init__(self, *chats: FakeAsyncChat) -> None:
        self.chats = list(chats)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> FakeAsyncChat:
        self.calls.append(kwargs)
        assert self.chats
        return self.chats.pop(0)


class FakeClient:
    def __init__(self, *chats: FakeAsyncChat) -> None:
        chats = FakeAsyncChats(*chats)
        self.aio = type("FakeAio", (), {"chats": chats})()


def grounded_retrieval_response() -> types.GenerateContentResponse:
    statement = "Example Domain is reserved for documentation."
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=statement)],
                ),
                url_context_metadata=types.UrlContextMetadata(
                    url_metadata=[
                        types.UrlMetadata(
                            retrieved_url="https://example.com/",
                            url_retrieval_status=(
                                types.UrlRetrievalStatus.
                                URL_RETRIEVAL_STATUS_SUCCESS
                            ),
                        )
                    ]
                ),
                grounding_metadata=types.GroundingMetadata(
                    grounding_chunks=[
                        types.GroundingChunk(
                            web=types.GroundingChunkWeb(
                                uri="https://example.com/",
                                title="Example Domain",
                            )
                        )
                    ],
                    grounding_supports=[
                        types.GroundingSupport(
                            segment=types.Segment(text=statement),
                            grounding_chunk_indices=[0],
                        )
                    ],
                ),
            )
        ]
    )


def structured_classification_response(
    *,
    statement: str = "Example Domain is reserved for documentation.",
) -> types.GenerateContentResponse:
    draft = {
        "facts": [{"text": statement, "source_ids": ["source-1"]}],
        "requirements": [],
        "constraints": [],
        "assumptions": [],
        "open_questions": [],
    }
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps(draft))],
                )
            )
        ]
    )


@pytest.mark.asyncio
async def test_source_service_retrieves_then_classifies_grounded_evidence(
) -> None:
    from expert_contracts import ExpertStatus
    from source_expert import SourceExpertInput
    from source_expert_service import SourceExpertService

    retrieval_chat = FakeAsyncChat(response=grounded_retrieval_response())
    classification_chat = FakeAsyncChat(
        response=structured_classification_response()
    )
    client = FakeClient(retrieval_chat, classification_chat)
    service = SourceExpertService(client=client)
    request = SourceExpertInput(
        objective="Extract the documented purpose.",
        urls=("https://example.com/",),
        constraints=("Separate source facts from assumptions.",),
    )

    result = await service.analyze(request)

    assert result.status is ExpertStatus.COMPLETED
    assert len(client.aio.chats.calls) == 2
    retrieval_config = client.aio.chats.calls[0]["config"]
    assert isinstance(retrieval_config, types.GenerateContentConfig)
    assert retrieval_config.response_mime_type is None
    assert retrieval_config.response_json_schema is None
    assert len(retrieval_config.tools or ()) == 1
    assert retrieval_config.tools[0].url_context is not None
    assert retrieval_config.tools[0].google_search is None
    classification_config = client.aio.chats.calls[1]["config"]
    assert isinstance(classification_config, types.GenerateContentConfig)
    assert classification_config.response_mime_type == "application/json"
    assert classification_config.response_schema is None
    assert not classification_config.tools
    assert len(retrieval_chat.messages) == 1
    retrieval_prompt = json.loads(retrieval_chat.messages[0])
    assert retrieval_prompt == {
        "objective": "Extract the documented purpose.",
        "sources": [
            {"source_id": "source-1", "url": "https://example.com/"}
        ],
        "constraints": ["Separate source facts from assumptions."],
    }
    assert len(classification_chat.messages) == 1
    classification_prompt = json.loads(classification_chat.messages[0])
    assert classification_prompt["grounded_statements"] == [
        {
            "text": "Example Domain is reserved for documentation.",
            "source_ids": ["source-1"],
        }
    ]


@pytest.mark.asyncio
async def test_source_service_rejects_classifier_statement_not_exactly_grounded(
) -> None:
    from expert_contracts import ExpertStatus
    from source_expert import SourceExpertInput
    from source_expert_service import (
        SourceExpertService,
        SourceExpertServiceError,
    )

    service = SourceExpertService(
        client=FakeClient(
            FakeAsyncChat(response=grounded_retrieval_response()),
            FakeAsyncChat(
                response=structured_classification_response(
                    statement="Example Domain"
                )
            ),
        )
    )

    with pytest.raises(SourceExpertServiceError) as exc_info:
        await service.analyze(
            SourceExpertInput(
                objective="Extract the documented purpose.",
                urls=("https://example.com/",),
            )
        )

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT
    assert exc_info.value.__cause__ is None


@pytest.mark.asyncio
async def test_source_service_uses_provider_safe_json_schema() -> None:
    from source_expert import SourceExpertDraft, SourceExpertInput
    from source_expert_service import SourceExpertService
    from synthesis_schema import adapt_schema_for_gemini

    client = FakeClient(
        FakeAsyncChat(response=grounded_retrieval_response()),
        FakeAsyncChat(response=structured_classification_response()),
    )
    service = SourceExpertService(client=client)

    await service.analyze(
        SourceExpertInput(
            objective="Extract the documented purpose.",
            urls=("https://example.com/",),
        )
    )

    config = client.aio.chats.calls[1]["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.response_schema is None
    assert config.response_json_schema == adapt_schema_for_gemini(
        SourceExpertDraft.model_json_schema()
    )
    serialized = json.dumps(config.response_json_schema, sort_keys=True)
    assert '"pattern"' not in serialized
    assert '"maxItems"' not in serialized


@pytest.mark.asyncio
async def test_source_service_translates_provider_failure_without_logging_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from expert_contracts import ExpertStatus
    from source_expert import SourceExpertInput
    from source_expert_service import (
        SourceExpertService,
        SourceExpertServiceError,
    )

    provider_error = RuntimeError(
        "provider echoed https://private.example.net/user-content"
    )
    service = SourceExpertService(
        client=FakeClient(FakeAsyncChat(error=provider_error))
    )
    request = SourceExpertInput(
        objective="Inspect the source.",
        urls=("https://example.com/",),
    )

    with pytest.raises(SourceExpertServiceError) as exc_info:
        await service.analyze(request)

    assert exc_info.value.status is ExpertStatus.UNAVAILABLE
    assert str(exc_info.value) == "Source Expert execution failed."
    assert exc_info.value.__cause__ is provider_error
    assert "private.example.net" not in caplog.text
    assert "user-content" not in caplog.text


@pytest.mark.asyncio
async def test_source_service_translates_timeout() -> None:
    from expert_contracts import ExpertStatus
    from source_expert import SourceExpertInput
    from source_expert_service import (
        SourceExpertService,
        SourceExpertServiceError,
    )

    service = SourceExpertService(
        client=FakeClient(
            FakeAsyncChat(
                response=grounded_retrieval_response(),
                delay=0.05,
            )
        ),
        timeout_seconds=0.001,
    )
    request = SourceExpertInput(
        objective="Inspect the source.",
        urls=("https://example.com/",),
    )

    with pytest.raises(SourceExpertServiceError) as exc_info:
        await service.analyze(request)

    assert exc_info.value.status is ExpertStatus.TIMED_OUT
    assert isinstance(exc_info.value.__cause__, TimeoutError)


@pytest.mark.asyncio
async def test_source_service_total_timeout_includes_classification() -> None:
    from expert_contracts import ExpertStatus
    from source_expert import SourceExpertInput
    from source_expert_service import (
        SourceExpertService,
        SourceExpertServiceError,
    )

    service = SourceExpertService(
        client=FakeClient(
            FakeAsyncChat(response=grounded_retrieval_response()),
            FakeAsyncChat(
                response=structured_classification_response(),
                delay=0.05,
            ),
        ),
        timeout_seconds=0.001,
    )

    with pytest.raises(SourceExpertServiceError) as exc_info:
        await service.analyze(
            SourceExpertInput(
                objective="Inspect the source.",
                urls=("https://example.com/",),
            )
        )

    assert exc_info.value.status is ExpertStatus.TIMED_OUT
    assert isinstance(exc_info.value.__cause__, TimeoutError)


@pytest.mark.asyncio
async def test_source_service_translates_classifier_failure_without_data_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from expert_contracts import ExpertStatus
    from source_expert import SourceExpertInput
    from source_expert_service import (
        SourceExpertService,
        SourceExpertServiceError,
    )

    classifier_error = RuntimeError(
        "provider echoed https://private.example.net/generated-content"
    )
    service = SourceExpertService(
        client=FakeClient(
            FakeAsyncChat(response=grounded_retrieval_response()),
            FakeAsyncChat(error=classifier_error),
        )
    )

    with pytest.raises(SourceExpertServiceError) as exc_info:
        await service.analyze(
            SourceExpertInput(
                objective="Inspect the source.",
                urls=("https://example.com/",),
            )
        )

    assert exc_info.value.status is ExpertStatus.UNAVAILABLE
    assert exc_info.value.__cause__ is classifier_error
    assert "private.example.net" not in caplog.text
    assert "generated-content" not in caplog.text


@pytest.mark.asyncio
async def test_source_service_rejects_invalid_provider_evidence() -> None:
    from expert_contracts import ExpertStatus
    from source_expert import SourceExpertInput
    from source_expert_service import (
        SourceExpertService,
        SourceExpertServiceError,
    )

    response = grounded_retrieval_response()
    response.candidates[0].url_context_metadata = None
    service = SourceExpertService(
        client=FakeClient(FakeAsyncChat(response=response))
    )
    request = SourceExpertInput(
        objective="Inspect the source.",
        urls=("https://example.com/",),
    )

    with pytest.raises(SourceExpertServiceError) as exc_info:
        await service.analyze(request)

    assert exc_info.value.status is ExpertStatus.INVALID_OUTPUT
    assert exc_info.value.__cause__ is None
