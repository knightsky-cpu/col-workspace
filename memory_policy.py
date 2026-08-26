import re
import unicodedata
from types import MappingProxyType
from typing import Annotated, Literal, cast

from pydantic import StringConstraints


MEMORY_SCHEMA_VERSION = "1.0"
MEMORY_POLICY_VERSION = "1.0"
MEMORY_SCHEMA_VERSION_V2 = "2.0"
MEMORY_POLICY_VERSION_V2 = "2.0"

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
UserRequestedMemoryStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=240),
]
MemoryValue = PreferenceValue | PreferredNameStr | list[BroadRole]
ExplanationPace = Literal["deliberate", "balanced", "brisk"]
LearningApproach = Literal[
    "concept_first",
    "example_first",
    "practice_first",
    "question_guided",
]
AccessibilitySupport = Literal[
    "plain_language",
    "screen_reader_friendly",
    "low_visual_density",
    "reduced_motion",
    "keyboard_first",
]
DevelopmentEnvironment = Literal["macos", "linux", "windows"]
DomainExperienceDomain = Literal[
    "software_development",
    "data_science",
    "cybersecurity",
    "research",
    "writing",
    "education",
    "project_management",
    "design",
    "mathematics",
    "science",
    "business",
    "creative_work",
]
DomainExperienceLevel = Literal[
    "exploring",
    "learning",
    "practicing",
    "experienced",
]
PreferenceCategoryV2 = PreferenceCategory | Literal[
    "explanation_pace",
    "learning_approach",
    "accessibility_support",
    "development_environments",
    "user_requested_memory",
]
IdentityContextCategoryV2 = IdentityContextCategory | Literal[
    "domain_experience"
]
MemoryCategoryV2 = PreferenceCategoryV2 | IdentityContextCategoryV2
MemoryPolicyVersion = Literal["1.0", "2.0"]
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
EXPLANATION_PACE_VALUES: tuple[ExplanationPace, ...] = (
    "deliberate",
    "balanced",
    "brisk",
)
LEARNING_APPROACH_VALUES: tuple[LearningApproach, ...] = (
    "concept_first",
    "example_first",
    "practice_first",
    "question_guided",
)
ACCESSIBILITY_SUPPORT_ORDER: tuple[AccessibilitySupport, ...] = (
    "plain_language",
    "screen_reader_friendly",
    "low_visual_density",
    "reduced_motion",
    "keyboard_first",
)
DEVELOPMENT_ENVIRONMENT_ORDER: tuple[DevelopmentEnvironment, ...] = (
    "macos",
    "linux",
    "windows",
)
DOMAIN_EXPERIENCE_DOMAIN_ORDER: tuple[DomainExperienceDomain, ...] = (
    "software_development",
    "data_science",
    "cybersecurity",
    "research",
    "writing",
    "education",
    "project_management",
    "design",
    "mathematics",
    "science",
    "business",
    "creative_work",
)
DOMAIN_EXPERIENCE_LEVELS: tuple[DomainExperienceLevel, ...] = (
    "exploring",
    "learning",
    "practicing",
    "experienced",
)
MEMORY_CATEGORY_ORDER_V2: tuple[MemoryCategoryV2, ...] = (
    "preferred_name",
    "broad_roles",
    "domain_experience",
    "response_length",
    "explanation_structure",
    "explanation_pace",
    "example_usage",
    "learning_approach",
    "question_style",
    "planning_granularity",
    "progress_check_ins",
    "tool_use_style",
    "formatting_style",
    "accessibility_support",
    "development_environments",
    "user_requested_memory",
)

