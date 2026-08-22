"""Deterministic numeric candidates for Agent_Col routing."""

import re
from math import isfinite
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StringConstraints,
    TypeAdapter,
    model_validator,
)


MAX_ROUTING_NUMERIC_CANDIDATES = 32
RoutingNumericId = Annotated[
    str,
    StringConstraints(pattern=r"^number-(?:[1-9]|[12][0-9]|3[0-2])$"),
]
_RoutingMessageText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
]
_MESSAGE_ADAPTER = TypeAdapter(_RoutingMessageText)
_UNSIGNED_NUMBER_BODY = (
    r"(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"(?:[eE][+-]?\d+)?"
)
_NUMBER_BODY = rf"[+-]?{_UNSIGNED_NUMBER_BODY}"
_NUMBER_BODY_PATTERN = re.compile(rf"^{_NUMBER_BODY}$")
_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])"
    r"(?P<currency>[$€£¥])?"
    rf"(?P<number>{_NUMBER_BODY})"
    r"(?P<percent>%?)"
    r"(?!\w|\.\d)"
)
_URL_PATTERN = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)
_UNSUPPORTED_PATTERNS = (
    re.compile(rf"(?<![\w.])\d{{4}}-\d{{1,2}}-\d{{1,2}}(?![\w.])"),
    re.compile(rf"(?<![\w.]){_UNSIGNED_NUMBER_BODY}:{_UNSIGNED_NUMBER_BODY}(?![\w.])"),
    re.compile(rf"(?<![\w.]){_NUMBER_BODY}/{_NUMBER_BODY}(?![\w.])"),
    re.compile(
        rf"(?<![\w.]){_UNSIGNED_NUMBER_BODY}\s*"
        rf"(?:[-–—]|\bto\b)\s*{_UNSIGNED_NUMBER_BODY}(?![\w.])",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:version\s+|v){_UNSIGNED_NUMBER_BODY}(?:\.\d+)+\b",
        re.IGNORECASE,
    ),
    re.compile(rf"[$€£¥]{_NUMBER_BODY}%"),
)
_IDENTIFIER_NUMBER_LIKE_PATTERN = re.compile(
    r"\b(?=[A-Za-z0-9_]*[A-Za-z_])(?=[A-Za-z0-9_]*\d)[A-Za-z0-9_]+\b"
)
_COMMA_NUMBER_LIKE_PATTERN = re.compile(
    r"(?<![\w.])[+-]?\d+(?:,\d+)+(?:\.\d+)?(?![\w.])"
)


class RoutingNumericNotation(StrEnum):
    PLAIN = "plain"
    PERCENT = "percent"
    CURRENCY = "currency"


class StrictNumericProjectionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )


class RoutingNumericCandidate(StrictNumericProjectionModel):
    candidate_id: RoutingNumericId
    raw_text: Annotated[
        str,
        StringConstraints(min_length=1, max_length=64),
    ]
    value: FiniteFloat
    notation: RoutingNumericNotation
    unit_symbol: Literal["%", "$", "€", "£", "¥"] | None = None
    start_index: int = Field(ge=0)
    end_index: int = Field(gt=0)

    @model_validator(mode="after")
    def require_valid_span_and_notation(self) -> Self:
        if self.end_index <= self.start_index:
            raise ValueError("Numeric candidate span must be positive.")
        expected_units = {
            RoutingNumericNotation.PLAIN: {None},
            RoutingNumericNotation.PERCENT: {"%"},
            RoutingNumericNotation.CURRENCY: {"$", "€", "£", "¥"},
        }
        if self.unit_symbol not in expected_units[self.notation]:
            raise ValueError("Numeric notation does not match its unit.")
        raw_number = self.raw_text
        if self.notation is RoutingNumericNotation.PERCENT:
            raw_number = raw_number.removesuffix("%")
        elif self.notation is RoutingNumericNotation.CURRENCY:
            raw_number = raw_number[1:]
        if not _NUMBER_BODY_PATTERN.fullmatch(raw_number):
            raise ValueError("Numeric candidate text is invalid.")
        parsed_value = float(raw_number.replace(",", ""))
        if not isfinite(parsed_value) or parsed_value != self.value:
            raise ValueError("Numeric candidate value does not match its text.")
        return self


class RoutingNumericProjection(StrictNumericProjectionModel):
    candidates: tuple[RoutingNumericCandidate, ...] = Field(max_length=32)
    numeric_projection_incomplete: bool = False


def _scan_numeric_candidates(
    current_message: str,
) -> RoutingNumericProjection:
    message = _MESSAGE_ADAPTER.validate_python(current_message)
    masked_spans = [match.span() for match in _URL_PATTERN.finditer(message)]

    def overlaps(
        span: tuple[int, int],
        other_spans: list[tuple[int, int]],
    ) -> bool:
        start_index, end_index = span
        return any(
            start_index < other_end and end_index > other_start
            for other_start, other_end in other_spans
        )

    unsupported_spans: list[tuple[int, int]] = []
    for pattern in _UNSUPPORTED_PATTERNS:
        unsupported_spans.extend(
            match.span()
            for match in pattern.finditer(message)
            if not overlaps(match.span(), masked_spans)
        )
    for match in _IDENTIFIER_NUMBER_LIKE_PATTERN.finditer(message):
        if (
            not _NUMBER_BODY_PATTERN.fullmatch(match.group(0))
            and not overlaps(match.span(), masked_spans)
        ):
            unsupported_spans.append(match.span())
    for match in _COMMA_NUMBER_LIKE_PATTERN.finditer(message):
        if (
            not _NUMBER_BODY_PATTERN.fullmatch(match.group(0))
            and not overlaps(match.span(), masked_spans)
        ):
            unsupported_spans.append(match.span())
    masked_spans.extend(unsupported_spans)

    def is_masked(start_index: int, end_index: int) -> bool:
        return any(
            start_index < masked_end and end_index > masked_start
            for masked_start, masked_end in masked_spans
        )

    candidates: list[RoutingNumericCandidate] = []
    incomplete = bool(unsupported_spans)
    for match in _NUMBER_PATTERN.finditer(message):
        if is_masked(match.start(), match.end()):
            continue
        currency = match.group("currency")
        percent = match.group("percent")
        if currency and percent:
            incomplete = True
            continue
        value = float(match.group("number").replace(",", ""))
        if not isfinite(value):
            incomplete = True
            continue
        if len(candidates) == MAX_ROUTING_NUMERIC_CANDIDATES:
            incomplete = True
            continue
        if currency:
            notation = RoutingNumericNotation.CURRENCY
            unit_symbol = currency
        elif percent:
            notation = RoutingNumericNotation.PERCENT
            unit_symbol = "%"
        else:
            notation = RoutingNumericNotation.PLAIN
            unit_symbol = None
        candidates.append(
            RoutingNumericCandidate(
                candidate_id=f"number-{len(candidates) + 1}",
                raw_text=match.group(0),
                value=value,
                notation=notation,
                unit_symbol=unit_symbol,
                start_index=match.start(),
                end_index=match.end(),
            )
        )
    return RoutingNumericProjection(
        candidates=tuple(candidates),
        numeric_projection_incomplete=incomplete,
    )


def project_routing_numeric_candidates(
    current_message: str,
) -> RoutingNumericProjection:
    """Project safe numeric literals from the current user message."""
    return _scan_numeric_candidates(current_message)


def contains_numeric_like_text(value: str) -> bool:
    """Return whether bounded text contains deterministic numeric syntax."""
    projection = _scan_numeric_candidates(value)
    return bool(
        projection.candidates or projection.numeric_projection_incomplete
    )
