import re
from collections.abc import Mapping


_MEMORY_RETRIEVAL_OR_HISTORY = re.compile(
    r"\b(?:do|did|can|could)\s+you\s+(?:remember|recall)\s+"
    r"(?:when|what|where|who|how|if|whether)\b|"
    r"\b(?:do|did|can|could)\s+you\s+(?:remember|recall)\s+"
    r"(?:my|our)\b|"
    r"\b(?:do|did|can|could)\s+you\s+(?:remember|recall)\s+"
    r"(?:me|us)\s+(?:telling|saying|mentioning)\s+you\b|"
    r"\bwhat\s+(?:do|did|have)\s+(?:you\s+)?"
    r"(?:remember|recall|know|tell|told|say|said|mention|mentioned)\b|"
    r"\bwhat\s+(?:kind|type|style)\s+of\s+.+\s+do\s+i\s+"
    r"(?:like|prefer|want|use)\b|"
    r"\bwhat\s+.+\s+do\s+i\s+(?:like|prefer|want|use)\b|"
    r"\bwhat\s+(?:is|are)\s+my\s+"
    r"(?:preferred|default|usual|normal|typical)\b|"
    r"\bwhat\s+(?:did|have)\s+i\s+(?:tell|say|mention)\s+you\b|"
    r"\bwhat\s+(?:was|were)\s+my\s+preferences?\b"
    r".*\b(?:last|before|previous|previously|prior|earlier)\b",
    re.IGNORECASE | re.DOTALL,
)
_MEMORY_FALLBACK_SOCIAL_GREETING = re.compile(
    r"(?:hi|hello|hey|yo|sup|"
    r"(?:good )?(?:morning|afternoon|evening))"
    r"(?: (?:agent )?col)?"
    r"(?: (?:(?:hows|how is) (?:it|your day) going|how are you(?: doing)?))?"
    r"(?: today| this morning| this afternoon| this evening)?"
    r"|(?:hows|how is) (?:it|your day) going"
    r"(?: today| this morning| this afternoon| this evening)?"
    r"|(?:hows|how is) everything"
    r"(?: today| this morning| this afternoon| this evening)?"
    r"|how are you(?: doing)?"
    r"(?: today| this morning| this afternoon| this evening)?"
    r"|hope (?:you are doing well|all is well)"
    r"(?: today| this morning| this afternoon| this evening)?",
)
_MEMORY_FALLBACK_SOCIAL_GRATITUDE = re.compile(
    r"thanks?|thank you|appreciate it|much appreciated",
)
_MEMORY_FALLBACK_SOCIAL_ACKNOWLEDGEMENT = re.compile(
    r"ok(?:ay)?|got it|sounds good|sure|yep|fair enough|alright|"
    r"all right|all good|no worries|no problem|that makes sense",
)
_MEMORY_FALLBACK_SOCIAL_REACTION = re.compile(
    r"lol|haha|nice|cool|awesome|perfect|thats (?:hilarious|funny)|"
    r"good to hear|glad to hear it",
)
_MEMORY_FALLBACK_EXTERNAL_TOPIC_INQUIRY = re.compile(
    r"what are your thoughts on .+|"
    r"what do you think(?: (?:of|about) .+)?|"
    r"how does .+ work",
)
_MEMORY_FALLBACK_CURRENT_TURN_ONLY = re.compile(
    r"^\s*(?:"
    r"for\s+this\s+(?:response|turn|message|answer|chat)\s+only\b.*|"
    r"(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"review\s+(?:this\s+)?code|"
    r"(?:please\s+)?fix\s+the\s+failing\s+tests|"
    r"(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"explain\s+this\s+function"
    r")\s*[.!?]*\s*$",
    re.IGNORECASE | re.DOTALL,
)
_MEMORY_CREATION_INTENT = re.compile(
    r"\b(?:remember|save|store|record|keep in mind|bear in mind|"
    r"note|make a note|propose remembering)\b",
)
_MEMORY_CONTEXT_USER_ANCHOR = re.compile(
    r"\b(?:i|my|mine|myself|we|our|us)\b|"
    r"\bfor me\b|\bwith me\b|\bhelps? me (?:more|work|understand)\b",
)
_MEMORY_CONTEXT_COLLABORATION_ANCHOR = re.compile(
    r"\b(?:collaboration|collaborate|when we|for code review|"
    r"review code|debugging ui|working with me)\b",
)
_MEMORY_CONTEXT_STANDING_ANCHOR = re.compile(
    r"\b(?:future|default|usual|usually|normal|normally|typical|"
    r"typically|always|tend to|tends to|works best|work better|"
    r"working better|easier|more useful|smoother|stick better)\b",
)
_MEMORY_CONTEXT_PROCESS_COMPARISON = re.compile(
    r"\b(?:matters more than|goes better|helps? me decide)\b",
)
_MEMORY_CONTEXT_TASK_WITH_COLLABORATION_MODIFIER = re.compile(
    r"^(?:review|fix|debug|explain|walk through|analyze)\b.+\b"
    r"(?:with|by keeping|using|source-backed|concise|findings first|"
    r"future explanations)\b",
)


