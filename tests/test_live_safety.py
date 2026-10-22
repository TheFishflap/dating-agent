"""Live-Sicherungen der Schleife mit Fake-App und Fake-Engine (ohne Emulator/Claude)."""
import io

import pytest

pytest.importorskip("pydantic")
from PIL import Image  # noqa: E402

from agent.decision import Decision  # noqa: E402
from agent.loop import AgentLoop, StopLoop  # noqa: E402
from core.config import load_config  # noqa: E402
from platforms.base import Screen  # noqa: E402


def png(shade):
    buf = io.BytesIO()
    Image.new("L", (40, 80), shade).save(buf, format="PNG")
    return buf.getvalue()


class FakeApp:
    def __init__(self, swipe_ok):
        self.swipe_ok, self.swipes = swipe_ok, []

    def detect_screen(self): return Screen.UNKNOWN
    def screenshot(self): return png(100)
    def stable_screenshot(self): return png(100)
    def scroll_to_top(self): return png(100)
    def scroll_to_bottom(self): return png(100)
    def capture_profile(self, n, top=None): return [png(100)]
    def close(self): pass

    def swipe_right(self):
        self.swipes.append("right")
        return self.swipe_ok

    swipe_left = swipe_right


class FakeEngine:
    def decide(self, shots):
        return Decision.model_validate({
            "screen_type": "profile", "multiple_profiles_visible": False, "attractiveness": 9,
            "dealbreaker_hit": False, "action": "swipe_right", "reason": "", "confidence": 1,
            "profile": {}}), {}


@pytest.fixture
def live_cfg(tmp_path):
    cfg = load_config()
    cfg.dry_run = False
    cfg.raw["paths"] = {**cfg.raw["paths"], "data_dir": str(tmp_path), "log_dir": str(tmp_path)}
    cfg.raw["agent"] = {**cfg.raw["agent"], "ready_sound": ""}
    cfg.raw["delays"] = {**cfg.raw["delays"], "dry_run_time_scale": 0}
    return cfg


def _loop(cfg, app):
    loop = AgentLoop(cfg, cfg.device(), engine=FakeEngine(), app=app)
    loop.delays._sleep = lambda s: None
    return loop


def test_swipe_executed(live_cfg):
    app = FakeApp(swipe_ok=True)
    rec = _loop(live_cfg, app).step(force=True)
    assert rec["executed"] is True and app.swipes == ["right"]


def test_swipe_without_effect_stops(live_cfg):
    with pytest.raises(StopLoop):
        _loop(live_cfg, FakeApp(swipe_ok=False)).step(force=True)


def test_daily_limit_stops(live_cfg):
    live_cfg.raw["delays"]["daily_limits"] = {"swipe_right": 0}
    app = FakeApp(swipe_ok=True)
    with pytest.raises(StopLoop):
        _loop(live_cfg, app).step(force=True)
    assert app.swipes == []
