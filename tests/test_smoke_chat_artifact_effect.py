from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from chat_turns import ChatTurnClaim, ChatTurnRequest, derive_chat_turn_ids
from database import BlueprintDocumentRecord, ChatTurnArtifactEffectResult
from schemas import AgentActionReceipt, ArtifactReference


@pytest.mark.asyncio
async def test_artifact_effect_smoke_proves_recovery_and_canonical_document() -> None:
    from smoke_test_chat_artifact_effect import run_artifact_effect_smoke

    observed_at = datetime(2026, 8, 23, 14, 0, tzinfo=UTC)
    run_id = "test-run"
    request = ChatTurnRequest(
        project_id="m8-col-3b-smoke-test-run",
        session_id="m8-col-3b-smoke-test-run",
        user_id="m8-col-3b-smoke-test-run",
        message="Create one bounded artifact-effect ledger smoke blueprint.",
    )
    ids = derive_chat_turn_ids("m8-col-3b-smoke-test-run")
    initial_claim = ChatTurnClaim(
        request=request,
        ids=ids,
        owner_token="owner-1",
        lease_expires_at=observed_at + timedelta(seconds=120),
        resumed=False,
    )
    artifact = ArtifactReference(
        artifact_type="synthesis_blueprint",
        project_id=request.project_id,
        artifact_id=f"blueprint--{ids.turn_id}",
        schema_version="2.0",
        display_label="Artifact Effect Ledger Smoke",
    )
    action = AgentActionReceipt(
        action_name="synthesize_project",
        status="completed",
    )
    effect_claim = ChatTurnClaim(
        request=request,
        ids=ids,
        owner_token="owner-1",
        lease_expires_at=initial_claim.lease_expires_at,
        resumed=False,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    released_claim = ChatTurnClaim(
        request=request,
        ids=ids,
        owner_token="owner-1",
        lease_expires_at=observed_at,
        resumed=False,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    resumed_claim = ChatTurnClaim(
        request=request,
        ids=ids,
        owner_token="owner-2",
        lease_expires_at=observed_at + timedelta(seconds=121),
        resumed=True,
        precompleted_actions=(action,),
        precompleted_artifacts=(artifact,),
    )
    engine = AsyncMock()
    engine.claim_chat_turn.side_effect = [initial_claim, resumed_claim]
    engine.record_chat_turn_blueprint_effect.return_value = (
        ChatTurnArtifactEffectResult(
            claim=effect_claim,
            artifact=artifact,
        )
    )
    engine.release_chat_turn.side_effect = [released_claim, resumed_claim]
    engine.get_blueprint_document.return_value = BlueprintDocumentRecord(
        artifact_id=artifact.artifact_id,
        document={
            "originating_session_id": request.session_id,
            "originating_turn_id": ids.turn_id,
            "user_id": request.user_id,
            "blueprint": {"smoke_marker": run_id},
        },
    )

    result = await run_artifact_effect_smoke(
        engine,
        run_id=run_id,
        observed_at=observed_at,
    )

    assert result == {
        "project_id": request.project_id,
        "session_id": request.session_id,
        "user_id": request.user_id,
        "turn_id": ids.turn_id,
        "artifact_id": artifact.artifact_id,
    }
    assert engine.claim_chat_turn.await_count == 2
    engine.record_chat_turn_blueprint_effect.assert_awaited_once()
    assert engine.release_chat_turn.await_args_list[0].args == (effect_claim,)
    assert engine.release_chat_turn.await_args_list[0].kwargs == {
        "observed_at": observed_at,
    }
    assert engine.release_chat_turn.await_args_list[1].args == (resumed_claim,)
    assert engine.release_chat_turn.await_args_list[1].kwargs == {
        "observed_at": observed_at + timedelta(seconds=1),
    }