def memory_clause_is_retrieval_or_history(clause: str) -> bool:
    return _MEMORY_RETRIEVAL_OR_HISTORY.search(clause) is not None


def memory_candidate_clause_is_excluded(clause: str) -> bool:
    return (
        memory_clause_is_retrieval_or_history(clause)
        or _is_memory_fallback_social_only_clause(clause)
        or _is_memory_fallback_external_topic_inquiry_clause(clause)
        or _MEMORY_FALLBACK_CURRENT_TURN_ONLY.match(clause) is not None
    )


def memory_candidate_clause_is_eligible(clause: str) -> bool:
    return (
        not memory_candidate_clause_is_excluded(clause)
        and _memory_candidate_clause_has_context_floor(clause)
    )


def memory_decision_evidence_is_excluded(
    decision: Mapping[str, object],
) -> bool:
    kind = decision.get("kind")
    if kind == "profile_candidate":
        evidence = decision.get("evidence_text")
        return (
            isinstance(evidence, str)
            and memory_candidate_clause_is_excluded(evidence)
        )
    if kind != "clarify":
        return False
    candidates = decision.get("candidates")
    if not isinstance(candidates, list):
        return False
    evidences = [
        candidate.get("evidence_text")
        for candidate in candidates
        if isinstance(candidate, Mapping)
        and isinstance(candidate.get("evidence_text"), str)
    ]
    return bool(evidences) and all(
        memory_candidate_clause_is_excluded(evidence)
        for evidence in evidences
    )


def memory_decision_evidence_is_ineligible(
    decision: Mapping[str, object],
) -> bool:
    kind = decision.get("kind")
    if kind == "profile_candidate":
        return _memory_profile_candidate_is_ineligible(decision)
    if kind != "clarify":
        return False
    candidates = decision.get("candidates")
    if not isinstance(candidates, list):
        return False
    evaluated_candidates = [
        candidate
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]
    return bool(evaluated_candidates) and all(
        _memory_profile_candidate_is_ineligible(candidate)
        for candidate in evaluated_candidates
    )


def _memory_profile_candidate_is_ineligible(
    candidate: Mapping[str, object],
) -> bool:
    evidence = candidate.get("evidence_text")
    if not isinstance(evidence, str):
        return False
    if memory_candidate_clause_is_excluded(evidence):
        return True
    if candidate.get("category") != "user_requested_memory":
        return False
    return not _memory_candidate_clause_has_context_floor(evidence)


def _memory_candidate_clause_has_context_floor(clause: str) -> bool:
    normalized = _normalize_memory_context_clause(clause)
    if not normalized:
        return False
    return any(
        pattern.search(normalized) is not None
        for pattern in (
            _MEMORY_CREATION_INTENT,
            _MEMORY_CONTEXT_USER_ANCHOR,
            _MEMORY_CONTEXT_COLLABORATION_ANCHOR,
            _MEMORY_CONTEXT_STANDING_ANCHOR,
            _MEMORY_CONTEXT_PROCESS_COMPARISON,
            _MEMORY_CONTEXT_TASK_WITH_COLLABORATION_MODIFIER,
        )
    )


def _is_memory_fallback_social_only_clause(clause: str) -> bool:
    normalized = _normalize_memory_fallback_social_clause(clause)
    if not normalized:
        return False
    return any(
        pattern.fullmatch(normalized) is not None
        for pattern in (
            _MEMORY_FALLBACK_SOCIAL_GREETING,
            _MEMORY_FALLBACK_SOCIAL_GRATITUDE,
            _MEMORY_FALLBACK_SOCIAL_ACKNOWLEDGEMENT,
            _MEMORY_FALLBACK_SOCIAL_REACTION,
        )
    )


def _normalize_memory_fallback_social_clause(clause: str) -> str:
    normalized = clause.lower().replace("’", "'")
    normalized = re.sub(r"\bhow[' ]?s\b", "hows", normalized)
    normalized = re.sub(r"\byou[' ]?re\b", "you are", normalized)
    normalized = re.sub(r"\bthat[' ]?s\b", "thats", normalized)
    normalized = re.sub(r"[^a-z0-9']+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _is_memory_fallback_external_topic_inquiry_clause(clause: str) -> bool:
    normalized = _normalize_memory_fallback_inquiry_clause(clause)
    if not normalized:
        return False
    return _MEMORY_FALLBACK_EXTERNAL_TOPIC_INQUIRY.fullmatch(normalized) is not None


def _normalize_memory_fallback_inquiry_clause(clause: str) -> str:
    normalized = clause.lower().replace("’", "'")
    normalized = re.sub(r"\bwhat[' ]?s\b", "what is", normalized)
    normalized = re.sub(r"[^a-z0-9']+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_memory_context_clause(clause: str) -> str:
    normalized = clause.lower().replace("’", "'")
    normalized = re.sub(r"\bi[' ]?m\b", "i am", normalized)
    normalized = re.sub(r"\bi[' ]?d\b", "i would", normalized)
    normalized = re.sub(r"\bi[' ]?ll\b", "i will", normalized)
    normalized = re.sub(r"\byou[' ]?re\b", "you are", normalized)
    normalized = re.sub(r"[^a-z0-9']+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
