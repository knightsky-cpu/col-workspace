"""Deterministic current-message text blocks for Agent_Col routing."""

import re
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


MAX_ROUTING_TEXT_BLOCK_CANDIDATES = 64
RoutingTextBlockId = Annotated[
    str,
    StringConstraints(pattern=r"^block-(?:[1-9]|[1-5][0-9]|6[0-4])$"),
]
RoutingTextBlockText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=8_000),
]
_RoutingMessageText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=10_000),
]

_ATX_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+\S")
_LABEL_HEADING = re.compile(r"^[^\n:]{1,119}:$")
_LIST_ITEM = re.compile(
    r"^[ \t]{0,3}(?:[-+*]|[1-9][0-9]{0,2}[.)])[ \t]+\S"
)
_FENCE_OPEN = re.compile(r"^[ \t]{0,3}(?P<marker>`{3,}|~{3,})")


class RoutingTextBlockKind(StrEnum):
    HEADING = "heading"
    LIST_ITEM = "list_item"
    PARAGRAPH = "paragraph"
    FENCED_BLOCK = "fenced_block"


class StrictTextProjectionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class _RoutingMessageSource(StrictTextProjectionModel):
    value: _RoutingMessageText

    @field_validator("value")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Routing message cannot be whitespace only.")
        return value


class RoutingTextBlockCandidate(StrictTextProjectionModel):
    candidate_id: RoutingTextBlockId
    text: RoutingTextBlockText
    start_index: int = Field(ge=0)
    end_index: int = Field(gt=0)
    structural_kind: RoutingTextBlockKind

    @model_validator(mode="after")
    def require_positive_span(self) -> Self:
        if self.end_index <= self.start_index:
            raise ValueError("Text block candidate span must be positive.")
        return self


class RoutingTextBlockProjection(StrictTextProjectionModel):
    candidates: tuple[RoutingTextBlockCandidate, ...] = Field(max_length=64)
    text_projection_incomplete: bool = False


def _content_end(line: str, start_index: int) -> int:
    if line.endswith("\r\n"):
        return start_index + len(line) - 2
    if line.endswith(("\n", "\r")):
        return start_index + len(line) - 1
    return start_index + len(line)


def _is_structured_line(line_text: str) -> bool:
    return bool(
        _ATX_HEADING.match(line_text)
        or _LABEL_HEADING.match(line_text)
        or _LIST_ITEM.match(line_text)
        or _FENCE_OPEN.match(line_text)
    )


def project_routing_text_blocks(
    current_message: str,
) -> RoutingTextBlockProjection:
    """Project exact, syntax-derived blocks from the current user message."""
    message = _RoutingMessageSource(value=current_message).value
    lines = message.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)

    candidates: list[RoutingTextBlockCandidate] = []
    incomplete = False

    def emit(start_index: int, end_index: int, kind: RoutingTextBlockKind) -> None:
        nonlocal incomplete
        text = message[start_index:end_index]
        if len(text) > 8_000 or len(candidates) == MAX_ROUTING_TEXT_BLOCK_CANDIDATES:
            incomplete = True
            return
        candidates.append(
            RoutingTextBlockCandidate(
                candidate_id=f"block-{len(candidates) + 1}",
                text=text,
                start_index=start_index,
                end_index=end_index,
                structural_kind=kind,
            )
        )

    line_index = 0
    while line_index < len(lines):
        line = lines[line_index]
        start_index = offsets[line_index]
        end_index = _content_end(line, start_index)
        line_text = message[start_index:end_index]
        if not line_text.strip():
            line_index += 1
            continue

        fence_match = _FENCE_OPEN.match(line_text)
        if fence_match:
            marker = fence_match.group("marker")
            closing = re.compile(
                rf"^[ \t]{{0,3}}{re.escape(marker[0])}"
                rf"{{{len(marker)},}}[ \t]*$"
            )
            closing_index = line_index + 1
            while closing_index < len(lines):
                closing_start = offsets[closing_index]
                closing_end = _content_end(lines[closing_index], closing_start)
                if closing.fullmatch(message[closing_start:closing_end]):
                    emit(start_index, closing_end, RoutingTextBlockKind.FENCED_BLOCK)
                    line_index = closing_index + 1
                    break
                closing_index += 1
            else:
                incomplete = True
                break
            continue

        if _ATX_HEADING.match(line_text) or _LABEL_HEADING.match(line_text):
            emit(start_index, end_index, RoutingTextBlockKind.HEADING)
            line_index += 1
            continue
        if _LIST_ITEM.match(line_text):
            emit(start_index, end_index, RoutingTextBlockKind.LIST_ITEM)
            line_index += 1
            continue

        paragraph_start = start_index
        paragraph_end = end_index
        line_index += 1
        while line_index < len(lines):
            next_start = offsets[line_index]
            next_end = _content_end(lines[line_index], next_start)
            next_text = message[next_start:next_end]
            if not next_text.strip() or _is_structured_line(next_text):
                break
            paragraph_end = next_end
            line_index += 1
        emit(paragraph_start, paragraph_end, RoutingTextBlockKind.PARAGRAPH)

    return RoutingTextBlockProjection(
        candidates=tuple(candidates),
        text_projection_incomplete=incomplete,
    )
