from dataclasses import dataclass
from enum import StrEnum
from ipaddress import ip_address
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from google.genai import types

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from expert_contracts import ExpertCapability, ExpertResult, ExpertStatus
from schemas import AgentActionReceipt, CitationReference

SOURCE_EXPERT_MODEL_NAME = "gemini-3.6-flash"
SOURCE_EXPERT_TIMEOUT_SECONDS = 45

SourceTaskText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]
SourceConstraintText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
]
SourceEvidenceText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]
SourceInterpretationText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
SourceId = Annotated[
    str,
    StringConstraints(pattern=r"^source-[1-3]$"),
]
SourceLabel = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]

_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


class StrictSourceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class SourceExpertInput(StrictSourceModel):
    """Minimal user-authored task data allowed into the Source boundary."""

    objective: SourceTaskText
    urls: tuple[HttpUrl, ...] = Field(min_length=1, max_length=3)
    constraints: tuple[SourceConstraintText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )

    @field_validator("urls")
    @classmethod
    def validate_public_urls(
        cls,
        urls: tuple[HttpUrl, ...],
    ) -> tuple[HttpUrl, ...]:
        for url in urls:
            if url.username is not None or url.password is not None:
                raise ValueError("Source URLs cannot contain credentials.")
            host = (url.host or "").rstrip(".").lower()
            if host == "localhost" or host.endswith(".localhost"):
                raise ValueError("Source URLs must be public.")
            address_host = host[1:-1] if host.startswith("[") else host
            try:
                address = ip_address(address_host)
            except ValueError:
                if "." not in host or host.endswith(
                    (".internal", ".local", ".test", ".invalid")
                ):
                    raise ValueError("Source URLs must be public.")
                continue
            if not address.is_global:
                raise ValueError("Source URLs must be public.")
        return urls

    @model_validator(mode="after")
    def validate_unique_urls(self) -> Self:
        normalized_urls = tuple(str(url) for url in self.urls)
        if len(set(normalized_urls)) != len(normalized_urls):
            raise ValueError("Source URLs must be unique.")
        return self


class SourceRetrievalStatus(StrEnum):
    RETRIEVED = "retrieved"
    ERROR = "error"
    PAYWALL = "paywall"
    UNSAFE = "unsafe"


