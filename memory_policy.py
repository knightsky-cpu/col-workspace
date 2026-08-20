import re
import unicodedata
from types import MappingProxyType
from typing import Annotated, Literal, cast

from pydantic import StringConstraints


MEMORY_SCHEMA_VERSION = "1.0"
MEMORY_POLICY_VERSION = "1.0"

PreferenceCategory = Literal[
    "response_length",
    "explanation_structure",
    "example_usage",
    "question_style",
    "planning_granularity",
    "progress_check_ins",
    "tool_use_style",
    "formatting_style",
]
IdentityContextCategory = Literal[
    "preferred_name",
    "broad_roles",
]
MemoryCategory = PreferenceCategory | IdentityContextCategory

PreferenceValue = Literal[
    "concise",
    "balanced",
    "detailed",
    "direct_then_steps",
    "step_by_step",
    "concept_then_example",
    "none",
    "when_helpful",
    "always_practical",
    "ask_before_assuming",
    "recommend_then_ask",
    "minimal_follow_up",
    "milestones",
    "tasks",
    "micro_steps",
    "only_when_blocked",
    "at_milestones",
    "frequent",
    "ask_before_external_tools",
    "use_when_needed",
    "minimize_tools",
    "prose",
    "bullets",
    "mixed",
]
BroadRole = Literal[
    "student",
    "professional",
    "educator",
    "researcher",
    "hobbyist",
    "retired",
    "career_transition",
]
PreferredNameStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]
MemoryValue = PreferenceValue | PreferredNameStr | list[BroadRole]
MemoryDecision = Literal["approve", "reject"]
ConfirmationChannel = Literal["chat_decision", "memory_api"]
MemoryEventType = Literal[
    "approved",
    "corrected",
    "superseded",
    "revoked",
]

PREFERENCE_VALUES_BY_CATEGORY = MappingProxyType(
    {
        "response_length": frozenset(
            {"concise", "balanced", "detailed"}
        ),
        "explanation_structure": frozenset(
            {
                "direct_then_steps",
                "step_by_step",
                "concept_then_example",
            }
        ),
        "example_usage": frozenset(
            {"none", "when_helpful", "always_practical"}
        ),
        "question_style": frozenset(
            {
                "ask_before_assuming",
                "recommend_then_ask",
                "minimal_follow_up",
            }
        ),
        "planning_granularity": frozenset(
            {"milestones", "tasks", "micro_steps"}
        ),
        "progress_check_ins": frozenset(
            {"only_when_blocked", "at_milestones", "frequent"}
        ),
        "tool_use_style": frozenset(
            {
                "ask_before_external_tools",
                "use_when_needed",
                "minimize_tools",
            }
        ),
        "formatting_style": frozenset({"prose", "bullets", "mixed"}),
    }
)
PREFERENCE_CATEGORY_ORDER: tuple[PreferenceCategory, ...] = (
    "response_length",
    "explanation_structure",
    "example_usage",
    "question_style",
    "planning_granularity",
    "progress_check_ins",
    "tool_use_style",
    "formatting_style",
)
BROAD_ROLE_ORDER: tuple[BroadRole, ...] = (
    "student",
    "professional",
    "educator",
    "researcher",
    "hobbyist",
    "retired",
    "career_transition",
)
PREFERENCE_INSTRUCTIONS = MappingProxyType(
    {
        ("response_length", "concise"): (
            "Keep the response compact while preserving information required "
            "to complete the request."
        ),
        ("response_length", "balanced"): (
            "Use moderate detail, covering the answer and its most important "
            "supporting context."
        ),
        ("response_length", "detailed"): (
            "Provide thorough context, explicit steps, and important "
            "limitations without exposing hidden reasoning."
        ),
        ("explanation_structure", "direct_then_steps"): (
            "Lead with the outcome, then give ordered steps when the task "
            "requires them."
        ),
        ("explanation_structure", "step_by_step"): (
            "Explain complex work as ordered, independently checkable steps."
        ),
        ("explanation_structure", "concept_then_example"): (
            "Explain the governing concept before demonstrating it with an "
            "example."
        ),
        ("example_usage", "none"): (
            "Do not add examples unless the current request requires one for "
            "correctness."
        ),
        ("example_usage", "when_helpful"): (
            "Add a concise example when it materially improves understanding."
        ),
        ("example_usage", "always_practical"): (
            "Include one practical example when the task permits it."
        ),
        ("question_style", "ask_before_assuming"): (
            "Ask one concise question before making a consequential "
            "unsupported assumption."
        ),
        ("question_style", "recommend_then_ask"): (
            "Give the safest bounded recommendation, then ask one question "
            "that could materially change it."
        ),
        ("question_style", "minimal_follow_up"): (
            "Ask a follow-up only when missing information prevents safe or "
            "correct progress."
        ),
        ("planning_granularity", "milestones"): (
            "Organize plans around outcomes and major milestones."
        ),
        ("planning_granularity", "tasks"): (
            "Organize plans into independently reviewable tasks with clear "
            "outcomes."
        ),
        ("planning_granularity", "micro_steps"): (
            "Break complex plans into small sequential actions with explicit "
            "verification."
        ),
        ("progress_check_ins", "only_when_blocked"): (
            "Request a check-in only when progress is blocked or authority is "
            "required."
        ),
        ("progress_check_ins", "at_milestones"): (
            "Request confirmation at consequential milestone boundaries."
        ),
        ("progress_check_ins", "frequent"): (
            "Offer brief progress check-ins during longer collaborative work."
        ),
        ("tool_use_style", "ask_before_external_tools"): (
            "Ask before using an external information tool unless the current "
            "request already authorizes it."
        ),
        ("tool_use_style", "use_when_needed"): (
            "Use a tool only when it materially improves correctness, evidence, "
            "or completion."
        ),
        ("tool_use_style", "minimize_tools"): (
            "Prefer the fewest tool calls that can reliably complete the "
            "request."
        ),
        ("formatting_style", "prose"): (
            "Prefer compact prose unless another format is necessary for "
            "clarity."
        ),
        ("formatting_style", "bullets"): (
            "Prefer concise bullets for multiple facts, options, or actions."
        ),
        ("formatting_style", "mixed"): (
            "Use short prose for conclusions and lists for comparisons or "
            "sequential work."
        ),
    }
)
IDENTITY_CONTEXT_INSTRUCTIONS = MappingProxyType(
    {
        "preferred_name": (
            "Address the user by their approved preferred name when natural; "
            "do not repeat it mechanically or treat it as verified legal "
            "identity."
        ),
        "broad_roles": (
            "Use the approved broad role context only to calibrate examples "
            "and explanations; do not infer expertise, employer, school, "
            "seniority, or credentials."
        ),
    }
)
MEMORY_CATEGORY_ORDER: tuple[MemoryCategory, ...] = (
    "preferred_name",
    "broad_roles",
    *PREFERENCE_CATEGORY_ORDER,
)


