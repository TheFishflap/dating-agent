"""Entscheidungsschleife (Meilenstein 1: Trockenlauf).

Ablauf pro Durchgang:
  aktive Stunden abwarten → Screenshot → hat sich der Bildschirm geändert? →
  Claude entscheidet → JSONL-Log → (nur live: Swipe) → Delay-Modul.

Im Trockenlauf wird nichts ausgeführt. Damit trotzdem neue Profile kommen,
swipest du selbst im Emulator; die Schleife bewertet jeden neuen Bildschirm.
"""
from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

from agent.decision import DecisionEngine, DecisionError
from agent.rules import apply_rules
from core.config import Config, DeviceConfig
from core.delays import DelayManager
from core.imaging import hamming, image_fingerprint
from core.logging_setup import DecisionLog, prune_old_files
from platforms.base import PlatformApp, Screen
from platforms.registry import get_platform_class

log = logging.getLogger(__name__)

class StopLoop(Exception):
    """Sicherheits-Stopp im Live-Betrieb (Swipe ohne Wirkung, Tageslimit)."""


SKIP_SCREENS = {Screen.OTHER_APP, Screen.PAYWALL, Screen.OUT_OF_PROFILES}


class AgentLoop:
    def __init__(self, config: Config, device: DeviceConfig,
                 engine: DecisionEngine | None = None, app: PlatformApp | None = None,
                 feedback: bool = False):
        self.config = config
        self.feedback = feedback
        self.device = device
        self.delays = DelayManager(
            config.delays,
            state_file=config.data_dir / "state" / f"limits_{device.name}.json",
            dry_run=config.dry_run,
        )
        self.app = app or get_platform_class(device.platform)(config, device, self.delays)
        self.engine = engine or DecisionEngine(config.agent, work_dir=config.data_dir / "tmp" / device.name)
        self.decisions = DecisionLog(config.log_dir, device.name)
        self.shot_dir = config.data_dir / "screenshots" / device.name
        self._last_fp: int | None = None       # Bildschirm nach der letzten Bewertung
        self._last_top_fp: int | None = None   # Profilanfang der letzten Bewertung
        self._at_top = False                   # nach eigenem Swipe steht das neue Profil oben

        log_cfg = config.raw["logging"]
        self.keep_screenshots = bool(log_cfg.get("keep_screenshots", True))
        removed = prune_old_files(self.shot_dir, int(log_cfg.get("screenshot_retention_days", 7)))
        if removed:
            log.info("%d alte Screenshots gelöscht.", removed)

    # ---------- Ein Durchgang ----------

    def step(self, force: bool = False) -> dict | None:
        self.delays.wait_for_active_hours()

        screen = self._safe_detect()
        if screen in SKIP_SCREENS:
            log.info("Bildschirm: %s — nichts zu bewerten.", screen.value)
            return None

        png = self.app.screenshot()
        fp = image_fingerprint(png)
        if not force and self._last_fp is not None and hamming(fp, self._last_fp) <= 6:
            return None  # unverändert
        scrolling = (self.config.agent.get("scroll_profile", True)
                     and hasattr(self.app, "capture_profile"))

        shots = [png]
        if scrolling:
            top = self.app.stable_screenshot() if self._at_top else self.app.scroll_to_top()
            self._at_top = False
            top_fp = image_fingerprint(top)
            if (not force and self._last_top_fp is not None
                    and hamming(top_fp, self._last_top_fp) <= 6):
                # nur innerhalb des schon bewerteten Profils gescrollt → zurück zu den Knöpfen
                self._last_fp = image_fingerprint(self.app.scroll_to_bottom())
                return None
            self._last_top_fp = top_fp
            # "Profil ansehen" — im Trockenlauf skaliert, simuliert Lesedauer
            self.delays.pause("view_profile")
            log.info("Neues Profil — scrolle durch, bitte nicht eingreifen …")
            shots = self.app.capture_profile(
                int(self.config.agent.get("max_profile_shots", 5)), top=top)
            if self.config.dry_run:
                # ganz nach unten zu den Knöpfen (die drücke ich im Trockenlauf selbst)
                self._last_fp = image_fingerprint(self.app.scroll_to_bottom())
            else:
                self._last_fp = image_fingerprint(shots[-1])
        else:
            self._last_fp = fp
            self.delays.pause("view_profile")

        shot_paths = [p for p in (self._save_screenshot(s) for s in shots) if p]
        record: dict = {
            "platform": self.device.platform,
            "dry_run": self.config.dry_run,
            "detected_screen": screen.value,
            "screenshots": [str(p) for p in shot_paths],
        }
        try:
            decision, meta = self.engine.decide(shots)
        except DecisionError as e:
            log.warning("Keine Entscheidung: %s", e)
            self.decisions.write({**record, "error": str(e)})
            return None

        action, rule_reason = apply_rules(decision, self.config.agent.get("rules", {}))
        limit_ok = action == "skip" or self.delays.can_act(action)
        record.update(
            action=action,
            rule=rule_reason,
            llm_action=decision.action,
            decision=decision.model_dump(),
            api=meta,
            limit_ok=limit_ok,
            executed=False,
        )

        live = not self.config.dry_run
        stop_reason = None
        if live and action != "skip" and not limit_ok:
            stop_reason = f"Tageslimit für {action} erreicht"
        if action != "skip" and limit_ok:
            if live:
                try:
                    executed = (self.app.swipe_right() if action == "swipe_right"
                                else self.app.swipe_left())
                except Exception as e:  # z. B. UnknownDialog
                    executed, stop_reason = False, str(e)
                record["executed"] = executed
                self._at_top = bool(executed)
                if not executed and not stop_reason:
                    stop_reason = f"{action} ohne Wirkung"
            else:
                # Trockenlauf: im separaten _dryrun-Zähler verbuchen
                self.delays.record(action)
            self.delays.pause("between_swipes")
            self.delays.after_action()

        if decision.multiple_profiles_visible:
            # Während des Scrollens wurde weitergeswiped → aktuellen Bildschirm neu bewerten
            log.info("Profilwechsel während der Erfassung erkannt — bewerte neu.")
            record["interrupted"] = True
            self._last_fp = None
            self._last_top_fp = None

        if live and action == "skip":
            # unklarer Fall (Match-Popup, Werbung, kein Score) → ich entscheide selbst
            log.warning("⚠ %s — bitte selbst erledigen, Agent wartet.", rule_reason)
            self._signal_ready(sound="Basso")
        else:
            self._signal_ready()
        if self.feedback and decision.screen_type == "profile":
            record["user_action"] = self._ask_user()
        self.decisions.write(record)
        p = decision.profile
        log.info("→ %s | Score %s | %s, %s | %s | %s/%s [%d Bilder]\n   %s",
                 action, decision.attractiveness, p.name or "?", p.age or "?", rule_reason,
                 p.body_type, p.smoking, len(shots), decision.reason)
        if stop_reason:
            raise StopLoop(stop_reason)
        return record

    # ---------- Schleife ----------

    def run(self, once: bool = False, max_steps: int | None = None) -> None:
        log.info("Agent startet: Gerät=%s Plattform=%s dry_run=%s",
                 self.device.name, self.device.platform, self.config.dry_run)
        steps = 0
        poll = float(self.config.agent.get("poll_interval_s", 4))
        try:
            while True:
                result = self.step(force=once)
                if once:
                    return
                if result is not None:
                    steps += 1
                    if max_steps and steps >= max_steps:
                        return
                if not (result and result.get("executed")):  # nach eigenem Swipe sofort weiter
                    time.sleep(poll)
        except KeyboardInterrupt:
            log.info("Abgebrochen.")
        except StopLoop as e:
            log.error("Sicherheits-Stopp: %s", e)
            self._signal_ready(sound="Basso")
        finally:
            self.app.close()

    # ---------- Hilfen ----------

    def _ask_user(self) -> str | None:
        """Kalibrierung: meine eigene Bewertung abfragen (vor Anzeige der Agent-Entscheidung)."""
        answers = {"r": "swipe_right", "l": "swipe_left"}
        while True:
            raw = input("   Deine Bewertung — r = Like, l = Pass, Enter = auslassen: ").strip().lower()
            if raw in answers:
                return answers[raw]
            if raw == "":
                return None

    def _signal_ready(self, sound: str | None = None) -> None:
        """Hinweis an mich: Agent ist fertig (Trockenlauf: ich kann bewerten)."""
        if self.config.dry_run:
            log.info("✓ Fertig — du kannst jetzt bewerten.")
        sound = sound or self.config.agent.get("ready_sound")
        if sound:
            subprocess.Popen(["afplay", f"/System/Library/Sounds/{sound}.aiff"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _safe_detect(self) -> Screen:
        try:
            return self.app.detect_screen()
        except Exception as e:  # Appium nicht erreichbar etc. → LLM entscheidet allein
            log.warning("Bildschirmerkennung fehlgeschlagen (%s) — fahre ohne fort.", e)
            return Screen.UNKNOWN

    def _save_screenshot(self, png: bytes) -> Path | None:
        if not self.keep_screenshots:
            return None
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        path = self.shot_dir / f"{datetime.now():%Y%m%d_%H%M%S_%f}.png"
        path.write_bytes(png)
        return path
