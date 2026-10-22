"""Gerätezugriff, den alle Plattformen teilen: ADB (Screenshots, Shell) und Appium-Session."""
from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

from core.config import Config, DeviceConfig
from emulator.avd import SdkTools

log = logging.getLogger(__name__)


class Adb:
    def __init__(self, config: Config, device: DeviceConfig):
        self.bin = SdkTools(config.android_sdk).adb
        self.serial = device.serial

    def _cmd(self, *args: str) -> list[str]:
        return [self.bin, "-s", self.serial, *args]

    def screenshot_png(self) -> bytes:
        """PNG-Bytes des aktuellen Bildschirms (exec-out vermeidet CRLF-Probleme)."""
        res = subprocess.run(self._cmd("exec-out", "screencap", "-p"),
                             check=True, capture_output=True, timeout=20)
        if not res.stdout.startswith(b"\x89PNG"):
            raise RuntimeError("screencap lieferte kein PNG — Gerät gesperrt/nicht bereit?")
        return res.stdout

    def shell(self, *args: str) -> str:
        res = subprocess.run(self._cmd("shell", *args), check=True,
                             capture_output=True, text=True, timeout=20)
        return res.stdout

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None:
        self.shell("input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    def tap(self, x: int, y: int) -> None:
        self.shell("input", "tap", str(x), str(y))

    def ui_nodes(self) -> list[dict]:
        """UI-Hierarchie per uiautomator (ohne Appium): Knoten mit Text/ID/Mittelpunkt."""
        res = subprocess.run(self._cmd("exec-out", "uiautomator", "dump", "/dev/tty"),
                             capture_output=True, text=True, timeout=20)
        nodes = []
        for attrs in re.findall(r"<node ([^>]*)>", res.stdout):
            a = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", a.get("bounds", ""))
            if not m:
                continue
            x1, y1, x2, y2 = map(int, m.groups())
            nodes.append({"text": a.get("text", ""), "id": a.get("resource-id", ""),
                          "center": ((x1 + x2) // 2, (y1 + y2) // 2)})
        return nodes

    def vertical_swipe(self, x: int, y_start: int, y_end: int, duration_ms: int) -> None:
        """Rein senkrechte Wischgeste (gleiches x) — wird nie als Links/Rechts-Swipe gewertet."""
        self.shell("input", "swipe", str(x), str(y_start), str(x), str(y_end), str(duration_ms))

    def foreground_package(self) -> str | None:
        out = self.shell("dumpsys", "window")
        for line in out.splitlines():
            if "mCurrentFocus" in line and "/" in line:
                return line.split()[-1].split("/")[0].rstrip("}")
        return None

    def screen_size(self) -> tuple[int, int]:
        out = self.shell("wm", "size")  # "Physical size: 1080x2400"
        w, h = out.strip().split()[-1].split("x")
        return int(w), int(h)


class AppiumSession:
    """Lazy Appium-Verbindung; nur nötig für UI-Baum und Gesten."""

    def __init__(self, device: DeviceConfig, app_package: str):
        self.device = device
        self.app_package = app_package
        self._driver: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.device.appium.get("enabled"))

    @property
    def driver(self):
        if self._driver is None:
            from appium import webdriver
            from appium.options.android import UiAutomator2Options

            opts = UiAutomator2Options()
            opts.platform_name = "Android"
            opts.automation_name = "UiAutomator2"
            opts.udid = self.device.serial
            opts.system_port = int(self.device.appium["system_port"])
            opts.no_reset = True                 # Login/App-Daten nie anfassen
            opts.app_package = self.app_package
            opts.auto_launch = False             # App nicht neu starten
            opts.new_command_timeout = 600
            log.info("Verbinde Appium %s → %s", self.device.appium["url"], self.device.serial)
            self._driver = webdriver.Remote(self.device.appium["url"], options=opts)
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            finally:
                self._driver = None
