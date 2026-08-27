import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from expert_contracts import ExpertCapability
from source_expert import SourceExpertInput


RoutingTaskText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]
RoutingMessageText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
]
RoutingClarificationText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
RoutingConstraintText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
RoutingUrlId = Annotated[
    str,
    StringConstraints(pattern=r"^url-(?:[1-9]|10)$"),
]
_URL_PATTERN = re.compile(r'https?://[^\s<>"\']+')
_MAX_ROUTING_URL_CANDIDATES = 10


class AgentColRoute(StrEnum):
    DIRECT = "direct"
    CLARIFY = "clarify"
    SOURCE = "source"
    RESEARCH = "research"


class RoutingDirectiveInputError(RuntimeError):
    """Raised when a valid directive cannot execute against its input."""


class RoutingUrlSource(StrEnum):
    CURRENT_MESSAGE = "current_message"
    RECENT_USER_HISTORY = "recent_user_history"


class StrictRoutingModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class RoutingUrlCandidate(StrictRoutingModel):
    candidate_id: RoutingUrlId
    url: HttpUrl
    source: RoutingUrlSource

    @field_validator("url")
    @classmethod
    def require_public_url(cls, url: HttpUrl) -> HttpUrl:
        return SourceExpertInput(
            objective="Validate a routing URL candidate.",
            urls=(url,),
        ).urls[0]


class AgentColRoutingInput(StrictRoutingModel):
    current_message: RoutingMessageText
    candidate_urls: tuple[RoutingUrlCandidate, ...] = Field(
        default_factory=tuple,
        max_length=_MAX_ROUTING_URL_CANDIDATES,
    )
    available_capabilities: tuple[ExpertCapability, ...] = Field(
        default_factory=tuple,
        max_length=2,
    )

    @model_validator(mode="after")
    def require_unique_bounded_context(self) -> Self:
        allowed_capabilities = {
            ExpertCapability.SOURCE,
            ExpertCapability.RESEARCH,
        }
        if not set(self.available_capabilities) <= allowed_capabilities:
            raise ValueError("Routing capability is not available.")
        if len(set(self.available_capabilities)) != len(
            self.available_capabilities
        ):
            raise ValueError("Routing capabilities must be unique.")

        candidate_ids = tuple(
            candidate.candidate_id for candidate in self.candidate_urls
        )
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("Routing candidate IDs must be unique.")

        candidate_urls = tuple(
            str(candidate.url) for candidate in self.candidate_urls
        )
        if len(set(candidate_urls)) != len(candidate_urls):
            raise ValueError("Routing candidate URLs must be unique.")
        return self


class SourceRoutingIntent(StrictRoutingModel):
    objective: RoutingTaskText
    selected_url_ids: tuple[RoutingUrlId, ...] = Field(
        min_length=1,
        max_length=3,
    )
    constraints: tuple[RoutingConstraintText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )

    @field_validator("selected_url_ids")
    @classmethod
    def require_unique_url_ids(
        cls,
        url_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(set(url_ids)) != len(url_ids):
            raise ValueError("Selected routing URL IDs must be unique.")
        return url_ids


class ResearchRoutingIntent(StrictRoutingModel):
    question: RoutingTaskText
    objective: RoutingTaskText
    constraints: tuple[RoutingConstraintText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )


class AgentColRoutingDirective(StrictRoutingModel):
    schema_version: Literal["1.0"] = "1.0"
    route: AgentColRoute
    clarifying_question: RoutingClarificationText | None = None
    source_intent: SourceRoutingIntent | None = None
    research_intent: ResearchRoutingIntent | None = None

    @model_validator(mode="after")
    def require_matching_route_payload(self) -> Self:
        expected_presence = {
            AgentColRoute.DIRECT: (False, False, False),
            AgentColRoute.CLARIFY: (True, False, False),
            AgentColRoute.SOURCE: (False, True, False),
            AgentColRoute.RESEARCH: (False, False, True),
        }
        actual_presence = (
            self.clarifying_question is not None,
            self.source_intent is not None,
            self.research_intent is not None,
        )
        if actual_presence != expected_presence[self.route]:
            raise ValueError("Routing payload does not match its route.")
        return self


def validate_routing_directive_for_input(
    directive: AgentColRoutingDirective,
    routing_input: AgentColRoutingInput,
) -> AgentColRoutingDirective:
    """Validate a directive against the exact bounded input it received."""
    incompatible = "Routing directive is incompatible with its input."

    if directive.route is AgentColRoute.SOURCE:
        if ExpertCapability.SOURCE not in routing_input.available_capabilities:
            raise RoutingDirectiveInputError(incompatible)
        if directive.source_intent is None or not routing_input.candidate_urls:
            raise RoutingDirectiveInputError(incompatible)
        available_ids = {
            candidate.candidate_id for candidate in routing_input.candidate_urls
        }
        if not set(directive.source_intent.selected_url_ids) <= available_ids:
            raise RoutingDirectiveInputError(incompatible)

    if (
        directive.route is AgentColRoute.RESEARCH
        and ExpertCapability.RESEARCH
        not in routing_input.available_capabilities
    ):
        raise RoutingDirectiveInputError(incompatible)

    return directive


def _strip_sentence_punctuation(value: str) -> str:
    candidate = value.rstrip(".,;")
    for opening, closing in (("(", ")"), ("[", "]"), ("{", "}")):
        while (
            candidate.endswith(closing)
            and candidate.count(opening) < candidate.count(closing)
        ):
            candidate = candidate[:-1]
    return candidate


def project_routing_url_candidates(
    current_message: str,
    recent_user_messages: Sequence[str],
) -> tuple[RoutingUrlCandidate, ...]:
    """Project bounded public URL references from user-authored text."""
    projected: list[RoutingUrlCandidate] = []
    seen_urls: set[str] = set()
    sources = (
        (current_message, RoutingUrlSource.CURRENT_MESSAGE),
        *(
            (message, RoutingUrlSource.RECENT_USER_HISTORY)
            for message in reversed(recent_user_messages)
        ),
    )
    for message, source in sources:
        for match in _URL_PATTERN.finditer(message):
            raw_url = _strip_sentence_punctuation(match.group(0))
            try:
                validated = SourceExpertInput(
                    objective="Validate a routing URL candidate.",
                    urls=(raw_url,),
                ).urls[0]
            except ValidationError:
                continue
            normalized_url = str(validated)
            if normalized_url in seen_urls:
                continue
            projected.append(
                RoutingUrlCandidate(
                    candidate_id=f"url-{len(projected) + 1}",
                    url=validated,
                    source=source,
                )
            )
            seen_urls.add(normalized_url)
            if len(projected) == _MAX_ROUTING_URL_CANDIDATES:
                return tuple(projected)
    return tuple(projected)
