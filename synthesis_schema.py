from schemas import SynthesisBlueprint


LOCAL_ONLY_SCHEMA_KEYWORDS = frozenset(
    {"minLength", "maxLength", "pattern"}
)
NAMED_SCHEMA_MAPPINGS = frozenset({"$defs", "properties"})


def adapt_schema_for_gemini(
    schema: dict[str, object],
) -> dict[str, object]:
    """Return a provider-safe copy of a canonical JSON schema."""
    return _adapt_schema_node(schema)


def build_gemini_response_schema() -> dict[str, object]:
    """Build the Gemini response schema from the canonical model."""
    return adapt_schema_for_gemini(
        SynthesisBlueprint.model_json_schema()
    )


def _adapt_schema_node(
    node: dict[str, object],
) -> dict[str, object]:
    adapted: dict[str, object] = {}
    for key, value in node.items():
        if key in LOCAL_ONLY_SCHEMA_KEYWORDS:
            continue
        if key in NAMED_SCHEMA_MAPPINGS and isinstance(value, dict):
            adapted[key] = {
                name: _adapt_schema_value(child)
                for name, child in value.items()
            }
            continue
        adapted[key] = _adapt_schema_value(value)
    return adapted


def _adapt_schema_value(value: object) -> object:
    if isinstance(value, dict):
        return _adapt_schema_node(value)
    if isinstance(value, list):
        return [_adapt_schema_value(item) for item in value]
    return value
