"""Dialog-Behandlung nach dem Swipe mit Fake-ADB."""
import pytest

pytest.importorskip("yaml")

from core.config import load_config  # noqa: E402
from core.delays import DelayManager  # noqa: E402
from platforms.bumble.app import BumbleApp  # noqa: E402

YES = {"id": "android:id/button1", "text": "YES", "center": (894, 1369)}


def title(t):
    return {"id": "com.bumble.app:id/alertTitle", "text": t, "center": (0, 0)}


class FakeAdb:
    def __init__(self, screens):
        self.screens, self.taps = list(screens), []

    def ui_nodes(self):
        return self.screens.pop(0) if self.screens else []

    def tap(self, x, y):
        self.taps.append((x, y))


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    cfg = load_config()
    delays = DelayManager(cfg.delays, tmp_path / "l.json", dry_run=True, sleep=lambda s: None)
    return BumbleApp(cfg, cfg.device(), delays)


def test_no_dialog(app):
    app.adb = FakeAdb([[]])
    assert app._handle_dialog() is None and app.adb.taps == []


def test_known_dialog_confirmed(app):
    app.adb = FakeAdb([[title("Interested?"), YES], []])
    assert app._handle_dialog() == "confirmed" and app.adb.taps == [(894, 1369)]


def test_unknown_dialog_not_tapped(app):
    app.adb = FakeAdb([[title("Upgrade to Premium?"), YES]])
    assert app._handle_dialog() == "unknown" and app.adb.taps == []


def test_dialog_still_open_after_tap(app):
    app.adb = FakeAdb([[title("Interested?"), YES], [title("Interested?"), YES]])
    assert app._handle_dialog() == "unknown"
