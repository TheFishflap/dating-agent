import json

import pytest

pytest.importorskip("pydantic")
pytest.importorskip("anthropic")

from agent.decision import DECISION_SCHEMA, Decision, ProfileFacts  # noqa: E402


def _walk(schema):
    yield schema
    for sub in schema.get("properties", {}).values():
        yield from _walk(sub)


def test_schema_matches_models():
    assert set(DECISION_SCHEMA["required"]) == set(Decision.model_fields)
    prof = DECISION_SCHEMA["properties"]["profile"]
    assert set(prof["properties"]) == set(ProfileFacts.model_fields)
    for node in _walk(DECISION_SCHEMA):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])


def test_example_validates():
    example = {
        "screen_type": "profile", "multiple_profiles_visible": False, "attractiveness": 6,
        "dealbreaker_hit": False, "action": "skip", "reason": "Zu wenig Info.",
        "confidence": 0.4,
        "profile": {k: None for k in ProfileFacts.model_fields}
        | {"interests": [], "prompts": [], "red_flags": [],
           "smoking": "unknown", "body_type": "unknown"},
    }
    d = Decision.model_validate(json.loads(json.dumps(example)))
    assert d.action == "skip"
