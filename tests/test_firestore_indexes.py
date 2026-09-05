import json
from pathlib import Path


INDEX_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "firestore.indexes.json"
)


def test_blueprint_payload_is_exempt_from_firestore_indexes() -> None:
    assert INDEX_CONFIG_PATH.is_file(), (
        "firestore.indexes.json must define repository-owned indexes."
    )
    config = json.loads(INDEX_CONFIG_PATH.read_text(encoding="utf-8"))

    matching_overrides = [
        override
        for override in config["fieldOverrides"]
        if override.get("collectionGroup") == "blueprints"
        and override.get("fieldPath") == "blueprint"
    ]
    assert matching_overrides == [
        {
            "collectionGroup": "blueprints",
            "fieldPath": "blueprint",
            "indexes": [],
        }
    ]


def test_agent_job_startup_drain_collection_group_index_exists() -> None:
    assert INDEX_CONFIG_PATH.is_file(), (
        "firestore.indexes.json must define repository-owned indexes."
    )
    config = json.loads(INDEX_CONFIG_PATH.read_text(encoding="utf-8"))

    matching_indexes = [
        index
        for index in config["indexes"]
        if index.get("collectionGroup") == "agent_jobs"
        and index.get("queryScope") == "COLLECTION_GROUP"
        and index.get("fields")
        == [
            {"fieldPath": "status", "order": "ASCENDING"},
            {"fieldPath": "action_kind", "order": "ASCENDING"},
            {"fieldPath": "created_at", "order": "ASCENDING"},
        ]
    ]

    assert matching_indexes == [
        {
            "collectionGroup": "agent_jobs",
            "queryScope": "COLLECTION_GROUP",
            "fields": [
                {"fieldPath": "status", "order": "ASCENDING"},
                {"fieldPath": "action_kind", "order": "ASCENDING"},
                {"fieldPath": "created_at", "order": "ASCENDING"},
            ],
        }
    ]
