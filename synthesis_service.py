import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from google import genai

from database import MemoryEngine
from schemas import (
    SYNTHESIS_BLUEPRINT_SCHEMA_VERSION,
    AdaptationReceipt,
    SynthesisBlueprint,
)
from synthesis import (
    SYNTHESIS_MODEL_NAME,
    SynthesisEngineError,
    generate_blueprint,
    generate_governed_blueprint as generate_governed_blueprint_from_provider,
)
from synthesis_personalization import (
    SynthesisPersonalizationAdapter,
    SynthesisPersonalizationError,
)

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
GovernedBlueprintGenerator = BlueprintGenerator


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
    adaptations: tuple[AdaptationReceipt, ...] = ()


@dataclass(frozen=True, slots=True)
class GovernedSynthesisGenerationResult:
    blueprint: SynthesisBlueprint
    adaptations: tuple[AdaptationReceipt, ...]


class SynthesisApplicationService:
    def __init__(
        self,
        *,
        client: genai.Client,
        database: MemoryEngine,
        blueprint_generator: BlueprintGenerator = generate_blueprint,
        governed_blueprint_generator: GovernedBlueprintGenerator = (
            generate_governed_blueprint_from_provider
        ),
    ) -> None:
        self._client = client
        self._database = database
        self._blueprint_generator = blueprint_generator
        self._governed_blueprint_generator = governed_blueprint_generator

    async def generate_blueprint(
        self,
        command: SynthesisCommand,
    ) -> SynthesisBlueprint:
        """Generate one strict blueprint without choosing persistence."""
        profile, history = await asyncio.gather(
            self._database.get_user_profile(command.user_id),
            self._database.get_chat_history(
                command.session_id,
                limit=SYNTHESIS_HISTORY_LIMIT,
            ),
        )
        return await self._blueprint_generator(
            self._client,
            profile,
            history,
            command.source_text,
        )

    async def synthesize(
        self,
        command: SynthesisCommand,
    ) -> SynthesisResult:
        generated = await self.generate_governed_blueprint(command)
        blueprint = generated.blueprint
        blueprint_id = await self._database.save_blueprint(
            command.project_id,
            command.session_id,
            command.user_id,
            SYNTHESIS_MODEL_NAME,
            SYNTHESIS_BLUEPRINT_SCHEMA_VERSION,
            blueprint.model_dump(mode="json"),
            adaptations=generated.adaptations,
        )
        return SynthesisResult(
            blueprint_id=blueprint_id,
            blueprint=blueprint,
            adaptations=generated.adaptations,
        )

    async def generate_governed_blueprint(
        self,
        command: SynthesisCommand,
    ) -> GovernedSynthesisGenerationResult:
        """Generate from governed memory without choosing persistence."""
        profile, history = await asyncio.gather(
            self._database.get_collaboration_profile(command.user_id),
            self._database.get_chat_history(
                command.session_id,
                limit=SYNTHESIS_HISTORY_LIMIT,
            ),
        )
        projection = SynthesisPersonalizationAdapter.project(profile)
        blueprint = await self._governed_blueprint_generator(
            self._client,
            projection.model_context,
            history,
            command.source_text,
        )
        try:
            adaptations = (
                SynthesisPersonalizationAdapter.validate_and_derive_receipts(
                    projection,
                    blueprint,
                )
            )
        except SynthesisPersonalizationError as exc:
            raise SynthesisEngineError(
                "Blueprint personalization validation failed."
            ) from exc
        return GovernedSynthesisGenerationResult(
            blueprint=blueprint,
            adaptations=adaptations,
        )
