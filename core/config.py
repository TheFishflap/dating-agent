"""Konfiguration: YAML (config/config.yaml + optional config.local.yaml) plus .env.

Secrets (API-Keys) kommen ausschließlich aus Umgebungsvariablen / .env.
Sicherheitsriegel: dry_run wird erzwungen, solange DATING_AGENT_ALLOW_LIVE != "yes".
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "config.yaml"
LOCAL_CONFIG = PROJECT_ROOT / "config" / "config.local.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class DeviceConfig:
    name: str
    platform: str
    avd: dict[str, Any]
    console_port: int
    appium: dict[str, Any]

    @property
    def serial(self) -> str:
        return f"emulator-{self.console_port}"


@dataclass
class Config:
    raw: dict[str, Any]
    dry_run: bool
    devices: list[DeviceConfig] = field(default_factory=list)

    @property
    def android_sdk(self) -> Path:
        env = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
        return Path(env or self.raw["paths"]["android_sdk"]).expanduser()

    @property
    def data_dir(self) -> Path:
        return _resolve(self.raw["paths"]["data_dir"])

    @property
    def log_dir(self) -> Path:
        return _resolve(self.raw["paths"]["log_dir"])

    @property
    def agent(self) -> dict[str, Any]:
        return self.raw["agent"]

    @property
    def delays(self) -> dict[str, Any]:
        return self.raw["delays"]

    def platform(self, name: str) -> dict[str, Any]:
        return self.raw["platforms"][name]

    def device(self, name: str | None = None) -> DeviceConfig:
        if name is None:
            if len(self.devices) != 1:
                raise ValueError("Mehrere Geräte konfiguriert — bitte --device angeben.")
            return self.devices[0]
        for dev in self.devices:
            if dev.name == name:
                return dev
        raise KeyError(f"Gerät '{name}' nicht in der Config.")


def _resolve(p: str | Path) -> Path:
    path = Path(p).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_config(path: str | Path | None = None) -> Config:
    load_dotenv(PROJECT_ROOT / ".env")

    path = Path(path or os.environ.get("DATING_AGENT_CONFIG") or DEFAULT_CONFIG)
    raw = yaml.safe_load(_resolve(path).read_text())
    if path == DEFAULT_CONFIG and LOCAL_CONFIG.exists():
        raw = _deep_merge(raw, yaml.safe_load(LOCAL_CONFIG.read_text()) or {})

    allow_live = os.environ.get("DATING_AGENT_ALLOW_LIVE", "").strip().lower() == "yes"
    dry_run = bool(raw.get("dry_run", True)) or not allow_live

    devices = [
        DeviceConfig(
            name=d["name"],
            platform=d["platform"],
            avd=d["avd"],
            console_port=int(d["console_port"]),
            appium=d.get("appium", {"enabled": False}),
        )
        for d in raw.get("devices", [])
    ]
    _check_unique_ports(devices)
    return Config(raw=raw, dry_run=dry_run, devices=devices)


def _check_unique_ports(devices: list[DeviceConfig]) -> None:
    seen: dict[int, str] = {}
    for d in devices:
        ports = [d.console_port, d.console_port + 1]
        if d.appium.get("enabled"):
            ports.append(int(d.appium["system_port"]))
        for p in ports:
            if p in seen:
                raise ValueError(f"Port {p} doppelt vergeben ({seen[p]} / {d.name}).")
            seen[p] = d.name
