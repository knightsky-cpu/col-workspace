from dataclasses import dataclass

import pytest

import speech_service
from speech_service import (
    CloudSpeechTranscriptionService,
    CloudTextToSpeechSynthesisService,
    SpeechTranscriptionConfig,
    SpeechTranscriptionProviderError,
    SpeechSynthesisChunkError,
    SpeechSynthesisConfig,
    SpeechSynthesisProviderError,
    chunk_text_for_speech,
    UnsupportedAudioContentTypeError,
    load_speech_transcription_config,
    load_speech_synthesis_config,
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


@dataclass
class FakeSynthesisInput:
    text: str


@dataclass
class FakeVoiceSelectionParams:
    language_code: str
    name: str


@dataclass
class FakeAudioConfig:
    audio_encoding: str
    speaking_rate: float


@dataclass
class FakeSynthesizeResponse:
    audio_content: bytes


class FakeAudioEncoding:
    MP3 = "MP3"


class FakeTextToSpeechModule:
    AudioConfig = FakeAudioConfig
    AudioEncoding = FakeAudioEncoding
    SynthesisInput = FakeSynthesisInput
    VoiceSelectionParams = FakeVoiceSelectionParams


class FakeTextToSpeechClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    def synthesize_speech(
        self,
        *,
        input: FakeSynthesisInput,
        voice: FakeVoiceSelectionParams,
        audio_config: FakeAudioConfig,
    ) -> FakeSynthesizeResponse:
        self.calls.append(
            {
                "input": input,
                "voice": voice,
                "audio_config": audio_config,
            }
        )
        if self.error is not None:
            raise self.error
        return FakeSynthesizeResponse(audio_content=b"mp3 bytes")


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


def test_load_speech_synthesis_config_uses_chirp_3_hd_baseline() -> None:
    config = load_speech_synthesis_config({})

    assert config == SpeechSynthesisConfig(
        language_code="en-GB",
        voice_name="en-GB-Chirp3-HD-Kore",
        speaking_rate=1.0,
        audio_content_type="audio/mpeg",
    )


def test_cloud_text_to_speech_service_maps_approved_male_voice() -> None:
    client = FakeTextToSpeechClient()
    service = CloudTextToSpeechSynthesisService(
        client_factory=lambda: client,
        texttospeech_module=FakeTextToSpeechModule,
    )

    service._synthesize_sync(
        "Canonical persisted answer.",
        0,
        1,
        voice_id="male",
    )

    assert client.calls[0]["voice"] == FakeVoiceSelectionParams(
        language_code="en-GB",
        name="en-GB-Chirp3-HD-Alnilam",
    )


def test_chunk_text_for_speech_preserves_text_under_byte_limit() -> None:
    text = (
        "First paragraph has one sentence. It has another sentence.\n\n"
        "Second paragraph includes technical terms like FastAPI and Firestore."
    )

    chunks = chunk_text_for_speech(text, max_bytes=70)

    assert "".join(chunks) == text
    assert all(len(chunk.encode("utf-8")) <= 70 for chunk in chunks)
    assert chunks == (
        "First paragraph has one sentence. It has another sentence.\n\n",
        "Second paragraph includes technical terms like FastAPI and Firestore.",
    )


def test_chunk_text_for_speech_splits_oversized_sentence_by_bytes() -> None:
    text = "alpha " * 20

    chunks = chunk_text_for_speech(text, max_bytes=25)

    assert "".join(chunks) == text
    assert len(chunks) > 1
    assert all(len(chunk.encode("utf-8")) <= 25 for chunk in chunks)


def test_chunk_text_for_speech_uses_latency_sized_first_chunk() -> None:
    text = (
        "Short first sentence. "
        "Second sentence can share a later playback chunk. "
        "Third sentence also belongs after the quick-start chunk."
    )

    chunks = chunk_text_for_speech(
        text,
        max_bytes=140,
        first_chunk_max_bytes=24,
        later_chunk_max_bytes=140,
    )

    assert chunks == (
        "Short first sentence. ",
        "Second sentence can share a later playback chunk. "
        "Third sentence also belongs after the quick-start chunk.",
    )
    assert "".join(chunks) == text
    assert all(len(chunk.encode("utf-8")) <= 140 for chunk in chunks)


def test_chunk_text_for_speech_uses_larger_later_chunks_for_oversized_text() -> None:
    text = "alpha " * 20

    chunks = chunk_text_for_speech(
        text,
        max_bytes=90,
        first_chunk_max_bytes=30,
        later_chunk_max_bytes=90,
    )

    assert "".join(chunks) == text
    assert len(chunks[0].encode("utf-8")) <= 30
    assert len(chunks[1].encode("utf-8")) > 30
    assert all(len(chunk.encode("utf-8")) <= 90 for chunk in chunks)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("### Root cause\n\nUse this.", "Root cause\n\nUse this."),
        (
            "Use **bounded context**, *tests*, and ~~dead code~~ cleanup.",
            "Use bounded context, tests, and dead code cleanup.",
        ),
        (
            "Read [the deployment guide](https://example.com/deploy) before release.",
            "Read the deployment guide before release.",
        ),
        (
            "Run `git diff --check` before checkpointing.",
            "Run git diff --check before checkpointing.",
        ),
        (
            "- Read the docs\n- Run tests\n\n1. Verify audio\n2. Stop playback",
            "Read the docs\nRun tests\n\nVerify audio\nStop playback",
        ),
        (
            "```bash\ngit status --short\npytest -q\n```",
            "git status --short\npytest -q",
        ),
        ("Before\n\n---\n\nAfter", "Before\n\nAfter"),
    ],
)
def test_speech_text_renderer_removes_markdown_syntax_for_speech(
    source: str,
    expected: str,
) -> None:
    renderer_class = getattr(speech_service, "SpeechTextRenderer", None)
    assert renderer_class is not None
    renderer = renderer_class()

    assert renderer.render(source) == expected


