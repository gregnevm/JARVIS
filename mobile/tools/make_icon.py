#!/usr/bin/env python3
"""Генератор launcher-іконки JARVIS (stdlib-only, без PIL).

Малює просту, але впізнавану іконку: темно-синій фон + ціановий діод-кільце з
крапкою в центрі (натяк на «око» асистента). Пише PNG у res/drawable/ic_launcher.png.

Запуск: python mobile/tools/make_icon.py
"""
from __future__ import annotations

import math
import struct
import sys
import zlib
from pathlib import Path

SIZE = 192
BG = (11, 18, 32)        # темно-синій
RING = (34, 211, 238)    # cyan-400
DOT = (125, 240, 250)    # світліший cyan


def _blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))  # type: ignore[return-value]


def _pixel(x: int, y: int) -> tuple[int, int, int, int]:
    cx = cy = SIZE / 2.0
    dx, dy = x - cx, y - cy
    dist = math.hypot(dx, dy)
    # Скруглений квадрат-фон.
    corner = SIZE * 0.5
    if abs(dx) > corner - 1 and abs(dy) > corner - 1:
        if math.hypot(abs(dx) - (corner - 1), abs(dy) - (corner - 1)) > 0:
            return (0, 0, 0, 0)
    r_outer = SIZE * 0.34
    r_inner = SIZE * 0.24
    r_dot = SIZE * 0.10
    if dist <= r_dot:
        return (*DOT, 255)
    if r_inner <= dist <= r_outer:
        # м'які краї кільця
        edge = min(dist - r_inner, r_outer - dist)
        t = max(0.0, min(1.0, edge / 4.0))
        return (*_blend(BG, RING, t), 255)
    return (*BG, 255)


def build_png() -> bytes:
    raw = bytearray()
    for y in range(SIZE):
        raw.append(0)  # filter type 0
        for x in range(SIZE):
            raw.extend(_pixel(x, y))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)  # 8-bit RGBA
    idat = zlib.compress(bytes(raw), 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def main() -> int:
    out = Path(__file__).resolve().parents[1] / "app" / "src" / "main" / "res" / "drawable" / "ic_launcher.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_png())
    print(f"icon written: {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
