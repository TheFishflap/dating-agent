"""Auswertung: Agent-Entscheidung vs. meine eigene Bewertung (aus --feedback-Läufen).

    python -m agent.calibration
"""
from __future__ import annotations

import glob
import json

from core.config import load_config


def main() -> None:
    cfg = load_config()
    rows = [json.loads(line)
            for f in sorted(glob.glob(str(cfg.log_dir / "decisions" / "*.jsonl")))
            for line in open(f, encoding="utf-8")]
    rows = [r for r in rows if r.get("user_action") and r.get("action")]
    if not rows:
        print("Noch keine Bewertungen mit --feedback.")
        return

    agree = sum(r["action"] == r["user_action"] for r in rows)
    print(f"{len(rows)} Profile, Übereinstimmung {agree}/{len(rows)} "
          f"({agree / len(rows):.0%})\n")
    print(f"{'Name':<14}{'Score':>5}  {'Körper':<11}{'Agent':<7}{'Du':<6}")
    for r in rows:
        d, p = r["decision"], r["decision"]["profile"]
        mark = "" if r["action"] == r["user_action"] else "  ✗"
        print(f"{(p.get('name') or '?')[:13]:<14}{str(d.get('attractiveness')):>5}  "
              f"{p.get('body_type', '?'):<11}{_short(r['action']):<7}{_short(r['user_action']):<6}{mark}")

    liked = sorted(r["decision"]["attractiveness"] for r in rows
                   if r["user_action"] == "swipe_right" and r["decision"].get("attractiveness"))
    passed = sorted(r["decision"]["attractiveness"] for r in rows
                    if r["user_action"] == "swipe_left" and r["decision"].get("attractiveness"))
    print(f"\nScores deiner Likes:  {liked}")
    print(f"Scores deiner Passes: {passed}")


def _short(action: str | None) -> str:
    return {"swipe_right": "Like", "swipe_left": "Pass"}.get(action or "", "—")


if __name__ == "__main__":
    main()
