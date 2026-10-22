import random
from datetime import datetime

import pytest

from core.delays import DelayManager

CFG = {
    "dry_run_time_scale": 0.1,
    "actions": {"view_profile": {"median": 6.0, "sigma": 0.45, "min": 2.5, "max": 25}},
    "micro_break": {"probability": 0.0, "min": 20, "max": 90},
    "session": {"actions_min": 3, "actions_max": 3, "break_min_s": 600, "break_max_s": 600},
    "active_hours": {"start": "08:00", "end": "22:00"},
    "daily_limits": {"swipe_right": 2, "total": 3},
}


def make(tmp_path, dry_run=True, now=datetime(2026, 10, 4, 12, 0)):
    slept = []
    dm = DelayManager(CFG, tmp_path / "limits.json", dry_run=dry_run,
                      rng=random.Random(1), sleep=slept.append, now=lambda: now)
    return dm, slept


def test_pause_bounds_and_scaling(tmp_path):
    dm, slept = make(tmp_path)
    for _ in range(200):
        dm.pause("view_profile")
    assert all(0.25 <= s <= 2.5 for s in slept)  # [min,max] * 0.1


def test_live_mode_not_scaled(tmp_path):
    dm, slept = make(tmp_path, dry_run=False)
    dm.pause("view_profile")
    assert 2.5 <= slept[0] <= 25


def test_session_break_after_n_actions(tmp_path):
    dm, slept = make(tmp_path)
    assert dm.after_action() == 0 and dm.after_action() == 0
    assert dm.after_action() == pytest.approx(60.0)


def test_daily_limits(tmp_path):
    dm, _ = make(tmp_path)
    assert dm.remaining("swipe_right") == 2
    dm.record("swipe_right")
    dm.record("swipe_right")
    assert not dm.can_act("swipe_right")
    assert dm.remaining("swipe_left") == 1  # total-Limit greift
    dm.record("swipe_left")
    assert not dm.can_act("swipe_left")


def test_dry_run_uses_separate_counter(tmp_path):
    dry, _ = make(tmp_path, dry_run=True)
    dry.record("swipe_right")
    live, _ = make(tmp_path, dry_run=False)
    assert live.remaining("swipe_right") == 2
    assert dry.state_file != live.state_file


def test_outside_active_hours_dry_run_does_not_block(tmp_path):
    dm, slept = make(tmp_path, now=datetime(2026, 10, 4, 23, 30))
    assert dm.wait_for_active_hours() == 0.0
    assert slept == []
