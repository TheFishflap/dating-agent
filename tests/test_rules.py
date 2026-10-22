import pytest

pytest.importorskip("pydantic")

from agent.decision import Decision  # noqa: E402
from agent.rules import apply_rules  # noqa: E402

RULES = {"instant_like_score": 9, "min_score": 7,
         "exclude_body_types": ["overweight"], "exclude_smoking": ["regularly"]}


def make(score, body="athletic", smoking="no", dealbreaker=False, screen="profile", multi=False):
    return Decision.model_validate({
        "screen_type": screen, "multiple_profiles_visible": multi, "attractiveness": score,
        "dealbreaker_hit": dealbreaker, "action": "skip", "reason": "", "confidence": 0.5,
        "profile": {"body_type": body, "smoking": smoking},
    })


@pytest.mark.parametrize("decision,expected", [
    (make(10, body="overweight", smoking="regularly"), "swipe_right"),  # 10/10 schlägt alles
    (make(9), "swipe_right"),
    (make(8, body="overweight"), "swipe_left"),
    (make(8, smoking="regularly"), "swipe_left"),
    (make(8, smoking="sometimes"), "swipe_right"),
    (make(8, dealbreaker=True), "swipe_left"),
    (make(7, body="unknown"), "swipe_right"),
    (make(6), "swipe_left"),
    (make(None), "skip"),
    (make(None, screen="other"), "skip"),
    (make(9, multi=True), "skip"),
])
def test_rules(decision, expected):
    assert apply_rules(decision, RULES)[0] == expected
