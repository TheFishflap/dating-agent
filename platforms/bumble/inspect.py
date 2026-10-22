"""Hilfswerkzeug: aktuellen Bildschirm + UI-Hierarchie speichern, um Selektoren zu finden.

    python -m platforms.bumble.inspect --device bumble-1

Rein lesend — führt keine Gesten aus.
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime

from core.config import load_config
from core.delays import DelayManager
from core.logging_setup import setup_logging
from platforms.bumble.app import BumbleApp


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--device")
    args = p.parse_args()

    cfg = load_config()
    setup_logging(cfg.log_dir, "INFO", instance="inspect")
    dev = cfg.device(args.device)
    delays = DelayManager(cfg.delays, cfg.data_dir / "state" / f"limits_{dev.name}.json")
    app = BumbleApp(cfg, dev, delays)

    out = cfg.data_dir / "inspect"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (out / f"{stamp}.png").write_bytes(app.screenshot())
    try:
        xml = app.page_source()
        (out / f"{stamp}.xml").write_text(xml, encoding="utf-8")
        ids = sorted(set(re.findall(r'resource-id="([^"]+)"', xml)))
        descs = sorted(set(re.findall(r'content-desc="([^"]+)"', xml)))
        print(f"Vordergrund: {app.adb.foreground_package()}")
        print(f"\nresource-ids ({len(ids)}):\n  " + "\n  ".join(ids))
        print(f"\ncontent-desc ({len(descs)}):\n  " + "\n  ".join(descs))
    finally:
        app.close()
    print(f"\nGespeichert unter {out}/{stamp}.*")


if __name__ == "__main__":
    main()
