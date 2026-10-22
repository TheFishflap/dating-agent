"""Platzhalter: Gedächtnis pro Match.

Geplant: statt den Rohverlauf jedes Chats zu speichern und ans LLM zu schicken,
wird pro Match eine komprimierte Zusammenfassung gepflegt (Fakten über die Person,
besprochene Themen, offene Fragen, Ton, Stand der Date-Planung). Nach jeder neuen
Nachricht wird die Zusammenfassung inkrementell aktualisiert; nur sie plus die
letzten N Nachrichten gehen in den Prompt. Speicherung lokal (data/, gitignored),
eine Datei/Zeile pro Match, mit Löschfunktion bei Unmatch.
"""