USER_REQUESTED_MEMORY_PROHIBITED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bpassword\b", re.IGNORECASE),
    re.compile(r"\b(api|access|refresh|id)\s+key\b", re.IGNORECASE),
    re.compile(r"\b(token|credential|secret)\b", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"),
    re.compile(
        r"\b\d{1,6}\s+[\w .'-]{1,80}\s+"
        r"(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|"
        r"way|court|ct)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    re.compile(r"\bremember\s+everything\b", re.IGNORECASE),
    re.compile(
        r"\b(?:delete|remove|erase|revoke)\s+"
        r"(?:my\s+)?(?:saved\s+)?memory\b",
        re.IGNORECASE,
    ),
)

V2_SCALAR_VALUES_BY_CATEGORY = MappingProxyType(
    {
        "explanation_pace": frozenset(EXPLANATION_PACE_VALUES),
        "learning_approach": frozenset(LEARNING_APPROACH_VALUES),
    }
)
V2_SCALAR_INSTRUCTIONS = MappingProxyType(
    {
        ("explanation_pace", "deliberate"): (
            "When the current request permits, introduce concepts gradually "
            "and separate consequential stages so the user can follow each "
            "transition."
        ),
        ("explanation_pace", "balanced"): (
            "When the current request permits, use a steady explanatory pace "
            "with enough transition to connect the main ideas."
        ),
        ("explanation_pace", "brisk"): (
            "When the current request permits, move quickly to the result and "
            "minimize transitional explanation without omitting required "
            "evidence or limitations."
        ),
        ("learning_approach", "concept_first"): (
            "For instructional requests, explain the governing concept before "
            "applying it."
        ),
        ("learning_approach", "example_first"): (
            "For instructional requests, begin with one concrete example "
            "before explaining the governing rule."
        ),
        ("learning_approach", "practice_first"): (
            "For instructional requests, begin with one small guided exercise "
            "when practice is appropriate."
        ),
        ("learning_approach", "question_guided"): (
            "For instructional requests, use at most one bounded guiding "
            "question at a time when it helps the user reason without blocking "
            "a requested direct answer."
        ),
    }
)
ACCESSIBILITY_SUPPORT_INSTRUCTIONS = MappingProxyType(
    {
        "plain_language": (
            "Prefer plain language and define necessary technical terms."
        ),
        "screen_reader_friendly": (
            "Use linear headings, descriptive link text, and text equivalents; "
            "do not rely on spatial position alone."
        ),
        "low_visual_density": (
            "Keep sections visually separated and avoid unnecessarily dense "
            "presentation."
        ),
        "reduced_motion": (
            "When producing interface specifications or UI code, avoid "
            "nonessential motion and include reduced-motion behavior."
        ),
        "keyboard_first": (
            "When producing interface specifications or UI code, include "
            "complete keyboard operation."
        ),
    }
)
DEVELOPMENT_ENVIRONMENT_LABELS = MappingProxyType(
    {"macos": "macOS", "linux": "Linux", "windows": "Windows"}
)

MEMORY_POLICY_REGISTRY = MappingProxyType(
    {
        MEMORY_POLICY_VERSION: MEMORY_CATEGORY_ORDER,
        MEMORY_POLICY_VERSION_V2: MEMORY_CATEGORY_ORDER_V2,
    }
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


def memory_category_order_for_policy(
    policy_version: object,
) -> tuple[MemoryCategory, ...] | tuple[MemoryCategoryV2, ...]:
    if type(policy_version) is not str or policy_version not in (
        MEMORY_POLICY_REGISTRY
    ):
        raise ValueError("Unsupported memory policy version.")
    return MEMORY_POLICY_REGISTRY[policy_version]


def validate_memory_value_for_policy(
    policy_version: object,
    category: object,
    value: object,
) -> object:
    memory_category_order_for_policy(policy_version)
    if policy_version == MEMORY_POLICY_VERSION:
        return validate_memory_value(category, value)
    return _validate_memory_value_v2(category, value)


def memory_instruction_for_policy(
    policy_version: object,
    category: object,
    value: object,
) -> str:
    validated = validate_memory_value_for_policy(
        policy_version,
        category,
        value,
    )
    if category in PREFERENCE_VALUES_BY_CATEGORY:
        return PreferencePolicy.instruction(category, validated)
    if category in IDENTITY_CONTEXT_INSTRUCTIONS:
        return IdentityContextPolicy.instruction(category, validated)
    if category in V2_SCALAR_VALUES_BY_CATEGORY:
        return V2_SCALAR_INSTRUCTIONS[(category, validated)]
    if category == "accessibility_support":
        return " ".join(
            ACCESSIBILITY_SUPPORT_INSTRUCTIONS[item]
            for item in cast(list[AccessibilitySupport], validated)
        )
    if category == "development_environments":
        labels = [
            DEVELOPMENT_ENVIRONMENT_LABELS[item]
            for item in cast(list[DevelopmentEnvironment], validated)
        ]
        return (
            "When platform-specific commands or paths are needed and the "
            "current task does not specify another target, prefer guidance "
            f"compatible with {_join_human_labels(labels)}."
        )
    if category == "domain_experience":
        instructions = []
        for entry in cast(list[dict[str, str]], validated):
            domain_label = entry["domain"].replace("_", " ").title()
            level_label = entry["level"].replace("_", " ").title()
            instructions.append(
                f"For {domain_label} material, calibrate vocabulary and "
                "examples to the user's explicitly self-reported "
                f"{level_label} experience; do not treat it as verified "
                "expertise."
            )
        return " ".join(instructions)
    if category == "user_requested_memory":
        return (
            "Use this approved user-requested memory when it is relevant to "
            "the current conversation, without overriding explicit user "
            "instructions, project requirements, or safety policy: "
            f"{validated}"
        )
    raise ValueError("Unknown memory category.")


def memory_signal_sort_key_for_policy(
    policy_version: object,
    category: object,
) -> int:
    order = memory_category_order_for_policy(policy_version)
    try:
        return order.index(category)
    except ValueError as exc:
        raise ValueError("Unknown memory category.") from exc


def _validate_memory_value_v2(category: object, value: object) -> object:
    if category in PREFERENCE_VALUES_BY_CATEGORY:
        return PreferencePolicy.validate(category, value)
    if category in IDENTITY_CONTEXT_INSTRUCTIONS:
        return IdentityContextPolicy.validate(category, value)
    if category in V2_SCALAR_VALUES_BY_CATEGORY:
        if type(value) is not str:
            raise ValueError("Preference value must be a string.")
        if value not in V2_SCALAR_VALUES_BY_CATEGORY[category]:
            raise ValueError("Value is not allowed for this category.")
        return value
    if category == "accessibility_support":
        return _canonical_string_list(
            value,
            ACCESSIBILITY_SUPPORT_ORDER,
            "Accessibility support",
        )
    if category == "development_environments":
        return _canonical_string_list(
            value,
            DEVELOPMENT_ENVIRONMENT_ORDER,
            "Development environments",
        )
    if category == "domain_experience":
        return _canonical_domain_experience(value)
    if category == "user_requested_memory":
        return _canonical_user_requested_memory(value)
    raise ValueError("Unknown memory category.")


def _canonical_user_requested_memory(value: object) -> UserRequestedMemoryStr:
    if type(value) is not str:
        raise ValueError("User-requested memory must be a string.")
    if any(
        unicodedata.category(character).startswith("C")
        for character in value
    ):
        raise ValueError("User-requested memory contains a control character.")
    normalized = unicodedata.normalize("NFC", value)
    normalized = " ".join(normalized.split())
    if not 1 <= len(normalized) <= 240:
        raise ValueError(
            "User-requested memory must contain 1 through 240 characters."
        )
    if not any(character.isalpha() for character in normalized):
        raise ValueError("User-requested memory must contain a letter.")
    for pattern in USER_REQUESTED_MEMORY_PROHIBITED_PATTERNS:
        if pattern.search(normalized):
            raise ValueError("User-requested memory contains prohibited content.")
    return cast(UserRequestedMemoryStr, normalized)


def _canonical_string_list(
    value: object,
    allowed_order: tuple[str, ...],
    label: str,
) -> list[str]:
    if type(value) is not list:
        raise ValueError(f"{label} must be a list.")
    if not 1 <= len(value) <= 3:
        raise ValueError(f"{label} must contain 1 through 3 values.")
    if any(type(item) is not str for item in value):
        raise ValueError(f"{label} must contain strings.")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} values must be unique.")
    if any(item not in allowed_order for item in value):
        raise ValueError(f"{label} value is not allowed.")
    return [item for item in allowed_order if item in value]


def _canonical_domain_experience(value: object) -> list[dict[str, str]]:
    if type(value) is not list:
        raise ValueError("Domain experience must be a list.")
    if not 1 <= len(value) <= 3:
        raise ValueError(
            "Domain experience must contain 1 through 3 entries."
        )
    normalized: dict[str, dict[str, str]] = {}
    for entry in value:
        if type(entry) is not dict or set(entry) != {"domain", "level"}:
            raise ValueError("Domain experience entry is invalid.")
        domain = entry["domain"]
        level = entry["level"]
        if type(domain) is not str or domain not in (
            DOMAIN_EXPERIENCE_DOMAIN_ORDER
        ):
            raise ValueError("Domain experience domain is not allowed.")
        if type(level) is not str or level not in DOMAIN_EXPERIENCE_LEVELS:
            raise ValueError("Domain experience level is not allowed.")
        if domain in normalized:
            raise ValueError("Domain experience domains must be unique.")
        normalized[domain] = {"domain": domain, "level": level}
    return [
        normalized[domain]
        for domain in DOMAIN_EXPERIENCE_DOMAIN_ORDER
        if domain in normalized
    ]


def _join_human_labels(labels: list[str]) -> str:
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"
