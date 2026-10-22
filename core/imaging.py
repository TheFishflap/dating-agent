"""Bildvergleich für Screenshots (Änderungserkennung, Scroll-Ende)."""
from __future__ import annotations

import io

from PIL import Image


def image_fingerprint(png: bytes, size: int = 16) -> int:
    """Average-Hash: robust gegen Statusleisten-Uhr/kleine Änderungen."""
    img = Image.open(io.BytesIO(png)).convert("L").resize((size, size))
    px = list(img.getdata())
    avg = sum(px) / len(px)
    return sum(1 << i for i, p in enumerate(px) if p > avg)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def mean_pixel_diff(a: bytes, b: bytes, size: int = 96) -> float:
    """Mittlere Grauwert-Differenz (0–255) zweier verkleinerter Screenshots."""
    ia = Image.open(io.BytesIO(a)).convert("L").resize((size, size))
    ib = Image.open(io.BytesIO(b)).convert("L").resize((size, size))
    pa, pb = ia.getdata(), ib.getdata()
    return sum(abs(x - y) for x, y in zip(pa, pb)) / (size * size)


def same_screen(a: bytes, b: bytes, max_diff: float = 1.5) -> bool:
    """Pixelgenauer als der Fingerprint: erkennt auch kleine Scroll-Bewegungen."""
    return mean_pixel_diff(a, b) <= max_diff
