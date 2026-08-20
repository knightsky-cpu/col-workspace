import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from google import genai

from database import MemoryEngine
from schemas import (
    SYNTHESIS_BLUEPRINT_SCHEMA_VERSION,
    SynthesisBlueprint,
)
from synthesis import SYNTHESIS_MODEL_NAME, generate_blueprint

SYNTHESIS_HISTORY_LIMIT = 20

BlueprintGenerator = Callable[
    [
        genai.Client,
        dict[str, object],
        list[dict[str, object]],
        str,
    ],
    Awaitable[SynthesisBlueprint],
]


@dataclass(frozen=True)
class SynthesisCommand:
    project_id: str
    session_id: str
    user_id: str
    source_text: str


@dataclass(frozen=True)
class SynthesisResult:
    blueprint_id: str
    blueprint: SynthesisBlueprint


class SynthesisApplicationService:
    def __init__(
        self,
        *,
        client: genai.Client,
        database: MemoryEngine,
        blueprint_generator: BlueprintGenerator = generate_blueprint,
    ) -> None:
        self._client = client
        self._database = database
        self._blueprint_generator = blueprint_generator

    async def synthesize(
        self,
        command: SynthesisCommand,
    ) -> SynthesisResult:
        profile, history = await asyncio.gather(
            self._database.get_user_profile(command.user_id),
            self._database.get_chat_history(
                command.session_id,
                limit=SYNTHESIS_HISTORY_LIMIT,
            ),
        )
        blueprint = await self._blueprint_generator(
            self._client,
            profile,
            history,
            command.source_text,
        )
        blueprint_id = await self._database.save_blueprint(
            command.project_id,
            command.session_id,
            command.user_id,
            SYNTHESIS_MODEL_NAME,
            SYNTHESIS_BLUEPRINT_SCHEMA_VERSION,
            blueprint.model_dump(mode="json"),
        )
        return SynthesisResult(
            blueprint_id=blueprint_id,
            blueprint=blueprint,
        )