def test_cloud_text_to_speech_service_chunks_normalized_speech_text() -> None:
    service = CloudTextToSpeechSynthesisService(
        client_factory=FakeTextToSpeechClient,
        texttospeech_module=FakeTextToSpeechModule,
        chunk_byte_limit=64,
        first_chunk_byte_limit=18,
        later_chunk_byte_limit=64,
    )

    chunks = service._chunks_for_text(
        "### Title\n\n"
        "[short](https://example.com/this-url-would-force-extra-raw-markdown-chunks)"
    )

    assert chunks == ("Title\n\nshort",)


@pytest.mark.asyncio
async def test_cloud_text_to_speech_service_builds_chirp_request() -> None:
    client = FakeTextToSpeechClient()
    service = CloudTextToSpeechSynthesisService(
        client_factory=lambda: client,
        texttospeech_module=FakeTextToSpeechModule,
        config_loader=lambda: SpeechSynthesisConfig(
            language_code="en-GB",
            voice_name="en-GB-Chirp3-HD-Kore",
            speaking_rate=1.0,
            audio_content_type="audio/mpeg",
        ),
    )

    result = await service.synthesize(
        text="Canonical persisted answer.",
        chunk_index=0,
    )

    assert result.audio == b"mp3 bytes"
    assert result.content_type == "audio/mpeg"
    assert result.chunk_index == 0
    assert result.chunk_count == 1
    assert client.calls == [
        {
            "input": FakeSynthesisInput(text="Canonical persisted answer."),
            "voice": FakeVoiceSelectionParams(
                language_code="en-GB",
                name="en-GB-Chirp3-HD-Kore",
            ),
            "audio_config": FakeAudioConfig(
                audio_encoding="MP3",
                speaking_rate=1.0,
            ),
        }
    ]


@pytest.mark.asyncio
async def test_cloud_text_to_speech_service_sends_clean_speech_text_to_provider() -> None:
    client = FakeTextToSpeechClient()
    service = CloudTextToSpeechSynthesisService(
        client_factory=lambda: client,
        texttospeech_module=FakeTextToSpeechModule,
        config_loader=lambda: SpeechSynthesisConfig(
            language_code="en-GB",
            voice_name="en-GB-Chirp3-HD-Kore",
            speaking_rate=1.0,
            audio_content_type="audio/mpeg",
        ),
    )

    await service.synthesize(
        text="### Fix\n\nUse **TDD** and [docs](https://example.com).",
        chunk_index=0,
    )

    assert client.calls[0]["input"] == FakeSynthesisInput(
        text="Fix\n\nUse TDD and docs."
    )


