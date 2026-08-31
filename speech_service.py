import asyncio
import os
import re
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


DEFAULT_STT_LANGUAGE_CODES = ("en-US",)
DEFAULT_STT_MODEL = "latest_short"
DEFAULT_STT_LOCATION = "global"
DEFAULT_TTS_LANGUAGE_CODE = "en-GB"
DEFAULT_TTS_VOICE = "en-GB-Chirp3-HD-Kore"
ALTERNATE_TTS_MALE_VOICE = "en-GB-Chirp3-HD-Alnilam"
DEFAULT_TTS_SPEAKING_RATE = 1.0
DEFAULT_TTS_AUDIO_CONTENT_TYPE = "audio/mpeg"
TTS_PROVIDER_INPUT_BYTE_LIMIT = 5000
TTS_CHUNK_BYTE_LIMIT = 4800
TTS_VOICE_NAMES_BY_ID = {
    "female": DEFAULT_TTS_VOICE,
    "male": ALTERNATE_TTS_MALE_VOICE,
}
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


class SpeechSynthesisError(RuntimeError):
    """Base error for speech synthesis failures."""


class SpeechSynthesisConfigurationError(SpeechSynthesisError):
    """Raised when speech synthesis is not configured."""


class SpeechSynthesisProviderError(SpeechSynthesisError):
    """Raised when the synthesis provider fails."""


class SpeechSynthesisChunkError(ValueError):
    """Raised when a requested speech chunk is invalid."""


@dataclass(frozen=True)
class SpeechTranscriptionConfig:
    project_id: str
    location: str
    language_codes: tuple[str, ...]
    model: str


@dataclass(frozen=True)
class SpeechSynthesisConfig:
    language_code: str
    voice_name: str
    speaking_rate: float
    audio_content_type: str


@dataclass(frozen=True)
class SpeechSynthesisResult:
    audio: bytes
    content_type: str
    chunk_index: int
    chunk_count: int


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


def load_speech_synthesis_config(
    source: Mapping[str, str] = os.environ,
) -> SpeechSynthesisConfig:
    del source
    return SpeechSynthesisConfig(
        language_code=DEFAULT_TTS_LANGUAGE_CODE,
        voice_name=DEFAULT_TTS_VOICE,
        speaking_rate=DEFAULT_TTS_SPEAKING_RATE,
        audio_content_type=DEFAULT_TTS_AUDIO_CONTENT_TYPE,
    )


def chunk_text_for_speech(
    text: str,
    *,
    max_bytes: int = TTS_CHUNK_BYTE_LIMIT,
) -> tuple[str, ...]:
    if max_bytes < 1 or max_bytes > TTS_PROVIDER_INPUT_BYTE_LIMIT:
        raise ValueError("max_bytes must fit the provider limit.")
    if not text:
        raise SpeechSynthesisChunkError("Speech text cannot be empty.")
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    def append_unit(unit: str) -> None:
        nonlocal current
        if not unit:
            return
        if len(unit.encode("utf-8")) > max_bytes:
            flush()
            chunks.extend(_split_text_by_utf8_limit(unit, max_bytes))
            return
        if current and len((current + unit).encode("utf-8")) > max_bytes:
            flush()
        current += unit

    for paragraph in _split_after_boundary(text, r"\n\s*\n"):
        if len(paragraph.encode("utf-8")) <= max_bytes:
            append_unit(paragraph)
            continue
        for sentence in _split_after_boundary(paragraph, r"(?<=[.!?])\s+"):
            append_unit(sentence)
    flush()
    return tuple(chunks)


def _split_after_boundary(text: str, pattern: str) -> tuple[str, ...]:
    units: list[str] = []
    start = 0
    for match in re.finditer(pattern, text):
        end = match.end()
        units.append(text[start:end])
        start = end
    if start < len(text):
        units.append(text[start:])
    return tuple(units) if units else (text,)


def _split_text_by_utf8_limit(text: str, max_bytes: int) -> tuple[str, ...]:
    chunks: list[str] = []
    current = ""
    current_bytes = 0
    for character in text:
        character_bytes = len(character.encode("utf-8"))
        if current and current_bytes + character_bytes > max_bytes:
            chunks.append(current)
            current = ""
            current_bytes = 0
        current += character
        current_bytes += character_bytes
    if current:
        chunks.append(current)
    return tuple(chunks)


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


class CloudTextToSpeechSynthesisService:
    def __init__(
        self,
        *,
        client_factory: Callable[[], object] | None = None,
        texttospeech_module: object | None = None,
        config_loader: Callable[[], SpeechSynthesisConfig] = (
            load_speech_synthesis_config
        ),
        chunk_byte_limit: int = TTS_CHUNK_BYTE_LIMIT,
    ) -> None:
        self._client_factory = client_factory
        self._texttospeech_module = texttospeech_module
        self._config_loader = config_loader
        self._chunk_byte_limit = chunk_byte_limit

    async def synthesize(
        self,
        *,
        text: str,
        chunk_index: int,
        voice_id: str = "female",
    ) -> SpeechSynthesisResult:
        chunks = chunk_text_for_speech(
            text,
            max_bytes=self._chunk_byte_limit,
        )
        if chunk_index < 0 or chunk_index >= len(chunks):
            raise SpeechSynthesisChunkError("Speech chunk is unavailable.")
        return await asyncio.to_thread(
            self._synthesize_sync,
            chunks[chunk_index],
            chunk_index,
            len(chunks),
            voice_id,
        )

    def _texttospeech(self) -> object:
        if self._texttospeech_module is not None:
            return self._texttospeech_module
        from google.cloud import texttospeech

        return texttospeech

    def _client(self) -> object:
        if self._client_factory is not None:
            return self._client_factory()
        texttospeech = self._texttospeech()
        return texttospeech.TextToSpeechClient()

    def _synthesize_sync(
        self,
        text: str,
        chunk_index: int,
        chunk_count: int,
        voice_id: str,
    ) -> SpeechSynthesisResult:
        config = self._config_loader()
        voice_name = TTS_VOICE_NAMES_BY_ID.get(voice_id)
        if voice_name is None:
            raise SpeechSynthesisConfigurationError(
                "Speech voice is not configured."
            )
        texttospeech = self._texttospeech()
        client = self._client()
        try:
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=config.language_code,
                    name=voice_name,
                ),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=config.speaking_rate,
                ),
            )
        except Exception as exc:
            raise SpeechSynthesisProviderError(
                "Speech synthesis provider failed."
            ) from exc
        audio_content = getattr(response, "audio_content", b"")
        if not isinstance(audio_content, bytes) or not audio_content:
            raise SpeechSynthesisProviderError(
                "Speech synthesis provider returned no audio."
            )
        return SpeechSynthesisResult(
            audio=audio_content,
            content_type=config.audio_content_type,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
        )


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
