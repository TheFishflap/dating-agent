"""AVD-Lebenszyklus über die SDK-Kommandozeilentools (sdkmanager, avdmanager, emulator, adb).

Alle Parameter kommen aus `devices[]` in der Config, damit später mehrere
Instanzen (ein AVD pro Plattform/Instanz) parallel laufen können.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path

from core.config import Config, DeviceConfig

log = logging.getLogger(__name__)


class SdkTools:
    def __init__(self, sdk_root: Path):
        self.root = sdk_root

    def _find(self, name: str, *candidates: str) -> str:
        for rel in candidates:
            p = self.root / rel
            if p.exists():
                return str(p)
        found = shutil.which(name)
        if found:
            return found
        raise FileNotFoundError(
            f"'{name}' nicht gefunden (SDK: {self.root}). Siehe README → Manuelle Schritte."
        )

    @property
    def adb(self) -> str:
        return self._find("adb", "platform-tools/adb")

    @property
    def emulator(self) -> str:
        return self._find("emulator", "emulator/emulator")

    @property
    def avdmanager(self) -> str:
        return self._find("avdmanager", "cmdline-tools/latest/bin/avdmanager")

    @property
    def sdkmanager(self) -> str:
        return self._find("sdkmanager", "cmdline-tools/latest/bin/sdkmanager")

    def check(self) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        for tool in ("adb", "emulator", "avdmanager", "sdkmanager"):
            try:
                out[tool] = getattr(self, tool)
            except FileNotFoundError:
                out[tool] = None
        return out


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    log.debug("$ %s", " ".join(cmd))
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


class AvdManager:
    def __init__(self, config: Config):
        self.config = config
        self.sdk = SdkTools(config.android_sdk)

    # ---------- Anlegen ----------

    def list_avds(self) -> list[str]:
        res = _run([self.sdk.emulator, "-list-avds"])
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]

    def install_image(self, dev: DeviceConfig) -> None:
        """Lädt das System-Image per sdkmanager (Download, ~1,5 GB)."""
        image = dev.avd["system_image"]
        log.info("Installiere %s …", image)
        subprocess.run(
            [self.sdk.sdkmanager, "--install", image, "platform-tools", "emulator"],
            check=True, input="y\n" * 5, text=True,
        )

    def create(self, dev: DeviceConfig, force: bool = False) -> None:
        avd = dev.avd
        if avd["name"] in self.list_avds() and not force:
            log.info("AVD '%s' existiert bereits — nichts zu tun.", avd["name"])
            return
        if self.sdk.check()["avdmanager"] is None:
            log.info("avdmanager fehlt — lege AVD direkt als config.ini an.")
            self._create_without_avdmanager(dev)
        else:
            cmd = [
                self.sdk.avdmanager, "create", "avd",
                "--name", avd["name"],
                "--package", avd["system_image"],
                "--device", avd.get("device_profile", "pixel_7"),
            ]
            if force:
                cmd.append("--force")
            # avdmanager fragt nach "custom hardware profile" → "no"
            subprocess.run(cmd, check=True, input="no\n", text=True)
        self._tune_config_ini(dev)
        log.info("AVD '%s' angelegt.", avd["name"])

    def _create_without_avdmanager(self, dev: DeviceConfig) -> None:
        """Minimal-AVD (Pixel-7-Maße) aus Dateien, wenn die Command-line Tools fehlen."""
        name = dev.avd["name"]
        image_rel = dev.avd["system_image"].replace(";", "/") + "/"
        image_dir = self.config.android_sdk / image_rel
        if not (image_dir / "system.img").exists():
            raise FileNotFoundError(f"System-Image nicht installiert: {image_dir}")
        _, api, tag, abi = dev.avd["system_image"].split(";")

        avd_root = Path.home() / ".android" / "avd"
        avd_dir = avd_root / f"{name}.avd"
        avd_dir.mkdir(parents=True, exist_ok=True)
        (avd_root / f"{name}.ini").write_text(
            f"avd.ini.encoding=UTF-8\npath={avd_dir}\npath.rel=avd/{name}.avd\n"
            f"target={api}\n"
        )
        config = {
            "AvdId": name,
            "avd.ini.displayname": name,
            "abi.type": abi,
            "hw.cpu.arch": "arm64",
            "hw.cpu.ncore": "4",
            "image.sysdir.1": image_rel,
            "tag.id": tag,
            "tag.display": "Google Play" if "playstore" in tag else tag,
            "PlayStore.enabled": "true" if "playstore" in tag else "false",
            "hw.device.name": dev.avd.get("device_profile", "pixel_7"),
            "hw.device.manufacturer": "Google",
            "hw.lcd.width": "1080",
            "hw.lcd.height": "2400",
            "hw.lcd.density": "420",
            "hw.mainKeys": "no",
            "hw.accelerometer": "yes",
            "hw.gps": "yes",
            "hw.camera.back": "none",
            "hw.camera.front": "none",
            "hw.sdCard": "yes",
            "sdcard.size": "512M",
            "showDeviceFrame": "no",
        }
        (avd_dir / "config.ini").write_text(
            "\n".join(f"{k}={v}" for k, v in config.items()) + "\n"
        )

    def _tune_config_ini(self, dev: DeviceConfig) -> None:
        ini = Path.home() / ".android" / "avd" / f"{dev.avd['name']}.avd" / "config.ini"
        if not ini.exists():
            log.warning("config.ini nicht gefunden: %s", ini)
            return
        overrides = {
            "hw.ramSize": str(dev.avd.get("ram_mb", 3072)),
            "disk.dataPartition.size": dev.avd.get("data_partition", "8G"),
            "hw.keyboard": "yes",
            "hw.gpu.enabled": "yes",
            "hw.gpu.mode": "host",
            "fastboot.forceColdBoot": "no",
        }
        lines = ini.read_text().splitlines()
        keys_seen = set()
        for i, line in enumerate(lines):
            key = line.split("=", 1)[0].strip()
            if key in overrides:
                lines[i] = f"{key}={overrides[key]}"
                keys_seen.add(key)
        lines += [f"{k}={v}" for k, v in overrides.items() if k not in keys_seen]
        ini.write_text("\n".join(lines) + "\n")

    # ---------- Start/Stopp ----------

    def is_running(self, dev: DeviceConfig) -> bool:
        res = _run([self.sdk.adb, "devices"])
        return any(
            line.startswith(dev.serial) and line.endswith("device")
            for line in res.stdout.splitlines()
        )

    def start(self, dev: DeviceConfig, wait: bool = True, timeout: int = 240) -> None:
        if self.is_running(dev):
            log.info("%s läuft bereits.", dev.serial)
            return
        cmd = [
            self.sdk.emulator, "-avd", dev.avd["name"],
            "-port", str(dev.console_port),
            *dev.avd.get("extra_args", []),
        ]
        if dev.avd.get("headless"):
            cmd.append("-no-window")
        log_file = self.config.log_dir / f"emulator_{dev.name}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log.info("Starte Emulator: %s", " ".join(cmd))
        with log_file.open("ab") as f:
            subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        if wait:
            self.wait_for_boot(dev, timeout)

    def wait_for_boot(self, dev: DeviceConfig, timeout: int = 240) -> None:
        deadline = time.time() + timeout
        _run([self.sdk.adb, "-s", dev.serial, "wait-for-device"], timeout=timeout)
        while time.time() < deadline:
            res = subprocess.run(
                [self.sdk.adb, "-s", dev.serial, "shell", "getprop", "sys.boot_completed"],
                text=True, capture_output=True,
            )
            if res.stdout.strip() == "1":
                log.info("%s ist gebootet.", dev.serial)
                return
            time.sleep(3)
        raise TimeoutError(f"{dev.serial} nicht innerhalb von {timeout}s gebootet.")

    def stop(self, dev: DeviceConfig) -> None:
        if not self.is_running(dev):
            log.info("%s läuft nicht.", dev.serial)
            return
        _run([self.sdk.adb, "-s", dev.serial, "emu", "kill"])
        log.info("%s gestoppt (Zustand bleibt erhalten).", dev.serial)
