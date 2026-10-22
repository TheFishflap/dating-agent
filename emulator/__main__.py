"""CLI: python -m emulator {check|list|create|start|stop|status} [--device NAME]"""
from __future__ import annotations

import argparse
import sys

from core.config import load_config
from core.logging_setup import setup_logging
from emulator.avd import AvdManager


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m emulator")
    p.add_argument("command", choices=["check", "list", "create", "start", "stop", "status"])
    p.add_argument("--device", help="Name aus devices[] (Default: einziges Gerät)")
    p.add_argument("--all", action="store_true", help="auf alle konfigurierten Geräte anwenden")
    p.add_argument("--wait", action="store_true", help="start: auf Boot warten")
    p.add_argument("--force", action="store_true", help="create: bestehendes AVD überschreiben")
    p.add_argument("--install-image", action="store_true",
                   help="create: System-Image vorher per sdkmanager laden (Download!)")
    args = p.parse_args(argv)

    cfg = load_config()
    setup_logging(cfg.log_dir, cfg.raw["logging"]["level"], instance="emulator")
    mgr = AvdManager(cfg)

    if args.command == "check":
        print(f"SDK-Pfad: {cfg.android_sdk}")
        missing = False
        for tool, path in mgr.sdk.check().items():
            print(f"  {tool:<11} {path or 'FEHLT'}")
            missing |= path is None
        return 1 if missing else 0

    if args.command == "list":
        print("\n".join(mgr.list_avds()) or "(keine AVDs)")
        return 0

    devices = cfg.devices if args.all else [cfg.device(args.device)]
    for dev in devices:
        if args.command == "create":
            if args.install_image:
                mgr.install_image(dev)
            mgr.create(dev, force=args.force)
        elif args.command == "start":
            mgr.start(dev, wait=args.wait)
        elif args.command == "stop":
            mgr.stop(dev)
        elif args.command == "status":
            state = "läuft" if mgr.is_running(dev) else "gestoppt"
            print(f"{dev.name:<12} {dev.avd['name']:<20} {dev.serial:<15} {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
