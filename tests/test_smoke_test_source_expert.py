import pytest


@pytest.mark.asyncio
async def test_source_smoke_reports_only_bounded_evidence_metadata() -> None:
    from expert_contracts import ExpertStatus
    from source_expert import (
        SourceDocumentResult,
        SourceExpertEvidence,
        SourceExpertPayload,
        SourceExpertResult,
        SourceProviderSource,
        SourceRetrievalStatus,
        SourceStatement,
    )
    from smoke_test_source_expert import run_source_smoke

    result = SourceExpertResult(
        status=ExpertStatus.COMPLETED,
        summary="One grounded statement.",
        payload=SourceExpertPayload(
            documents=(
                SourceDocumentResult(
                    source_id="source-1",
                    url="https://example.com/",
                    retrieval_status=SourceRetrievalStatus.RETRIEVED,
                    evidence_summary="Private generated statement.",
                ),
            ),
            facts=(
                SourceStatement(
                    text="Private generated statement.",
                    source_ids=("source-1",),
                ),
            ),
            sources=(
                SourceProviderSource(
                    source_id="source-1",
                    uri="https://example.com/",
                    label="Example Domain",
                ),
            ),
        ),
        evidence=SourceExpertEvidence(
            source_ids=("source-1",),
            grounded_statement_count=1,
            grounding_support_count=1,
        ),
    )

    class FakeService:
        async def analyze(self, request: object) -> SourceExpertResult:
            return result

    output = await run_source_smoke(
        service=FakeService(),
        urls=("https://example.com/",),
    )

    assert output == (
        "source-expert pass status=completed documents=1 retrieved=1 "
        "statements=1 citations=1 grounding_supports=1"
    )
    assert "example.com" not in output
    assert "Private generated statement" not in output
