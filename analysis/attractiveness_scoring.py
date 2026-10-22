"""Platzhalter: bildbasierter Attraktivitäts-Score.

Geplant: lokales Regressionsmodell, trainiert auf SCUT-FBP5500 (5500 Gesichter,
Scores 1–5). Pipeline: Gesichtserkennung/-ausrichtung auf Profilfotos → Embedding
(z. B. ResNet/ViT-Backbone) → Score + Unsicherheit. Läuft lokal, damit keine Fotos
zusätzlich an Dritte gehen.

Zu beachten:
- Der Datensatz ist demografisch begrenzt; der Score ist ein schwaches Signal
  und darf nur eines von mehreren Kriterien sein, nicht die alleinige Entscheidung.
- Lizenz des Datensatzes prüfen (nur nicht-kommerzielle Forschung).
- Kalibrierung gegen eigene Likes/Pässe aus dem Trockenlauf-Log.
"""
