"""Plattformname → App-Layer-Klasse."""
from __future__ import annotations

from platforms.base import PlatformApp


def get_platform_class(name: str) -> type[PlatformApp]:
    if name == "bumble":
        from platforms.bumble.app import BumbleApp
        return BumbleApp
    raise KeyError(f"Unbekannte Plattform: {name}")
