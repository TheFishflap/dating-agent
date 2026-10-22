# dating-agent

LLM-gestützter Assistent für Dating-Apps, gesteuert über einen Android-Emulator.
Aktuell: nur Bumble. Der Agent scrollt jedes Profil durch, lässt Claude Merkmale
erkennen (Attraktivitäts-Score, Körpertyp, Rauchen, Dealbreaker), entscheidet nach festen
Regeln (`agent/rules.py`, Config `agent.rules`) und **loggt im Trockenlauf nur**. Live-Swipes
nur mit doppelter Freigabe (siehe [Sicherheitsriegel](#sicherheitsriegel)).

> **Hinweis:** Die Bumble-Nutzungsbedingungen verbieten automatisierten Zugriff. Wer
> später Aktionen live ausführt, riskiert eine Sperre des Accounts. Screenshots
> enthalten Fotos und Daten anderer Personen. Sie bleiben lokal (`data/`, gitignored),
> werden nach `screenshot_retention_days` gelöscht und gehen nur zur Auswertung an Claude
> (über die Claude-Code-CLI bzw. die Anthropic API).

## Ordnerstruktur

```
dating-agent/
├── core/              Config (.env + YAML), Logging, Delay-/Limit-Modul
├── emulator/          AVD anlegen/starten/stoppen per Config  (python -m emulator ...)
├── platforms/
│   ├── base.py        abstrakte App-Schnittstelle (ein Layer pro Plattform)
│   └── bumble/        Screenshots, Scrollen, Swipes und Dialoge per ADB (Appium optional)
├── agent/             Schleife, Claude-Bewertung (CLI oder API), Regeln, Kalibrierung
├── analysis/          Platzhalter: attractiveness_scoring, profile_analysis, scam_detection
├── chat/              Platzhalter: match_memory, match_summary, escalation
├── integrations/      Platzhalter: calendar (Google Calendar)
├── config/            config.yaml (ohne Secrets), optional config.local.yaml
├── docs/              Architektur, Emulator-Setup
├── data/  logs/       Laufzeitdaten (gitignored)
└── tests/
```

## Setup-Reihenfolge

1. **Android Studio + SDK** installieren (siehe [Manuelle Schritte](#manuelle-schritte-emulator--bumble)).
2. **Python-Umgebung**
   ```bash
   cd dating-agent
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.lock.txt
   ```
3. **Claude anmelden** (Standard `backend: claude_cli`, nutzt das Claude-Abo):
   ```bash
   claude auth login
   ```
   Alternativ `backend: api` und `cp .env.example .env` mit `ANTHROPIC_API_KEY`.
   Appium ist optional (siehe [Abhängigkeiten](#abhängigkeiten)).
4. **AVD anlegen und starten**
   ```bash
   python -m emulator check              # prüft SDK-Tools, ändert nichts
   python -m emulator create --device bumble-1
   python -m emulator start --device bumble-1 --wait
   ```
5. **Im Emulator manuell:** Play-Store-Login, Bumble installieren, in Bumble einloggen.
6. **Trockenlauf**
   ```bash
   python -m agent --device bumble-1 --no-appium --once     # aktuelles Profil einmal bewerten
   python -m agent --device bumble-1 --no-appium            # Schleife
   ```
   Der Agent scrollt jedes neue Profil durch und meldet sich mit einem Ton; du bewertest
   selbst. Ergebnisse: `logs/decisions/*.jsonl`.
7. **Kalibrieren** (eigene Bewertung r/l vs. Agent):
   ```bash
   python -m agent --device bumble-1 --no-appium --feedback --max-steps 20
   python -m agent.calibration
   ```
8. **Live** (echte Swipes): `dry_run: false` in `config/config.local.yaml` **und**
   ```bash
   DATING_AGENT_ALLOW_LIVE=yes python -m agent --device bumble-1 --no-appium --max-steps 10
   ```

## Manuelle Schritte: Emulator & Bumble

1. **Android Studio** installieren (developer.android.com/studio, Apple-Silicon-Build).
   Beim ersten Start den Setup-Wizard durchlaufen. Das SDK landet unter
   `~/Library/Android/sdk`.
2. **SDK-Komponenten** in *Settings → Languages & Frameworks → Android SDK*:
   Der Standard-Setup-Wizard installiert Emulator, Platform-Tools und das
   *Google Play ARM 64 v8a System Image* (aktuell API 37) — das reicht.
   Die *Command-line Tools* sind optional: fehlt `avdmanager`, legt
   `python -m emulator create` das AVD direkt als config.ini an.
   Anderes Image? `devices[].avd.system_image` in der Config anpassen.
3. **PATH setzen** (z. B. in `~/.zshrc`):
   ```bash
   export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
   export PATH="$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"
   ```
4. **AVD** per Skript anlegen (oben, Schritt 4) oder im Device Manager von Android Studio.
   Der Name muss dann zu `devices[].avd.name` in der Config passen.
5. **Play-Store-Login:** Emulator starten, Play Store öffnen, mit einem Google-Konto
   anmelden. Ein separates Konto ist sinnvoll.
6. **Bumble installieren** über den Play Store im Emulator.
7. **Bei Bumble einloggen**, und zwar manuell (Telefonnummer/SMS bzw. Google). Der Agent
   fasst keine Zugangsdaten an. Danach Standortfreigabe und Benachrichtigungen nach
   Wunsch setzen.
8. Emulator mit `python -m emulator stop` beenden. Der Login bleibt im AVD erhalten.
   Kein Wipe, kein Cold-Boot mit `-wipe-data`.

Für die Speicherplanung (16 GB RAM): ein AVD mit 3 GB RAM ist ausreichend. Bei mehreren
parallelen Instanzen `ram_mb` reduzieren und `headless: true` setzen.

## Abhängigkeiten

| Komponente | Version (getestet) | Installation |
|---|---|---|
| Python | 3.12 | python.org / Homebrew |
| Python-Pakete | siehe `requirements.txt` (Mindestversionen) bzw. `requirements.lock.txt` (exakt) | `pip install -r requirements.lock.txt` |
| Android Studio + SDK | Emulator, Platform-Tools, Image `android-37.0;google_apis_playstore;arm64-v8a` | Setup-Wizard (Command-line Tools optional) |
| Node.js | für Appium | Homebrew |
| Appium + Treiber | appium 3.8.0, uiautomator2 8.7.0 (optional; Standardbetrieb läuft per ADB mit `--no-appium`) | `npm install -g appium@3.8.0 && appium driver install uiautomator2@8.7.0` |
| Claude-Code-CLI | 2.1.x, angemeldet mit Claude-Abo (`backend: claude_cli`) | wird mit der Claude-Desktop-App geliefert oder separat installiert; `claude auth login` |

## Sicherheitsriegel

- `dry_run: true` ist Standard. Selbst wenn `dry_run: false` in der YAML steht, bleibt
  der Trockenlauf aktiv, solange `DATING_AGENT_ALLOW_LIVE=yes` nicht gesetzt ist.
- Live: Nach jedem Swipe wird geprüft, ob er gewirkt hat. Bekannte Bestätigungsdialoge
  („Interested?“) werden bestätigt, jeder andere Dialog führt zum Stopp. Unklare
  Bildschirme (Match, Werbung) → Agent wartet und spielt einen Ton.
- Tageslimits (`delays.daily_limits`) stoppen den Agenten; Trockenlauf zählt getrennt
  (`_dryrun`-Statusdatei).

## Weitere Doku

- [docs/architecture.md](docs/architecture.md): Schichten, Parallelbetrieb, Roadmap