@pytest.mark.asyncio
async def test_cloud_text_to_speech_service_synthesizes_requested_chunk() -> None:
    client = FakeTextToSpeechClient()
    service = CloudTextToSpeechSynthesisService(
        client_factory=lambda: client,
        texttospeech_module=FakeTextToSpeechModule,
        config_loader=lambda: SpeechSynthesisConfig(
            language_code="en-GB",
            voice_name="en-GB-Chirp3-HD-Kore",
            speaking_rate=1.0,
            audio_content_type="audio/mpeg",
        ),
        chunk_byte_limit=30,
    )

    result = await service.synthesize(
        text="First sentence. Second sentence. Third sentence.",
        chunk_index=1,
    )

    assert result.chunk_index == 1
    assert result.chunk_count == 3
    assert client.calls[0]["input"] == FakeSynthesisInput(
        text="Second sentence. "
    )


@pytest.mark.asyncio
async def test_cloud_text_to_speech_service_indexes_chunks_after_normalization() -> None:
    client = FakeTextToSpeechClient()
    service = CloudTextToSpeechSynthesisService(
        client_factory=lambda: client,
        texttospeech_module=FakeTextToSpeechModule,
        config_loader=lambda: SpeechSynthesisConfig(
            language_code="en-GB",
            voice_name="en-GB-Chirp3-HD-Kore",
            speaking_rate=1.0,
            audio_content_type="audio/mpeg",
        ),
        chunk_byte_limit=36,
        first_chunk_byte_limit=12,
        later_chunk_byte_limit=36,
    )

    result = await service.synthesize(
        text=(
            "### Title\n\n"
            "[short](https://example.com/this-url-would-be-raw-chunk-two)"
        ),
        chunk_index=0,
    )

    assert result.chunk_index == 0
    assert result.chunk_count == 1
    assert client.calls[0]["input"] == FakeSynthesisInput(text="Title\n\nshort")


def test_cloud_text_to_speech_service_uses_latency_chunk_limits() -> None:
    service = CloudTextToSpeechSynthesisService(
        client_factory=FakeTextToSpeechClient,
        texttospeech_module=FakeTextToSpeechModule,
        chunk_byte_limit=140,
        first_chunk_byte_limit=24,
        later_chunk_byte_limit=140,
    )

    chunks = service._chunks_for_text(
        "Short first sentence. "
        "Second sentence can share a later playback chunk. "
        "Third sentence also belongs after the quick-start chunk."
    )

    assert chunks == (
        "Short first sentence. ",
        "Second sentence can share a later playback chunk. "
        "Third sentence also belongs after the quick-start chunk.",
    )


@pytest.mark.asyncio
async def test_cloud_text_to_speech_service_rejects_out_of_range_chunk() -> None:
    service = CloudTextToSpeechSynthesisService(
        client_factory=FakeTextToSpeechClient,
        texttospeech_module=FakeTextToSpeechModule,
        chunk_byte_limit=30,
    )

    with pytest.raises(SpeechSynthesisChunkError):
        await service.synthesize(
            text="First sentence. Second sentence.",
            chunk_index=3,
        )


@pytest.mark.asyncio
async def test_cloud_text_to_speech_service_wraps_provider_errors() -> None:
    client = FakeTextToSpeechClient()
    client.error = RuntimeError("private provider internals")
    service = CloudTextToSpeechSynthesisService(
        client_factory=lambda: client,
        texttospeech_module=FakeTextToSpeechModule,
    )

    with pytest.raises(SpeechSynthesisProviderError) as exc_info:
        await service.synthesize(
            text="Canonical persisted answer.",
            chunk_index=0,
        )

    assert "private provider internals" not in str(exc_info.value)


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
