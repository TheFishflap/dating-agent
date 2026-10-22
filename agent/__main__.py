"""CLI: python -m agent --device bumble-1 [--once] [--max-steps N]"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from agent.loop import AgentLoop
from core.config import load_config
from core.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m agent")
    p.add_argument("--device", help="Name aus devices[] (Default: einziges Gerät)")
    p.add_argument("--once", action="store_true", help="aktuellen Bildschirm einmal bewerten")
    p.add_argument("--max-steps", type=int, help="nach N bewerteten Bildschirmen beenden")
    p.add_argument("--feedback", action="store_true",
                   help="nach jedem Profil eigene Bewertung (r/l) abfragen — Kalibrierung")
    p.add_argument("--no-appium", action="store_true",
                   help="nur ADB-Screenshots, keine UI-Erkennung")
    args = p.parse_args(argv)

    cfg = load_config()
    dev = cfg.device(args.device)
    if args.no_appium:
        dev.appium["enabled"] = False
    setup_logging(cfg.log_dir, cfg.raw["logging"]["level"], instance=dev.name)
    log = logging.getLogger("dating_agent")

    if cfg.agent.get("backend", "claude_cli") == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY nicht gesetzt — .env prüfen "
                    "(oder per `ant auth login` angemeldet sein).")
    if not cfg.dry_run:
        log.warning("LIVE-MODUS: Swipes werden ausgeführt.")

    AgentLoop(cfg, dev, feedback=args.feedback).run(once=args.once, max_steps=args.max_steps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
