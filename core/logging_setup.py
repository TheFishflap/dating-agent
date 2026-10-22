"""Logging: menschenlesbares Log auf Konsole + Datei, Entscheidungen als JSONL."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def setup_logging(log_dir: Path, level: str = "INFO", instance: str = "main") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_dir / f"{instance}.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    for noisy in ("httpx", "urllib3", "selenium"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger("dating_agent")


class DecisionLog:
    """Append-only JSONL, eine Datei pro Tag und Instanz."""

    def __init__(self, log_dir: Path, instance: str):
        self.dir = log_dir / "decisions"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.instance = instance

    def write(self, record: dict[str, Any]) -> Path:
        now = datetime.now(timezone.utc)
        path = self.dir / f"{now:%Y-%m-%d}_{self.instance}.jsonl"
        entry = {"ts": now.isoformat(), "instance": self.instance, **record}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path


def prune_old_files(directory: Path, max_age_days: int) -> int:
    if not directory.exists():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for f in directory.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    return removed
