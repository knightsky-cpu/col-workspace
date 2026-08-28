import _repo_path
import argparse
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from chat_turns import ChatTurnClaim, ChatTurnReplay, ChatTurnRequest
from database import MemoryEngine


SMOKE_MESSAGE = "Create one bounded artifact-effect ledger smoke blueprint."


async def run_artifact_effect_smoke(
    engine: MemoryEngine,
    *,
    run_id: str,
    observed_at: datetime,
) -> dict[str, str]:
    identifier = f"m8-col-3b-smoke-{run_id}"
    request = ChatTurnRequest(
        project_id=identifier,
        session_id=identifier,
        user_id=identifier,
        message=SMOKE_MESSAGE,
    )
    first_claim = await engine.claim_chat_turn(
        request,
        idempotency_key=identifier,
        observed_at=observed_at,
    )
    if not isinstance(first_claim, ChatTurnClaim):
        raise RuntimeError("Smoke turn unexpectedly replayed before creation.")
    effect = await engine.record_chat_turn_blueprint_effect(
        first_claim,
        model_name="deterministic-smoke",
        schema_version="2.0",
        blueprint={
            "synthesized_conceptual_model": {
                "project_name": "Artifact Effect Ledger Smoke",
            },
            "smoke_marker": run_id,
        },
        display_label="Artifact Effect Ledger Smoke",
        observed_at=observed_at,
    )
    await engine.release_chat_turn(
        effect.claim,
        observed_at=observed_at,
    )

    recovery_time = observed_at + timedelta(seconds=1)
    resumed = await engine.claim_chat_turn(
        request,
        idempotency_key=identifier,
        observed_at=recovery_time,
    )
    if isinstance(resumed, ChatTurnReplay) or not isinstance(
        resumed,
        ChatTurnClaim,
    ):
        raise RuntimeError("Smoke turn did not resume its incomplete effect.")
    if resumed.precompleted_artifacts != (effect.artifact,):
        raise RuntimeError("Resumed turn did not recover its artifact effect.")
    record = await engine.get_blueprint_document(
        request.project_id,
        effect.artifact.artifact_id,
    )
    if (
        record.artifact_id != effect.artifact.artifact_id
        or record.document.get("originating_session_id")
        != request.session_id
        or record.document.get("originating_turn_id") != resumed.ids.turn_id
        or record.document.get("user_id") != request.user_id
        or record.document.get("blueprint", {}).get("smoke_marker")
        != run_id
    ):
        raise RuntimeError("Canonical blueprint document is inconsistent.")
    await engine.release_chat_turn(resumed, observed_at=recovery_time)
    return {
        "project_id": request.project_id,
        "session_id": request.session_id,
        "user_id": request.user_id,
        "turn_id": resumed.ids.turn_id,
        "artifact_id": effect.artifact.artifact_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the M8-COL.3B atomic artifact-effect ledger."
    )
    parser.add_argument("--run-id", default=uuid.uuid4().hex)
    args = parser.parse_args()
    result = asyncio.run(
        run_artifact_effect_smoke(
            MemoryEngine(),
            run_id=args.run_id,
            observed_at=datetime.now(UTC),
        )
    )
    print(
        "m8-col-3b artifact-effect-pass "
        + " ".join(f"{key}={value}" for key, value in result.items())
    )


if __name__ == "__main__":
    main()
