"""Bumble-App-Layer: Screenshot (ADB), Bildschirmerkennung und Swipes (Appium/UiAutomator2).

Im Trockenlauf loggen swipe_left/swipe_right nur, was sie tun würden.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import yaml

from core.config import PROJECT_ROOT
from core.imaging import same_screen
from platforms.base import PlatformApp, Screen

log = logging.getLogger(__name__)


class UnknownDialog(Exception):
    """Nach einem Swipe erscheint ein Dialog, den der Agent nicht kennt."""

_BY = {
    "id": lambda v: ("id", v),
    "text": lambda v: ("-android uiautomator", f'new UiSelector().text("{v}")'),
    "desc": lambda v: ("accessibility id", v),
}


class BumbleApp(PlatformApp):
    name = "bumble"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dialog_free: set[str] = set()  # Richtungen ohne Bestätigungsdialog
        sel_path = PROJECT_ROOT / self.platform_cfg["selectors_file"]
        self.selectors: dict[str, Any] = yaml.safe_load(sel_path.read_text())

    # ---------- Erkennung ----------

    def find(self, locators: list[dict[str, str]]):
        """Erstes passendes Element oder None. Benötigt Appium."""
        if not self.appium.enabled:
            return None
        drv = self.appium.driver
        for loc in locators:
            by, value = _BY[loc["by"]](loc["value"])
            found = drv.find_elements(by, value)
            if found:
                return found[0]
        return None

    def detect_screen(self) -> Screen:
        if not self.is_foreground():
            return Screen.OTHER_APP
        if not self.appium.enabled:
            return Screen.UNKNOWN  # ohne Appium entscheidet das LLM anhand des Screenshots
        for screen in (Screen.MATCH_POPUP, Screen.PAYWALL,
                       Screen.OUT_OF_PROFILES, Screen.ENCOUNTERS):
            locators = self.selectors["screens"].get(screen.value, [])
            if locators and self.find(locators) is not None:
                return screen
        return Screen.UNKNOWN

    def page_source(self) -> str:
        return self.appium.driver.page_source

    # ---------- Profil erfassen (nur Scrollen, kein Swipe) ----------

    def stable_screenshot(self, timeout: float = 6.0) -> bytes:
        """Wartet, bis der Bildschirm stillsteht (Scroll-Schwung, Karten-Animation)."""
        prev = self.screenshot()
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.15)
            cur = self.screenshot()
            if same_screen(cur, prev):
                return cur
            prev = cur
        return prev

    def scroll_to_top(self, max_scrolls: int = 10) -> bytes:
        """Scrollt zum Profilanfang (Foto mit Name/Alter) und liefert diesen Screenshot."""
        shot = self.stable_screenshot()
        for _ in range(max_scrolls):
            self._scroll("up", reading=False)
            nxt = self.stable_screenshot()
            if same_screen(nxt, shot):
                break
            shot = nxt
        return shot

    def scroll_to_bottom(self, max_scrolls: int = 10) -> bytes:
        """Scrollt ans Profilende (Like-/Pass-Knöpfe) und liefert diesen Screenshot."""
        shot = self.stable_screenshot()
        for _ in range(max_scrolls):
            self._scroll("down", reading=False)
            nxt = self.stable_screenshot()
            if same_screen(nxt, shot):
                break
            shot = nxt
        return shot

    def capture_profile(self, max_shots: int = 5, top: bytes | None = None) -> list[bytes]:
        """Erfasst das Profil von oben nach unten und liefert die Screenshots.

        Erlaubt auch im Trockenlauf: Scrollen löst weder Like noch Pass aus.
        Das Profil bleibt danach unten stehen — dort liegen Like-/Pass-Knöpfe.
        """
        shots = [top if top is not None else self.scroll_to_top()]
        for _ in range(max_shots - 1):
            self._scroll("down")
            shot = self.stable_screenshot()
            if same_screen(shot, shots[-1]):  # Ende erreicht / kein scrollbares Profil
                break
            shots.append(shot)
        return shots

    def _scroll(self, direction: str, reading: bool = True) -> None:
        w, h = self.adb.screen_size()
        rng = self.delays.rng
        x = int(w * rng.uniform(0.45, 0.55))
        # oben unterhalb von Header/Premium-Banner (bis ~18 %), unten über der Navigationsleiste
        top, bottom = int(h * rng.uniform(0.24, 0.27)), int(h * rng.uniform(0.84, 0.87))
        y1, y2 = (bottom, top) if direction == "down" else (top, bottom)
        duration = int(rng.uniform(380, 650))
        self.adb.vertical_swipe(x, y1, y2, duration)
        if reading:
            self.delays.pause("scroll_profile")

    # ---------- Gesten ----------

    def swipe_left(self) -> bool:
        return self._swipe("left")

    def swipe_right(self) -> bool:
        return self._swipe("right")

    def _swipe(self, direction: str) -> bool:
        action = f"swipe_{direction}"
        if self.dry_run:
            log.info("[DRY-RUN] %s nicht ausgeführt.", action)
            return False
        if not self.delays.can_act(action):
            log.warning("Tageslimit für %s erreicht — übersprungen.", action)
            return False

        self.delays.pause("before_tap")
        before = self.screenshot()
        w, h = self.adb.screen_size()
        rng = self.delays.rng
        y = int(h * rng.uniform(0.42, 0.55))
        start, end = (rng.uniform(0.22, 0.32), rng.uniform(0.82, 0.92))
        if direction == "left":
            start, end = 1 - start, 1 - end
        # waagerecht mit leichter natürlicher Abweichung in y
        self.adb.swipe(int(w * start), y, int(w * end), y + int(h * rng.uniform(-0.02, 0.02)),
                       int(rng.uniform(180, 320)))
        time.sleep(0.6)
        # Bestätigungsdialog kommt nur beim ersten Swipe je Richtung → danach UI-Dump (2 s) sparen
        if direction not in self._dialog_free:
            dialog = self._handle_dialog()
            if dialog == "unknown":
                raise UnknownDialog(f"Unbekannter Dialog nach {action}")
            if dialog is None:
                self._dialog_free.add(direction)
        after = self.stable_screenshot()
        if same_screen(before, after):
            log.error("%s hatte keine Wirkung (Bildschirm unverändert).", action)
            return False
        self.delays.record(action)
        log.info("%s ausgeführt.", action)
        return True

    def _handle_dialog(self) -> str | None:
        """Prüft auf einen Dialog nach dem Swipe. Rückgabe: None | "confirmed" | "unknown"."""
        cfg = self.selectors.get("confirm_dialogs", {})
        nodes = self.adb.ui_nodes()
        positive = next((n for n in nodes if n["id"] == cfg.get("positive_id")), None)
        if positive is None:
            return None
        title = next((n["text"] for n in nodes if n["id"] == cfg.get("title_id")), "")
        if title not in cfg.get("titles", []):
            log.error("Unbekannter Dialog: %r", title)
            return "unknown"
        log.info("Bestätigungsdialog %r → %s", title, positive["text"])
        self.delays.pause("before_tap")
        self.adb.tap(*positive["center"])
        time.sleep(0.8)
        if any(n["id"] == cfg.get("positive_id") for n in self.adb.ui_nodes()):
            log.error("Dialog %r nach Tippen noch offen.", title)
            return "unknown"
        return "confirmed"

    def _swipe_area(self) -> dict[str, int]:
        card = self.find(self.selectors["elements"]["profile_card"])
        if card is not None:
            r = card.rect
            return {"left": r["x"], "top": r["y"], "width": r["width"], "height": r["height"]}
        w, h = self.adb.screen_size()
        a = self.selectors["swipe_area"]
        return {"left": int(a["left"] * w), "top": int(a["top"] * h),
                "width": int(a["width"] * w), "height": int(a["height"] * h)}
