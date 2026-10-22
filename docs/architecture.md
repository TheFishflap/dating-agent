# Architektur

## Schichten

```
agent/loop.py  ──►  agent/decision.py (Claude API, strukturierte Antwort)
     │                     ▲
     │ Screenshot          │ Präferenzen aus config
     ▼
platforms/<name>/app.py  (PlatformApp: screenshot, detect_screen, swipe_left/right)
     │ ADB (Screenshots, Shell)      │ Appium/UiAutomator2 (UI-Baum, Gesten)
     ▼                               ▼
emulator/  (AVD-Lebenszyklus)  ──►  Android-Emulator  emulator-<port>
core/      Config · Logging · DelayManager (Pausen, Sitzungen, Tageslimits)
```

## Instanzen & Parallelbetrieb

- Jede Instanz = ein Eintrag in `devices:` mit eigenem AVD, eigenem Konsolen-Port
  (ADB-Serial `emulator-<port>`) und eigenem UiAutomator2-`system_port`.
  `core.config` prüft, dass Ports eindeutig sind.
- Ein Prozess pro Instanz: `python -m agent --device <name>`. Logs, Entscheidungen und
  Limit-Zähler werden pro Instanz getrennt geschrieben.
- Neue Plattform: `platforms/<name>/` mit Unterklasse von `platforms.base.PlatformApp`
  und Eintrag in `platforms.registry`.

## Entscheidungsformat (Meilenstein 1)

```json
{
  "screen_type": "profile",
  "action": "swipe_right",
  "reason": "Teilt Wanderinteresse, Alter passt, Bio wirkt ernsthaft.",
  "confidence": 0.72,
  "profile": {"name": "…", "age": 31, "distance_km": 4, "job": "…", "interests": ["…"], …}
}
```

`action` ∈ `swipe_right | swipe_left | skip`. `skip` = Bildschirm ist kein Profil
oder es fehlen Informationen.

## Roadmap (Platzhalter-Module)

| Modul | Zweck |
|---|---|
| `analysis/attractiveness_scoring` | Bildbasierter Score (SCUT-FBP5500-Modell), lokal |
| `analysis/profile_analysis` | Text/Prompts → Kompatibilitätsmerkmale |
| `analysis/scam_detection` | Fake-/Scam-Profile und -Nachrichten erkennen |
| `chat/match_memory` | Komprimierte Zusammenfassung pro Match statt Rohverlauf |
| `chat/match_summary` | Kurzbriefing zu einem Match für mich |
| `chat/escalation` | KI-Frage → nicht abstreiten, Chat pausieren, mich benachrichtigen |
| `integrations/calendar` | Google Calendar, erst bei vereinbartem Date |
