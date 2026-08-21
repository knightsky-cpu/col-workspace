import hashlib
import re
from dataclasses import dataclass
from typing import cast

from memory_policy import MEMORY_CATEGORY_ORDER, MemoryCategory


PROPOSAL_ORIGIN_SCHEMA_VERSION = "1.0"
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_TURN_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ORIGIN_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


@dataclass(frozen=True, slots=True)
class ProposalOriginIds:
    origin_id: str
    proposal_id: str


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


def proposal_origin_id_from_signal_id(
    category: MemoryCategory,
    signal_id: str,
) -> str | None:
    """Return the origin ID only for a version-1 guarded signal ID."""
    if category not in MEMORY_CATEGORY_ORDER:
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
