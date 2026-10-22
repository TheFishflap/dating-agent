"""Feste Entscheidungsregeln (Config `agent.rules`) auf Basis der von Claude erkannten Merkmale.

Claude liefert Merkmale + einen eigenen Vorschlag; die finale Aktion kommt von hier,
damit sie nachvollziehbar und per Config einstellbar ist.
"""
from __future__ import annotations

from typing import Any

from agent.decision import Decision


def apply_rules(decision: Decision, rules: dict[str, Any]) -> tuple[str, str]:
    """Gibt (Aktion, Regel-Begründung) zurück."""
    if decision.screen_type != "profile" or decision.multiple_profiles_visible:
        return "skip", "kein einzelnes Profil"
    score = decision.attractiveness
    if score is None:
        return "skip", "kein Attraktivitäts-Score"

    p = decision.profile
    if score >= int(rules.get("instant_like_score", 9)):
        return "swipe_right", f"Score {score} ≥ {rules.get('instant_like_score', 9)} → direkt Like"

    if p.body_type in rules.get("exclude_body_types", []):
        return "swipe_left", f"Ausschluss: Körpertyp {p.body_type}"
    if p.smoking in rules.get("exclude_smoking", []):
        return "swipe_left", f"Ausschluss: raucht ({p.smoking})"
    if decision.dealbreaker_hit:
        return "swipe_left", "Ausschluss: Dealbreaker im Profiltext"

    min_score = int(rules.get("min_score", 7))
    if score >= min_score:
        return "swipe_right", f"Score {score} ≥ {min_score}, kein Ausschluss"
    return "swipe_left", f"Score {score} < {min_score}"
