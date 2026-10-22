"""Platzhalter: Fake-/Scam-Erkennung.

Geplant: Heuristiken + LLM-Prüfung für Profile und Nachrichten, z. B.
- Profil: Stockfoto-/Model-Optik bei leerer Bio, Links/Handles in der Bio,
  widersprüchliche Angaben, sehr neue Profile mit wenigen Fotos.
- Chat: schneller Wechsel auf WhatsApp/Telegram, Geld/Krypto/Investment,
  Notfallgeschichten, Bitte um Codes/Verifizierungen.
Ergebnis: Risiko-Score + Gründe. Bei hohem Risiko: kein Like bzw. Chat pausieren
und mich benachrichtigen (siehe chat.escalation).
"""
