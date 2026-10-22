"""Delay-Modul: menschlich wirkende Pausen, Sitzungsrhythmus, aktive Stunden, Tageslimits.

Bewusst nur stdlib, damit es ohne Emulator/API testbar ist.

- Pausen sind log-normal verteilt (rechtsschief wie echte Reaktionszeiten),
  gekappt auf [min, max].
- Gelegentliche Mikropausen, nach N Aktionen eine längere Sitzungspause.
- Tageslimits werden pro Tag in einer JSON-Datei gezählt. Trockenlauf und
  Live-Betrieb nutzen getrennte Zähler, damit Tests die echten Limits nicht
  verbrauchen.
"""
from __future__ import annotations

import json
import logging
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class PauseSpec:
    median: float
    sigma: float
    min: float
    max: float

    def sample(self, rng: random.Random) -> float:
        value = rng.lognormvariate(math.log(self.median), self.sigma)
        return max(self.min, min(self.max, value))


class DailyLimitReached(Exception):
    pass


class DelayManager:
    def __init__(
        self,
        cfg: dict[str, Any],
        state_file: Path,
        dry_run: bool = True,
        rng: random.Random | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = datetime.now,
    ):
        self.cfg = cfg
        self.dry_run = dry_run
        self.rng = rng or random.Random()
        self._sleep = sleep
        self._now = now
        self.time_scale = float(cfg.get("dry_run_time_scale", 1.0)) if dry_run else 1.0
        self.pauses = {k: PauseSpec(**v) for k, v in cfg["actions"].items()}
        self.limits: dict[str, int] = dict(cfg.get("daily_limits", {}))

        self.state_file = state_file.with_name(
            state_file.stem + ("_dryrun" if dry_run else "") + state_file.suffix
        )
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._actions_in_session = 0
        self._session_target = self._new_session_target()

    # ---------- Pausen ----------

    def pause(self, kind: str) -> float:
        """Schläft eine zufällige Zeit für die Aktionsart; gibt Sekunden zurück."""
        seconds = self.pauses[kind].sample(self.rng)
        mb = self.cfg.get("micro_break")
        if mb and self.rng.random() < mb["probability"]:
            extra = self.rng.uniform(mb["min"], mb["max"])
            log.info("Mikropause %.0fs", extra * self.time_scale)
            seconds += extra
        return self._do_sleep(seconds, kind)

    def after_action(self) -> float:
        """Nach jeder (simulierten) Aktion aufrufen; legt ggf. Sitzungspause ein."""
        self._actions_in_session += 1
        if self._actions_in_session < self._session_target:
            return 0.0
        s = self.cfg["session"]
        seconds = self.rng.uniform(s["break_min_s"], s["break_max_s"])
        log.info("Sitzungspause nach %d Aktionen: %.0fs",
                 self._actions_in_session, seconds * self.time_scale)
        self._actions_in_session = 0
        self._session_target = self._new_session_target()
        return self._do_sleep(seconds, "session_break")

    def wait_for_active_hours(self) -> float:
        """Blockiert bis zum Beginn des aktiven Zeitfensters (falls außerhalb)."""
        window = self.cfg.get("active_hours")
        if not window:
            return 0.0
        start, end = _parse_hm(window["start"]), _parse_hm(window["end"])
        now = self._now()
        if start <= now.time() <= end:
            return 0.0
        target = datetime.combine(now.date(), start)
        if now.time() > end:
            target += timedelta(days=1)
        seconds = (target - now).total_seconds()
        seconds += self.rng.uniform(0, 900)  # nicht exakt zur vollen Startzeit
        log.info("Außerhalb der aktiven Stunden — warte bis ~%s", target.strftime("%H:%M"))
        # Wartezeit bis zum Fenster wird nicht skaliert; im Dry-Run nur loggen.
        if self.dry_run:
            return 0.0
        self._sleep(seconds)
        return seconds

    def _do_sleep(self, seconds: float, label: str) -> float:
        scaled = seconds * self.time_scale
        log.debug("Pause %-14s %.2fs (roh %.2fs)", label, scaled, seconds)
        self._sleep(scaled)
        return scaled

    def _new_session_target(self) -> int:
        s = self.cfg["session"]
        return self.rng.randint(s["actions_min"], s["actions_max"])

    # ---------- Tageslimits ----------

    def remaining(self, action: str) -> int:
        counts = self._load_counts()
        total_left = self.limits.get("total", 10**9) - sum(counts.values())
        action_left = self.limits.get(action, 10**9) - counts.get(action, 0)
        return max(0, min(total_left, action_left))

    def can_act(self, action: str) -> bool:
        return self.remaining(action) > 0

    def record(self, action: str) -> None:
        state = self._load_state()
        today = self._today()
        state.setdefault(today, {})
        state[today][action] = state[today].get(action, 0) + 1
        # nur die letzten 14 Tage behalten
        for day in sorted(state)[:-14]:
            del state[day]
        self.state_file.write_text(json.dumps(state, indent=2))

    def _load_state(self) -> dict[str, dict[str, int]]:
        if not self.state_file.exists():
            return {}
        try:
            return json.loads(self.state_file.read_text())
        except json.JSONDecodeError:
            log.warning("Limit-Statusdatei defekt, starte neu: %s", self.state_file)
            return {}

    def _load_counts(self) -> dict[str, int]:
        return self._load_state().get(self._today(), {})

    def _today(self) -> str:
        return self._now().date().isoformat()


def _parse_hm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))

