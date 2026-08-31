import asyncio
import os
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


DEFAULT_STT_LANGUAGE_CODES = ("en-US",)
DEFAULT_STT_MODEL = "latest_short"
DEFAULT_STT_LOCATION = "global"
SUPPORTED_AUDIO_CONTENT_TYPES = frozenset(
    {
        "audio/webm",
        "audio/webm;codecs=opus",
    }
)


class SpeechTranscriptionError(RuntimeError):
    """Base error for speech transcription failures."""


class SpeechTranscriptionConfigurationError(SpeechTranscriptionError):
    """Raised when speech transcription is not configured."""


class SpeechTranscriptionProviderError(SpeechTranscriptionError):
    """Raised when the transcription provider fails."""


class UnsupportedAudioContentTypeError(ValueError):
    """Raised when an audio MIME type is outside the allowlist."""


@dataclass(frozen=True)
class SpeechTranscriptionConfig:
    project_id: str
    location: str
    language_codes: tuple[str, ...]
    model: str


def normalize_audio_content_type(content_type: str | None) -> str:
    if content_type is None:
        raise UnsupportedAudioContentTypeError("Audio content type is required.")
    parts = [part.strip().lower() for part in content_type.split(";")]
    base_type = parts[0]
    parameters = tuple(part for part in parts[1:] if part)
    if base_type == "audio/webm" and not parameters:
        return "audio/webm"
    if base_type == "audio/webm" and parameters == ("codecs=opus",):
        return "audio/webm;codecs=opus"
    raise UnsupportedAudioContentTypeError("Unsupported audio content type.")


def _parse_language_codes(raw_value: str | None) -> tuple[str, ...]:
    if raw_value is None:
        return DEFAULT_STT_LANGUAGE_CODES
    language_codes = tuple(
        code.strip()
        for code in raw_value.split(",")
        if code.strip()
    )
    return language_codes or DEFAULT_STT_LANGUAGE_CODES


def load_speech_transcription_config(
    source: Mapping[str, str] = os.environ,
) -> SpeechTranscriptionConfig:
    project_id = source.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project_id:
        raise SpeechTranscriptionConfigurationError(
            "Google Cloud project is not configured."
        )
    location = source.get("GOOGLE_CLOUD_LOCATION", DEFAULT_STT_LOCATION).strip()
    model = source.get("AGENT_COL_STT_MODEL", DEFAULT_STT_MODEL).strip()
    return SpeechTranscriptionConfig(
        project_id=project_id,
        location=location or DEFAULT_STT_LOCATION,
        language_codes=_parse_language_codes(
            source.get("AGENT_COL_STT_LANGUAGE_CODES")
        ),
        model=model or DEFAULT_STT_MODEL,
    )


class CloudSpeechTranscriptionService:
    def __init__(
        self,
        *,
        client_factory: Callable[[], object] | None = None,
        speech_v2_module: object | None = None,
        config_loader: Callable[[], SpeechTranscriptionConfig] = (
            load_speech_transcription_config
        ),
    ) -> None:
        self._client_factory = client_factory
        self._speech_v2_module = speech_v2_module
        self._config_loader = config_loader

    async def transcribe(
        self,
        *,
        audio: bytes,
        content_type: str,
    ) -> str:
        normalized_content_type = normalize_audio_content_type(content_type)
        return await asyncio.to_thread(
            self._transcribe_sync,
            audio,
            normalized_content_type,
        )

    def _speech_v2(self) -> object:
        if self._speech_v2_module is not None:
            return self._speech_v2_module
        from google.cloud.speech_v2.types import cloud_speech

        return cloud_speech

    def _client(self, speech_v2: object) -> object:
        del speech_v2
        if self._client_factory is not None:
            return self._client_factory()
        from google.cloud.speech_v2 import SpeechClient

        return SpeechClient()

    def _transcribe_sync(
        self,
        audio: bytes,
        content_type: str,
    ) -> str:
        del content_type
        config = self._config_loader()
        speech_v2 = self._speech_v2()
        client = self._client(speech_v2)
        recognize_request = speech_v2.RecognizeRequest(
            recognizer=(
                f"projects/{config.project_id}/locations/"
                f"{config.location}/recognizers/_"
            ),
            config=speech_v2.RecognitionConfig(
                auto_decoding_config=speech_v2.AutoDetectDecodingConfig(),
                language_codes=list(config.language_codes),
                model=config.model,
            ),
            content=audio,
        )
        try:
            response = client.recognize(request=recognize_request)
        except Exception as exc:
            raise SpeechTranscriptionProviderError(
                "Speech transcription provider failed."
            ) from exc
        return _extract_transcript(response)


def _extract_transcript(response: Any) -> str:
    transcripts: list[str] = []
    for result in getattr(response, "results", ()):
        alternatives = getattr(result, "alternatives", ())
        if not alternatives:
            continue
        transcript = getattr(alternatives[0], "transcript", "")
        if transcript.strip():
            transcripts.append(transcript.strip())
    return " ".join(transcripts)
