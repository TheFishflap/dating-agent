"""Gemeinsame Schnittstelle für alle Dating-App-Layer."""
from __future__ import annotations

import abc
import enum
import logging

from core.config import Config, DeviceConfig
from core.delays import DelayManager
from platforms.device import Adb, AppiumSession

log = logging.getLogger(__name__)


class Screen(str, enum.Enum):
    ENCOUNTERS = "encounters"
    MATCH_POPUP = "match_popup"
    PAYWALL = "paywall"
    OUT_OF_PROFILES = "out_of_profiles"
    OTHER_APP = "other_app"
    UNKNOWN = "unknown"


class PlatformApp(abc.ABC):
    name: str = "base"

    def __init__(self, config: Config, device: DeviceConfig, delays: DelayManager):
        self.config = config
        self.device = device
        self.delays = delays
        self.dry_run = config.dry_run
        self.platform_cfg = config.platform(self.name)
        self.adb = Adb(config, device)
        self.appium = AppiumSession(device, self.platform_cfg["app_package"])

    def screenshot(self) -> bytes:
        return self.adb.screenshot_png()

    def is_foreground(self) -> bool:
        return self.adb.foreground_package() == self.platform_cfg["app_package"]

    @abc.abstractmethod
    def detect_screen(self) -> Screen: ...

    @abc.abstractmethod
    def swipe_left(self) -> bool: ...

    @abc.abstractmethod
    def swipe_right(self) -> bool: ...

    def close(self) -> None:
        self.appium.close()
