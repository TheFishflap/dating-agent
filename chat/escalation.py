"""Platzhalter: Eskalation an mich.

Geplant: jede eingehende Nachricht wird vor dem Antworten geprüft.

Trigger "Fragt das Gegenüber, ob es mit einer KI/einem Bot schreibt?":
  1. Nicht abstreiten. Es wird keine Antwort generiert, die das verneint
     oder ausweicht.
  2. Den Chat für dieses Match sofort pausieren (keine automatischen Antworten mehr).
  3. Mich benachrichtigen (Kanal noch offen, z. B. Push/Telegram/E-Mail) mit
     Match-Briefing (chat.match_summary) und der Originalnachricht.
  4. Erst nach meiner manuellen Freigabe geht es weiter, ggf. antworte ich selbst.

Weitere geplante Trigger: Scam-Verdacht (analysis.scam_detection), Date-Vorschlag
(→ integrations.calendar), Hinweise auf Notlage/Unwohlsein, explizite Inhalte,
Wunsch nach Telefonnummer/Treffen.
"""
