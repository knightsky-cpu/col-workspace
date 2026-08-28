import _repo_path
import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx

from chat_turns import derive_chat_turn_ids
from schemas import ChatResponse


PROJECT_ID = "agent-col"
SOURCE_MESSAGE = (
    "Explain why retry-safe collaboration needs a durable turn boundary."
)
CONFLICT_MESSAGE = (
    "This changed request must conflict with the existing turn."
)
EXPECTED_CONFLICT = {
    "detail": "Idempotency key conflicts with a different chat request."
}


class ChatIdempotencySmokeError(RuntimeError):
    """Raised when the live idempotency contract does not hold."""


@dataclass(frozen=True, slots=True)
class ChatIdempotencySmokeResult:
    """Hold structural evidence from the live idempotency smoke check."""

    user_id: str
    session_id: str
    turn_id: str
    user_message_id: str
    model_message_id: str
    first_status: int
    replay_status: int
    conflict_status: int
    replay_equal: bool

    def safe_summary(self) -> str:
        """Render structural evidence without request or response content."""
        return (
            "trusted-memory-m6-2-3 pass "
            f"first={self.first_status} "
            f"replay={self.replay_status} "
            f"conflict={self.conflict_status} "
            f"replay_equal={str(self.replay_equal).lower()} "
            f"user_id={self.user_id} "
            f"session_id={self.session_id} "
            f"turn_id={self.turn_id} "
            f"user_message_id={self.user_message_id} "
            f"model_message_id={self.model_message_id}"
        )


def _parse_chat_response(
    response: httpx.Response,
    *,
    stage: str,
) -> ChatResponse:
    try:
        payload = response.json()
        return ChatResponse.model_validate(payload)
    except (TypeError, ValueError):
        raise ChatIdempotencySmokeError(
            f"{stage} response validation failed."
        ) from None


def _parse_conflict_response(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        raise ChatIdempotencySmokeError(
            "Conflict response validation failed."
        ) from None


async def _post_chat(
    client: httpx.AsyncClient,
    *,
    headers: dict[str, str],
    payload: dict[str, str],
    stage: str,
) -> httpx.Response:
    try:
        return await client.post(
            "/api/chat",
            headers=headers,
            json=payload,
        )
    except httpx.RequestError:
        raise ChatIdempotencySmokeError(
            f"{stage} request transport failed."
        ) from None


def _require_status(
    response: httpx.Response,
    *,
    expected: int,
    stage: str,
) -> None:
    if response.status_code != expected:
        raise ChatIdempotencySmokeError(
            f"{stage} request returned unexpected status "
            f"{response.status_code}."
        )


async def run_chat_idempotency_smoke(
    *,
    client: httpx.AsyncClient,
    id_factory: Callable[[], UUID] = uuid4,
) -> ChatIdempotencySmokeResult:
    """Verify new execution, replay, and conflict through the public API."""
    suffix = id_factory().hex
    user_id = f"memory-m6-2-3-user-{suffix}"
    session_id = f"memory-m6-2-3-session-{suffix}"
    idempotency_key = f"m6-2-3-{suffix}"
    headers = {"Idempotency-Key": idempotency_key}
    payload = {
        "project_id": PROJECT_ID,
        "session_id": session_id,
        "user_id": user_id,
        "message": SOURCE_MESSAGE,
    }

    first = await _post_chat(
        client,
        headers=headers,
        payload=payload,
        stage="Initial",
    )
    _require_status(first, expected=200, stage="Initial")
    first_response = _parse_chat_response(first, stage="Initial")

    replay = await _post_chat(
        client,
        headers=headers,
        payload=payload,
        stage="Replay",
    )
    _require_status(replay, expected=200, stage="Replay")
    replay_response = _parse_chat_response(replay, stage="Replay")
    replay_equal = replay_response == first_response
    if not replay_equal:
        raise ChatIdempotencySmokeError("Replay response changed.")

    conflict_payload = {**payload, "message": CONFLICT_MESSAGE}
    conflict = await _post_chat(
        client,
        headers=headers,
        payload=conflict_payload,
        stage="Conflict",
    )
    _require_status(conflict, expected=409, stage="Conflict")
    if _parse_conflict_response(conflict) != EXPECTED_CONFLICT:
        raise ChatIdempotencySmokeError(
            "Conflict response did not match the public contract."
        )

    ids = derive_chat_turn_ids(idempotency_key)
    return ChatIdempotencySmokeResult(
        user_id=user_id,
        session_id=session_id,
        turn_id=ids.turn_id,
        user_message_id=ids.user_message_id,
        model_message_id=ids.model_message_id,
        first_status=first.status_code,
        replay_status=replay.status_code,
        conflict_status=conflict.status_code,
        replay_equal=replay_equal,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the live smoke runner command-line parser."""
    parser = argparse.ArgumentParser(
        description="Verify the live /api/chat idempotency contract."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the running Agent_Col API.",
    )
    return parser


async def _run_from_cli(base_url: str) -> ChatIdempotencySmokeResult:
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=100.0,
    ) as client:
        return await run_chat_idempotency_smoke(client=client)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the live contract check and print only safe structural evidence."""
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(_run_from_cli(args.base_url))
    except ChatIdempotencySmokeError as exc:
        print(f"trusted-memory-m6-2-3 fail {exc}", file=sys.stderr)
        return 1
    print(result.safe_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
