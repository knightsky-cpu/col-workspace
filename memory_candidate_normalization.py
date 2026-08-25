import re
import unicodedata
from types import MappingProxyType

from memory_policy import validate_memory_value_for_policy


MEMORY_ALIAS_CATALOG_VERSION = "2.0"


def _alias_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


_ALIASES = MappingProxyType(
    {
        "response_length": MappingProxyType(
            {
                "detailed answers": "detailed",
                "long detailed responses": "detailed",
                "long detailed informative answers": "detailed",
                "short answers": "concise",
                "concise answers": "concise",
                "balanced answers": "balanced",
            }
        ),
        "explanation_structure": MappingProxyType(
            {
                "give me the answer first and steps after": (
                    "direct_then_steps"
                ),
                "answer first then steps": "direct_then_steps",
                "step by step": "step_by_step",
                "concept then example": "concept_then_example",
            }
        ),
        "explanation_pace": MappingProxyType(
            {
                "take explanations slowly": "deliberate",
                "slow explanations": "deliberate",
                "normal explanation pace": "balanced",
                "get to the result quickly": "brisk",
            }
        ),
        "learning_approach": MappingProxyType(
            {
                "show me an example before the theory": "example_first",
                "example before theory": "example_first",
                "concept first": "concept_first",
                "practice first": "practice_first",
                "guide me with questions": "question_guided",
            }
        ),
        "accessibility_support": MappingProxyType(
            {
                "format it so it works well with a screen reader": [
                    "screen_reader_friendly"
                ],
                "screen reader friendly": ["screen_reader_friendly"],
                "use plain language": ["plain_language"],
                "keep the visual layout sparse": ["low_visual_density"],
                "reduce motion": ["reduced_motion"],
                "keyboard first": ["keyboard_first"],
            }
        ),
        "development_environments": MappingProxyType(
            {
                "favor macos and linux development environments": [
                    "macos",
                    "linux",
                ],
                "macos and linux": ["macos", "linux"],
                "macos": ["macos"],
                "linux": ["linux"],
                "windows": ["windows"],
            }
        ),
        "domain_experience": MappingProxyType(
            {
                "i am learning software development": [
                    {
                        "domain": "software_development",
                        "level": "learning",
                    }
                ],
                "learning software development": [
                    {
                        "domain": "software_development",
                        "level": "learning",
                    }
                ],
            }
        ),
    }
)


def normalize_memory_candidate(
    policy_version: object,
    category: object,
    candidate_value: object,
) -> object:
    try:
        return validate_memory_value_for_policy(
            policy_version,
            category,
            candidate_value,
        )
    except ValueError as canonical_error:
        if policy_version != MEMORY_ALIAS_CATALOG_VERSION:
            raise ValueError(
                "Memory candidate has no recognized canonical value."
            ) from canonical_error
        if type(category) is not str or type(candidate_value) is not str:
            raise ValueError(
                "Memory candidate has no recognized canonical value."
            ) from canonical_error
        aliases = _ALIASES.get(category)
        alias = aliases.get(_alias_key(candidate_value)) if aliases else None
        if alias is None:
            raise ValueError(
                "Memory candidate has no recognized canonical value."
            ) from canonical_error
        try:
            return validate_memory_value_for_policy(
                policy_version,
                category,
                alias,
            )
        except ValueError as alias_error:
            raise ValueError(
                "Memory candidate has no recognized canonical value."
            ) from alias_error
