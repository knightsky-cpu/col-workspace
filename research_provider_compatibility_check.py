"""Metadata-only Research provider compatibility probe."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types

from expert_contracts import ExpertStatus
from research_expert import (
    ResearchExpertInput,
    ResearchInvalidOutputReason,
    diagnose_grounded_research_text,
)
from research_expert_service import (
    ResearchExpertService,
    ResearchExpertServiceError,
)
from vertex_config import VertexAIConfigurationError, load_vertex_ai_settings


DEFAULT_PROMPT = (
    "Identify the current stable Python release using current public evidence. "
    "Use official sources when possible."
)


ProbeSurface = Literal[
    "adk_research_service",
    "generate_content",
    "interactions",
]


@dataclass(frozen=True, slots=True)
class ResearchProviderObservation:
    probe_id: str
    surface: ProbeSurface
    status: str
    error_class: str = "none"
    api_status: str = "none"
    candidate_count: int = 0
    grounding_metadata_present: bool = False
    grounding_chunk_count: int = 0
    grounding_support_count: int = 0
    step_types: tuple[str, ...] = ()
    google_search_call_count: int = 0
    google_search_result_count: int = 0
    model_output_count: int = 0
    citation_annotation_count: int = 0
    invalid_output_reason: str = "none"

    def to_report_line(self) -> str:
        steps = ",".join(self.step_types) if self.step_types else "none"
        grounding_present = (
            "true" if self.grounding_metadata_present else "false"
        )
        return (
            f"research-provider probe={self.probe_id} "
            f"surface={self.surface} status={self.status} "
            f"error_class={self.error_class} "
            f"api_status={self.api_status} "
            f"candidates={self.candidate_count} "
            f"grounding_metadata={grounding_present} "
            f"grounding_chunks={self.grounding_chunk_count} "
            f"grounding_supports={self.grounding_support_count} "
            f"steps={steps} "
            f"google_search_calls={self.google_search_call_count} "
            f"google_search_results={self.google_search_result_count} "
            f"model_outputs={self.model_output_count} "
            f"annotations={self.citation_annotation_count} "
            f"invalid_output_reason={self.invalid_output_reason}"
        )


def summarize_generate_content_response(
    *,
    probe_id: str,
    response: types.GenerateContentResponse,
) -> ResearchProviderObservation:
    candidates = tuple(response.candidates or ())
    metadata = candidates[0].grounding_metadata if candidates else None
    response_text = response.text if isinstance(response.text, str) else ""
    invalid_output_reason = _diagnose_invalid_output_reason(
        response_text=response_text,
        metadata=metadata,
    )
    return ResearchProviderObservation(
        probe_id=probe_id,
        surface="generate_content",
        status="completed",
        candidate_count=len(candidates),
        grounding_metadata_present=metadata is not None,
        grounding_chunk_count=len(tuple(metadata.grounding_chunks or ()))
        if metadata is not None
        else 0,
        grounding_support_count=len(tuple(metadata.grounding_supports or ()))
        if metadata is not None
        else 0,
        invalid_output_reason=invalid_output_reason,
    )


def summarize_interaction(
    *,
    probe_id: str,
    interaction: object,
) -> ResearchProviderObservation:
    steps = tuple(getattr(interaction, "steps", None) or ())
    step_types = tuple(
        str(step_type)
        for step in steps
        if (step_type := getattr(step, "type", None)) is not None
    )
    return ResearchProviderObservation(
        probe_id=probe_id,
        surface="interactions",
        status=str(getattr(interaction, "status", "unknown")),
        step_types=step_types,
        google_search_call_count=step_types.count("google_search_call"),
        google_search_result_count=step_types.count("google_search_result"),
        model_output_count=step_types.count("model_output"),
        citation_annotation_count=_count_model_output_annotations(steps),
    )


def summarize_probe_error(
    *,
    probe_id: str,
    surface: ProbeSurface,
    exc: Exception,
) -> ResearchProviderObservation:
    return ResearchProviderObservation(
        probe_id=probe_id,
        surface=surface,
        status="error",
        error_class=type(exc).__name__,
        api_status=_exception_api_status(exc),
    )


async def run_adk_research_service_probe(
    *,
    client: genai.Client,
    prompt: str,
) -> ResearchProviderObservation:
    del client
    try:
        settings = load_vertex_ai_settings(os.environ)
        service = ResearchExpertService.from_vertex_settings(settings)
        result = await service.research(
            ResearchExpertInput(
                question=prompt,
                objective=(
                    "Return only current public evidence with validated "
                    "Google Search grounding."
                ),
            )
        )
    except ResearchExpertServiceError as exc:
        reason = (
            exc.invalid_output_reason.value
            if exc.invalid_output_reason is not None
            else "none"
        )
        return ResearchProviderObservation(
            probe_id="adk-research-service",
            surface="adk_research_service",
            status=exc.status.value,
            invalid_output_reason=reason,
        )
    except Exception as exc:
        return summarize_probe_error(
            probe_id="adk-research-service",
            surface="adk_research_service",
            exc=exc,
        )
    metadata_present = result.evidence is not None
    return ResearchProviderObservation(
        probe_id="adk-research-service",
        surface="adk_research_service",
        status=result.status.value,
        grounding_metadata_present=metadata_present,
        grounding_chunk_count=len(result.evidence.source_ids)
        if result.evidence is not None
        else 0,
        grounding_support_count=result.evidence.grounding_support_count
        if result.evidence is not None
        else 0,
    )


async def run_generate_content_probe(
    *,
    client: genai.Client,
    prompt: str,
) -> ResearchProviderObservation:
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,
                max_output_tokens=2_048,
            ),
        )
    except Exception as exc:
        return summarize_probe_error(
            probe_id="generate-content-google-search",
            surface="generate_content",
            exc=exc,
        )
    return summarize_generate_content_response(
        probe_id="generate-content-google-search",
        response=response,
    )


async def run_interactions_probe(
    *,
    client: genai.Client,
    prompt: str,
    model: str,
    tools_enabled: bool,
) -> ResearchProviderObservation:
    model_label = model.replace("gemini-", "").replace("-flash", "")
    probe_id = f"interactions-basic-{model_label}"
    if tools_enabled:
        probe_id = f"interactions-google-search-{model_label}"
    body: dict[str, object] = {
        "model": model,
        "input": prompt,
        "store": False,
        "generation_config": {
            "temperature": 0.0,
            "max_output_tokens": 2_048,
        },
    }
    if tools_enabled:
        body["tools"] = [{"type": "google_search"}]
    try:
        interaction = await client.aio.interactions.create(**body)
    except Exception as exc:
        return summarize_probe_error(
            probe_id=probe_id,
            surface="interactions",
            exc=exc,
        )
    return summarize_interaction(probe_id=probe_id, interaction=interaction)


async def run_interactions_forced_extra_body_probe(
    *,
    client: genai.Client,
    prompt: str,
) -> ResearchProviderObservation:
    probe_id = "interactions-forced-extra-body-google-search-3.7"
    try:
        interaction = await client.aio.interactions.create(
            model="gemini-3.7-flash",
            input=prompt,
            tools=[{"type": "google_search"}],
            store=False,
            extra_body={
                "tool_choice": {
                    "allowed_tools": {
                        "mode": "any",
                        "tools": ["google_search"],
                    }
                }
            },
        )
    except Exception as exc:
        return summarize_probe_error(
            probe_id=probe_id,
            surface="interactions",
            exc=exc,
        )
    return summarize_interaction(probe_id=probe_id, interaction=interaction)


async def run_research_provider_compatibility_check(
    *,
    prompt: str = DEFAULT_PROMPT,
) -> tuple[ResearchProviderObservation, ...]:
    load_dotenv(".env")
    try:
        settings = load_vertex_ai_settings(os.environ)
    except VertexAIConfigurationError as exc:
        return (
            summarize_probe_error(
                probe_id="configuration",
                surface="generate_content",
                exc=exc,
            ),
        )
    client = genai.Client(**settings.client_kwargs())
    try:
        return (
            await run_adk_research_service_probe(client=client, prompt=prompt),
            await run_generate_content_probe(client=client, prompt=prompt),
            await run_interactions_probe(
                client=client,
                prompt=prompt,
                model="gemini-3.6-flash",
                tools_enabled=False,
            ),
            await run_interactions_probe(
                client=client,
                prompt=prompt,
                model="gemini-3.6-flash",
                tools_enabled=True,
            ),
            await run_interactions_probe(
                client=client,
                prompt=prompt,
                model="gemini-3.7-flash",
                tools_enabled=False,
            ),
            await run_interactions_probe(
                client=client,
                prompt=prompt,
                model="gemini-3.7-flash",
                tools_enabled=True,
            ),
            await run_interactions_forced_extra_body_probe(
                client=client,
                prompt=prompt,
            ),
        )
    finally:
        try:
            await client.aio.aclose()
        finally:
            client.close()


def _diagnose_invalid_output_reason(
    *,
    response_text: str,
    metadata: types.GroundingMetadata | None,
) -> str:
    outcome = diagnose_grounded_research_text(
        response_text=response_text,
        metadata=metadata,
    )
    if outcome.result.status is ExpertStatus.COMPLETED:
        return "none"
    reason = outcome.invalid_output_reason
    if isinstance(reason, ResearchInvalidOutputReason):
        return reason.value
    return "normalized_result_validation_failed"


def _count_model_output_annotations(steps: Iterable[object]) -> int:
    total = 0
    for step in steps:
        if getattr(step, "type", None) != "model_output":
            continue
        for block in tuple(getattr(step, "content", None) or ()):
            total += len(tuple(getattr(block, "annotations", None) or ()))
    return total


def _exception_api_status(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    return str(status) if status is not None else "none"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run metadata-only Research provider compatibility probes."
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Probe prompt. The prompt is sent to the provider but never logged.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    observations = asyncio.run(
        run_research_provider_compatibility_check(prompt=args.prompt)
    )
    for observation in observations:
        print(observation.to_report_line())


if __name__ == "__main__":
    main()
