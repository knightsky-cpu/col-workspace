from dataclasses import dataclass

import pytest

from speech_service import (
    CloudSpeechTranscriptionService,
    SpeechTranscriptionConfig,
    SpeechTranscriptionProviderError,
    UnsupportedAudioContentTypeError,
    load_speech_transcription_config,
    normalize_audio_content_type,
)


@dataclass
class FakeAutoDetectDecodingConfig:
    pass


@dataclass
class FakeRecognitionConfig:
    auto_decoding_config: FakeAutoDetectDecodingConfig
    language_codes: list[str]
    model: str


@dataclass
class FakeRecognizeRequest:
    recognizer: str
    config: FakeRecognitionConfig
    content: bytes


@dataclass
class FakeAlternative:
    transcript: str


@dataclass
class FakeResult:
    alternatives: list[FakeAlternative]


@dataclass
class FakeResponse:
    results: list[FakeResult]


class FakeSpeechV2Module:
    AutoDetectDecodingConfig = FakeAutoDetectDecodingConfig
    RecognitionConfig = FakeRecognitionConfig
    RecognizeRequest = FakeRecognizeRequest


class FakeSpeechClient:
    def __init__(self) -> None:
        self.requests: list[FakeRecognizeRequest] = []
        self.error: Exception | None = None

    def recognize(self, *, request: FakeRecognizeRequest) -> FakeResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return FakeResponse(
            results=[
                FakeResult(
                    alternatives=[
                        FakeAlternative(transcript="Recognized first sentence.")
                    ]
                ),
                FakeResult(
                    alternatives=[
                        FakeAlternative(transcript="Recognized second sentence.")
                    ]
                ),
            ]
        )


def test_normalize_audio_content_type_accepts_browser_webm_baseline() -> None:
    assert normalize_audio_content_type("audio/webm") == "audio/webm"
    assert (
        normalize_audio_content_type("audio/webm;codecs=opus")
        == "audio/webm;codecs=opus"
    )
    assert (
        normalize_audio_content_type("audio/webm; codecs=opus")
        == "audio/webm;codecs=opus"
    )


def test_normalize_audio_content_type_rejects_unsupported_mime() -> None:
    with pytest.raises(UnsupportedAudioContentTypeError):
        normalize_audio_content_type("audio/wav")


def test_load_speech_transcription_config_uses_stt_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-1")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setenv("AGENT_COL_STT_LANGUAGE_CODES", "en-US,es-US")
    monkeypatch.setenv("AGENT_COL_STT_MODEL", "latest_short")

    config = load_speech_transcription_config()

    assert config == SpeechTranscriptionConfig(
        project_id="project-1",
        location="us-central1",
        language_codes=("en-US", "es-US"),
        model="latest_short",
    )


@pytest.mark.asyncio
async def test_cloud_speech_service_builds_v2_recognize_request() -> None:
    client = FakeSpeechClient()
    service = CloudSpeechTranscriptionService(
        client_factory=lambda: client,
        speech_v2_module=FakeSpeechV2Module,
        config_loader=lambda: SpeechTranscriptionConfig(
            project_id="project-1",
            location="global",
            language_codes=("en-US",),
            model="latest_short",
        ),
    )

    transcript = await service.transcribe(
        audio=b"webm audio",
        content_type="audio/webm;codecs=opus",
    )

    assert transcript == "Recognized first sentence. Recognized second sentence."
    assert client.requests == [
        FakeRecognizeRequest(
            recognizer="projects/project-1/locations/global/recognizers/_",
            config=FakeRecognitionConfig(
                auto_decoding_config=FakeAutoDetectDecodingConfig(),
                language_codes=["en-US"],
                model="latest_short",
            ),
            content=b"webm audio",
        )
    ]


@pytest.mark.asyncio
async def test_cloud_speech_service_wraps_provider_errors() -> None:
    client = FakeSpeechClient()
    client.error = RuntimeError("private provider internals")
    service = CloudSpeechTranscriptionService(
        client_factory=lambda: client,
        speech_v2_module=FakeSpeechV2Module,
        config_loader=lambda: SpeechTranscriptionConfig(
            project_id="project-1",
            location="global",
            language_codes=("en-US",),
            model="latest_short",
        ),
    )

    with pytest.raises(SpeechTranscriptionProviderError) as exc_info:
        await service.transcribe(
            audio=b"webm audio",
            content_type="audio/webm;codecs=opus",
        )

    assert "private provider internals" not in str(exc_info.value)