class SourceStatementDraft(StrictSourceModel):
    text: SourceEvidenceText
    source_ids: tuple[SourceId, ...] = Field(min_length=1, max_length=3)

    @field_validator("source_ids")
    @classmethod
    def validate_unique_source_ids(
        cls,
        source_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("Statement source identifiers must be unique.")
        return source_ids


class SourceExpertDraft(StrictSourceModel):
    facts: tuple[SourceStatementDraft, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    requirements: tuple[SourceStatementDraft, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    constraints: tuple[SourceStatementDraft, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    assumptions: tuple[SourceInterpretationText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )
    open_questions: tuple[SourceInterpretationText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )

    @model_validator(mode="after")
    def require_evidenced_statement(self) -> Self:
        if not (self.facts or self.requirements or self.constraints):
            raise ValueError("Source output requires evidenced content.")
        return self


class SourceDocumentResult(StrictSourceModel):
    source_id: SourceId
    url: HttpUrl
    retrieval_status: SourceRetrievalStatus
    evidence_summary: SourceEvidenceText | None = None


class SourceProviderSource(StrictSourceModel):
    source_id: SourceId
    uri: HttpUrl
    label: SourceLabel


class SourceStatement(StrictSourceModel):
    text: SourceEvidenceText
    source_ids: tuple[SourceId, ...] = Field(min_length=1, max_length=3)


class SourceExpertPayload(StrictSourceModel):
    documents: tuple[SourceDocumentResult, ...] = Field(
        min_length=1,
        max_length=3,
    )
    facts: tuple[SourceStatement, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    requirements: tuple[SourceStatement, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    constraints: tuple[SourceStatement, ...] = Field(
        default_factory=tuple,
        max_length=8,
    )
    assumptions: tuple[SourceInterpretationText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )
    open_questions: tuple[SourceInterpretationText, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )
    sources: tuple[SourceProviderSource, ...] = Field(
        min_length=1,
        max_length=3,
    )


class SourceExpertEvidence(StrictSourceModel):
    source_ids: tuple[SourceId, ...] = Field(min_length=1, max_length=3)
    grounded_statement_count: int = Field(ge=1, le=24)
    grounding_support_count: int = Field(ge=1, le=40)


class SourceExpertResult(
    ExpertResult[SourceExpertPayload, SourceExpertEvidence]
):
    capability: Literal[ExpertCapability.SOURCE] = ExpertCapability.SOURCE

    @model_validator(mode="after")
    def validate_completed_evidence(self) -> Self:
        if self.status is not ExpertStatus.COMPLETED:
            return self
        assert self.payload is not None
        assert self.evidence is not None
        payload_source_ids = tuple(
            source.source_id for source in self.payload.sources
        )
        if self.evidence.source_ids != payload_source_ids:
            raise ValueError("Source evidence does not match payload sources.")
        statement_count = sum(
            len(statements)
            for statements in (
                self.payload.facts,
                self.payload.requirements,
                self.payload.constraints,
            )
        )
        if self.evidence.grounded_statement_count != statement_count:
            raise ValueError(
                "Source evidence does not match grounded statements."
            )
        return self


@dataclass(frozen=True, slots=True)
class SourceExpertReceipts:
    actions: tuple[AgentActionReceipt, ...] = ()
    citations: tuple[CitationReference, ...] = ()


_PROVIDER_STATUS_MAP = {
    types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_SUCCESS: (
        SourceRetrievalStatus.RETRIEVED
    ),
    types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_ERROR: (
        SourceRetrievalStatus.ERROR
    ),
    types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_PAYWALL: (
        SourceRetrievalStatus.PAYWALL
    ),
    types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_UNSAFE: (
        SourceRetrievalStatus.UNSAFE
    ),
}


def _invalid_source_result() -> SourceExpertResult:
    return SourceExpertResult(status=ExpertStatus.INVALID_OUTPUT)


def _normalize_url(value: object) -> str | None:
    try:
        return str(_HTTP_URL_ADAPTER.validate_python(value))
    except ValidationError:
        return None


def _response_text(candidate: types.Candidate) -> str:
    if candidate.content is None:
        return ""
    return "".join(
        part.text
        for part in candidate.content.parts or ()
        if isinstance(part.text, str) and not part.thought
    ).strip()


def extract_grounded_statements(
    *,
    request: SourceExpertInput,
    response: types.GenerateContentResponse,
) -> tuple[SourceStatement, ...]:
    """Extract only provider-grounded segments from a URL Context response."""
    candidates = tuple(response.candidates or ())
    if len(candidates) != 1:
        return ()
    candidate = candidates[0]
    allowed_source_ids = {
        str(url): f"source-{index}"
        for index, url in enumerate(request.urls, start=1)
    }
    url_metadata = candidate.url_context_metadata
    retrievals = (
        tuple(url_metadata.url_metadata or ())
        if url_metadata is not None
        else ()
    )
    if len(retrievals) != len(allowed_source_ids):
        return ()

    retrieved_source_ids: set[str] = set()
    seen_source_ids: set[str] = set()
    for retrieval in retrievals:
        normalized_url = _normalize_url(retrieval.retrieved_url)
        source_id = allowed_source_ids.get(normalized_url or "")
        if source_id is None or source_id in seen_source_ids:
            return ()
        seen_source_ids.add(source_id)
        if (
            retrieval.url_retrieval_status
            is types.UrlRetrievalStatus.URL_RETRIEVAL_STATUS_SUCCESS
        ):
            retrieved_source_ids.add(source_id)
        elif retrieval.url_retrieval_status not in _PROVIDER_STATUS_MAP:
            return ()
    if seen_source_ids != set(allowed_source_ids.values()):
        return ()

    metadata = candidate.grounding_metadata
    supports = tuple(metadata.grounding_supports or ()) if metadata else ()
    chunks = tuple(metadata.grounding_chunks or ()) if metadata else ()
    if not supports or len(supports) > 40 or not chunks:
        return ()

    source_ids_by_chunk: dict[int, str] = {}
    for chunk_index, chunk in enumerate(chunks):
        web = chunk.web
        normalized_uri = _normalize_url(web.uri if web else None)
        source_id = allowed_source_ids.get(normalized_uri or "")
        if source_id in retrieved_source_ids:
            source_ids_by_chunk[chunk_index] = source_id

    response_text = _response_text(candidate)
    grounded_statements: list[SourceStatement] = []
    seen_statements: set[tuple[str, tuple[str, ...]]] = set()
    for support in supports:
        indices = tuple(support.grounding_chunk_indices or ())
        if not indices or any(
            index not in source_ids_by_chunk for index in indices
        ):
            return ()
        segment_text = support.segment.text if support.segment else None
        if not segment_text and support.segment is not None:
            start = support.segment.start_index
            end = support.segment.end_index
            if start is not None and end is not None:
                segment_text = response_text[start:end]
        if not segment_text:
            return ()
        source_ids = tuple(
            dict.fromkeys(source_ids_by_chunk[index] for index in indices)
        )
        try:
            statement = SourceStatement(
                text=segment_text,
                source_ids=source_ids,
            )
        except ValidationError:
            return ()
        statement_key = (statement.text, statement.source_ids)
        if statement_key not in seen_statements:
            grounded_statements.append(statement)
            seen_statements.add(statement_key)
    return tuple(grounded_statements)


def _grounded_source_ids(
    *,
    statement: SourceStatementDraft,
    response_text: str,
    supports: tuple[types.GroundingSupport, ...],
    source_ids_by_chunk: dict[int, str],
) -> tuple[str, ...] | None:
    grounded_source_ids: list[str] = []
    for support in supports:
        indices = tuple(support.grounding_chunk_indices or ())
        if any(index not in source_ids_by_chunk for index in indices):
            return None
        segment_text = support.segment.text if support.segment else None
        if not segment_text and support.segment is not None:
            start = support.segment.start_index
            end = support.segment.end_index
            if start is not None and end is not None:
                segment_text = response_text[start:end]
        if not segment_text or statement.text != segment_text.strip():
            continue
        for index in indices:
            source_id = source_ids_by_chunk[index]
            if source_id not in grounded_source_ids:
                grounded_source_ids.append(source_id)
    if set(grounded_source_ids) != set(statement.source_ids):
        return None
    return tuple(
        source_id
        for source_id in statement.source_ids
        if source_id in grounded_source_ids
    )


def normalize_source_response(
    *,
    request: SourceExpertInput,
    response: types.GenerateContentResponse,
) -> SourceExpertResult:
    """Bind a Source draft to allowlisted raw provider evidence."""
    candidates = tuple(response.candidates or ())
    if len(candidates) != 1:
        return _invalid_source_result()
    candidate = candidates[0]
    response_text = _response_text(candidate)
    try:
        draft = SourceExpertDraft.model_validate_json(response_text)
    except ValidationError:
        return _invalid_source_result()

    allowed_source_ids = {
        str(url): f"source-{index}"
        for index, url in enumerate(request.urls, start=1)
    }
    url_metadata = candidate.url_context_metadata
    retrievals = (
        tuple(url_metadata.url_metadata or ())
        if url_metadata is not None
        else ()
    )
    if len(retrievals) != len(allowed_source_ids):
        return _invalid_source_result()

    documents_by_id: dict[str, SourceDocumentResult] = {}
    for retrieval in retrievals:
        normalized_url = _normalize_url(retrieval.retrieved_url)
        source_id = allowed_source_ids.get(normalized_url or "")
        provider_status = retrieval.url_retrieval_status
        retrieval_status = _PROVIDER_STATUS_MAP.get(provider_status)
        if (
            source_id is None
            or retrieval_status is None
            or source_id in documents_by_id
        ):
            return _invalid_source_result()
        documents_by_id[source_id] = SourceDocumentResult(
            source_id=source_id,
            url=normalized_url,
            retrieval_status=retrieval_status,
        )
    if set(documents_by_id) != set(allowed_source_ids.values()):
        return _invalid_source_result()

    metadata = candidate.grounding_metadata
    supports = tuple(metadata.grounding_supports or ()) if metadata else ()
    chunks = tuple(metadata.grounding_chunks or ()) if metadata else ()
    if not supports or len(supports) > 40 or not chunks:
        return _invalid_source_result()

    source_ids_by_chunk: dict[int, str] = {}
    provider_sources_by_id: dict[str, SourceProviderSource] = {}
    for chunk_index, chunk in enumerate(chunks):
        web = chunk.web
        normalized_uri = _normalize_url(web.uri if web else None)
        source_id = allowed_source_ids.get(normalized_uri or "")
        if source_id is None:
            continue
        document = documents_by_id[source_id]
        if document.retrieval_status is not SourceRetrievalStatus.RETRIEVED:
            continue
        host = urlsplit(normalized_uri).hostname or "Public source"
        label = ((web.title if web else None) or host).strip()[:160]
        try:
            provider_source = SourceProviderSource(
                source_id=source_id,
                uri=normalized_uri,
                label=label,
            )
        except ValidationError:
            return _invalid_source_result()
        source_ids_by_chunk[chunk_index] = source_id
        provider_sources_by_id[source_id] = provider_source

    normalized_groups: list[tuple[SourceStatement, ...]] = []
    referenced_source_ids: set[str] = set()
    all_draft_groups = (draft.facts, draft.requirements, draft.constraints)
    for group in all_draft_groups:
        normalized_statements: list[SourceStatement] = []
        for statement in group:
            grounded_source_ids = _grounded_source_ids(
                statement=statement,
                response_text=response_text,
                supports=supports,
                source_ids_by_chunk=source_ids_by_chunk,
            )
            if not grounded_source_ids:
                return _invalid_source_result()
            normalized_statements.append(
                SourceStatement(
                    text=statement.text,
                    source_ids=grounded_source_ids,
                )
            )
            referenced_source_ids.update(grounded_source_ids)
        normalized_groups.append(tuple(normalized_statements))

    if not referenced_source_ids:
        return _invalid_source_result()
    provider_sources = tuple(
        provider_sources_by_id[source_id]
        for source_id in allowed_source_ids.values()
        if source_id in referenced_source_ids
        and source_id in provider_sources_by_id
    )
    if len(provider_sources) != len(referenced_source_ids):
        return _invalid_source_result()

    statements = tuple(
        statement
        for group in normalized_groups
        for statement in group
    )
    documents = tuple(
        documents_by_id[source_id].model_copy(
            update={
                "evidence_summary": next(
                    (
                        statement.text
                        for statement in statements
                        if source_id in statement.source_ids
                    ),
                    None,
                )
            }
        )
        for source_id in allowed_source_ids.values()
    )
    failed_count = sum(
        document.retrieval_status is not SourceRetrievalStatus.RETRIEVED
        for document in documents
    )
    limitations = (
        (f"{failed_count} source could not be retrieved.",)
        if failed_count == 1
        else (
            (f"{failed_count} sources could not be retrieved.",)
            if failed_count
            else ()
        )
    )
    payload = SourceExpertPayload(
        documents=documents,
        facts=normalized_groups[0],
        requirements=normalized_groups[1],
        constraints=normalized_groups[2],
        assumptions=draft.assumptions,
        open_questions=draft.open_questions,
        sources=provider_sources,
    )
    evidence = SourceExpertEvidence(
        source_ids=tuple(source.source_id for source in provider_sources),
        grounded_statement_count=len(statements),
        grounding_support_count=len(supports),
    )
    return SourceExpertResult(
        status=ExpertStatus.COMPLETED,
        summary=(
            f"Source analysis produced {len(statements)} grounded "
            f"statement{'s' if len(statements) != 1 else ''} from "
            f"{len(provider_sources)} retrieved "
            f"source{'s' if len(provider_sources) != 1 else ''}."
        ),
        limitations=limitations,
        payload=payload,
        evidence=evidence,
    )


def build_source_receipts(
    result: SourceExpertResult,
) -> SourceExpertReceipts:
    """Map validated Source evidence to existing public chat receipts."""
    if result.status is not ExpertStatus.COMPLETED or result.payload is None:
        return SourceExpertReceipts()
    return SourceExpertReceipts(
        actions=(
            AgentActionReceipt(
                action_name="url_context",
                status="completed",
            ),
        ),
        citations=tuple(
            CitationReference(uri=source.uri, label=source.label)
            for source in result.payload.sources
        ),
    )