class PreferencePolicy:
    @staticmethod
    def validate(category: object, value: object) -> PreferenceValue:
        if category not in PREFERENCE_VALUES_BY_CATEGORY:
            raise ValueError("Unknown preference category.")
        if type(value) is not str:
            raise ValueError("Preference value must be a string.")
        if value not in PREFERENCE_VALUES_BY_CATEGORY[category]:
            raise ValueError("Value is not allowed for this category.")
        return cast(PreferenceValue, value)

    @classmethod
    def instruction(cls, category: object, value: object) -> str:
        validated = cls.validate(category, value)
        return PREFERENCE_INSTRUCTIONS[(category, validated)]


class IdentityContextPolicy:
    @staticmethod
    def validate(
        field: object,
        value: object,
        *,
        current_message: str | None = None,
        require_grounding: bool = False,
    ) -> PreferredNameStr | list[BroadRole]:
        if field == "preferred_name":
            if type(value) is not str:
                raise ValueError("Preferred name must be a string.")
            if any(
                unicodedata.category(character).startswith("C")
                for character in value
            ):
                raise ValueError("Preferred name contains a control character.")
            normalized = unicodedata.normalize("NFC", value)
            normalized = " ".join(normalized.split())
            if not 1 <= len(normalized) <= 80:
                raise ValueError(
                    "Preferred name must contain 1 through 80 characters."
                )
            if not any(character.isalpha() for character in normalized):
                raise ValueError("Preferred name must contain a letter.")
            if any(
                not (character.isalpha() or character in " .'’-")
                for character in normalized
            ):
                raise ValueError(
                    "Preferred name contains a prohibited character."
                )
            if require_grounding:
                if current_message is None:
                    raise ValueError("Current message is required.")
                normalized_message = unicodedata.normalize(
                    "NFC",
                    " ".join(current_message.split()),
                ).casefold()
                pattern = rf"(?<!\w){re.escape(normalized.casefold())}(?!\w)"
                if re.search(pattern, normalized_message) is None:
                    raise ValueError(
                        "Preferred name is absent from the current message."
                    )
            return cast(PreferredNameStr, normalized)
        if field == "broad_roles":
            if type(value) is not list:
                raise ValueError("Broad roles must be a list.")
            if not 1 <= len(value) <= 3:
                raise ValueError("Broad roles must contain 1 through 3 values.")
            if any(type(role) is not str for role in value):
                raise ValueError("Broad roles must contain strings.")
            if len(set(value)) != len(value):
                raise ValueError("Broad roles must be unique.")
            if any(role not in BROAD_ROLE_ORDER for role in value):
                raise ValueError("Broad role is not allowed.")
            roles = cast(list[BroadRole], value)
            return [role for role in BROAD_ROLE_ORDER if role in roles]
        raise ValueError("Unknown identity-context field.")

    @classmethod
    def instruction(cls, field: object, value: object) -> str:
        cls.validate(field, value)
        return IDENTITY_CONTEXT_INSTRUCTIONS[field]


def validate_memory_value(category: object, value: object) -> MemoryValue:
    if category in PREFERENCE_VALUES_BY_CATEGORY:
        return PreferencePolicy.validate(category, value)
    if category in IDENTITY_CONTEXT_INSTRUCTIONS:
        return IdentityContextPolicy.validate(category, value)
    raise ValueError("Unknown memory category.")


def memory_signal_sort_key(category: object) -> int:
    try:
        return MEMORY_CATEGORY_ORDER.index(category)
    except ValueError as exc:
        raise ValueError("Unknown memory category.") from exc
