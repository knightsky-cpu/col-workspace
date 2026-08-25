import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import cast

from memory_policy import (
    MEMORY_CATEGORY_ORDER,
    MEMORY_CATEGORY_ORDER_V2,
    MemoryCategory,
    MemoryCategoryV2,
)


PROPOSAL_ORIGIN_SCHEMA_VERSION = "1.0"
PROPOSAL_ORIGIN_SCHEMA_VERSION_V2 = "2.0"
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_TURN_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ORIGIN_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


@dataclass(frozen=True, slots=True)
class ProposalOriginIds:
    origin_id: str
    proposal_id: str


@dataclass(frozen=True, slots=True)
class ProposalOriginV1:
    schema_version: str
    proposal_id: str
    category: MemoryCategory
    source_session_id: str
    source_message_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version != PROPOSAL_ORIGIN_SCHEMA_VERSION:
            raise ValueError("Unsupported proposal-origin schema version.")
        _validate_proposal_origin_common(
            proposal_id=self.proposal_id,
            category=self.category,
            category_order=MEMORY_CATEGORY_ORDER,
            source_session_id=self.source_session_id,
            source_message_id=self.source_message_id,
            created_at=self.created_at,
        )


@dataclass(frozen=True, slots=True)
class ProposalOriginV2:
    schema_version: str
    proposal_id: str
    category: MemoryCategoryV2
    source_session_id: str
    source_message_id: str
    evidence_message_id: str
    created_at: datetime
    clarification_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != PROPOSAL_ORIGIN_SCHEMA_VERSION_V2:
            raise ValueError("Unsupported proposal-origin schema version.")
        _validate_proposal_origin_common(
            proposal_id=self.proposal_id,
            category=self.category,
            category_order=MEMORY_CATEGORY_ORDER_V2,
            source_session_id=self.source_session_id,
            source_message_id=self.source_message_id,
            created_at=self.created_at,
        )
        _validate_identifier(self.evidence_message_id, "evidence_message_id")
        if self.clarification_id is None:
            if self.evidence_message_id != self.source_message_id:
                raise ValueError(
                    "Direct memory evidence must match the source message."
                )
        else:
            _validate_identifier(self.clarification_id, "clarification_id")
            if self.evidence_message_id == self.source_message_id:
                raise ValueError(
                    "Clarified memory evidence must precede the source message."
                )


PROPOSAL_ORIGIN_SCHEMA_REGISTRY = MappingProxyType(
    {
        PROPOSAL_ORIGIN_SCHEMA_VERSION: ProposalOriginV1,
        PROPOSAL_ORIGIN_SCHEMA_VERSION_V2: ProposalOriginV2,
    }
)


@dataclass(frozen=True, slots=True)
class ProposalTurnLease:
    turn_id: str
    owner_token: str

    def __post_init__(self) -> None:
        if _TURN_ID_PATTERN.fullmatch(self.turn_id) is None:
            raise ValueError("turn_id must be a lowercase SHA-256 digest.")
        _validate_identifier(self.owner_token, "owner_token")


def derive_proposal_origin_ids(
    user_id: str,
    session_id: str,
    source_message_id: str,
    category: MemoryCategory,
) -> ProposalOriginIds:
    """Derive stable source-message and category-bound proposal IDs."""
    _validate_identifier(user_id, "user_id")
    _validate_identifier(session_id, "session_id")
    _validate_identifier(source_message_id, "source_message_id")
    if category not in MEMORY_CATEGORY_ORDER:
        raise ValueError("category must be a governed memory category.")
    validated_category = cast(MemoryCategory, category)
    digest_input = "\0".join(
        (
            "memory-proposal-origin-v1",
            user_id,
            session_id,
            source_message_id,
        )
    )
    origin_id = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:32]
    return ProposalOriginIds(
        origin_id=origin_id,
        proposal_id=f"{validated_category}--{origin_id}",
    )


def derive_proposal_origin_ids_v2(
    user_id: str,
    session_id: str,
    source_message_id: str,
    category: MemoryCategoryV2,
) -> ProposalOriginIds:
    """Derive version-2 IDs without changing version-1 identity."""
    _validate_identifier(user_id, "user_id")
    _validate_identifier(session_id, "session_id")
    _validate_identifier(source_message_id, "source_message_id")
    if category not in MEMORY_CATEGORY_ORDER_V2:
        raise ValueError("category must be a governed memory category.")
    validated_category = cast(MemoryCategoryV2, category)
    digest_input = "\0".join(
        (
            "memory-proposal-origin-v2",
            user_id,
            session_id,
            source_message_id,
        )
    )
    origin_id = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:32]
    return ProposalOriginIds(
        origin_id=origin_id,
        proposal_id=f"{validated_category}--{origin_id}",
    )


def parse_proposal_origin(
    document: object,
) -> ProposalOriginV1 | ProposalOriginV2:
    if not isinstance(document, Mapping):
        raise ValueError("Stored proposal origin is invalid.")
    schema_version = document.get("schema_version")
    if type(schema_version) is not str or schema_version not in (
        PROPOSAL_ORIGIN_SCHEMA_REGISTRY
    ):
        raise ValueError("Unsupported proposal-origin schema version.")
    fields = set(document)
    v1_fields = {
        "schema_version",
        "proposal_id",
        "category",
        "source_session_id",
        "source_message_id",
        "created_at",
    }
    if schema_version == PROPOSAL_ORIGIN_SCHEMA_VERSION:
        if fields != v1_fields:
            raise ValueError("Stored proposal origin is invalid.")
        return ProposalOriginV1(**dict(document))
    v2_required_fields = v1_fields | {"evidence_message_id"}
    if fields not in (
        v2_required_fields,
        v2_required_fields | {"clarification_id"},
    ):
        raise ValueError("Stored proposal origin is invalid.")
    return ProposalOriginV2(**dict(document))


def proposal_origin_id_from_signal_id(
    category: MemoryCategoryV2,
    signal_id: str,
) -> str | None:
    """Return the origin ID for a guarded versioned signal ID."""
    if category not in MEMORY_CATEGORY_ORDER_V2:
        raise ValueError("category must be a governed memory category.")
    _validate_identifier(signal_id, "signal_id")
    prefix = f"{category}--"
    if not signal_id.startswith(prefix):
        raise ValueError("signal_id must match its category.")
    origin_id = signal_id[len(prefix) :]
    if _ORIGIN_ID_PATTERN.fullmatch(origin_id) is None:
        return None
    return origin_id


def _validate_identifier(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or _IDENTIFIER_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(f"{field_name} must be a valid identifier.")


def _validate_proposal_origin_common(
    *,
    proposal_id: object,
    category: object,
    category_order: tuple[object, ...],
    source_session_id: object,
    source_message_id: object,
    created_at: object,
) -> None:
    if category not in category_order:
        raise ValueError("category must be a governed memory category.")
    _validate_identifier(proposal_id, "proposal_id")
    _validate_identifier(source_session_id, "source_session_id")
    _validate_identifier(source_message_id, "source_message_id")
    if (
        not isinstance(created_at, datetime)
        or created_at.tzinfo is None
        or created_at.utcoffset() is None
    ):
        raise ValueError("created_at must be a timezone-aware datetime.")
