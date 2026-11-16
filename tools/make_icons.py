"""Generate pwa/icons/*.png programmatically (emerald square, white plus).

Run:  .venv/bin/python -m tools.make_icons

Pure-Python PNG writer (zlib) — no external image dependencies, no text
rendering needed for the maskable-safe icon.
"""

import struct
import zlib
from pathlib import Path

SIZES = (192, 512)
EMERALD = (5, 150, 105)      # #059669
DARK = (2, 6, 23)            # #020617 (safe-zone padding for maskable)
WHITE = (255, 255, 255)


def write_png(path, w, h, pixel_fn):
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter: none
        for x in range(w):
            r, g, b = pixel_fn(x, y)
            raw.extend((r, g, b))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit RGB
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
    Path(path).write_bytes(png)


def pixel_factory(size):
    # icon: emerald rounded square on dark background, centered white plus
    pad = round(size * 0.10)          # safe zone for maskable icons
    radius = round(size * 0.22)
    bar_w = round(size * 0.115)       # plus bar thickness
    bar_l = round(size * 0.52)        # plus arm length
    def px(x, y):
        # dark background outside the rounded square
        rx = min(x - pad, size - pad - 1 - x)  # distance from vertical edges
        ry = min(y - pad, size - pad - 1 - y)
        inside = rx >= 0 and ry >= 0
        if inside and (rx >= radius or ry >= radius):
            pass  # solid area
        elif inside and rx * rx + ry * ry > radius * radius:
            return DARK  # outside rounded corner
        if not inside:
            return DARK
        # centered plus
        cx, cy = size / 2, size / 2
        in_h = abs(y - cy) <= bar_w / 2 and abs(x - cx) <= bar_l / 2
        in_v = abs(x - cx) <= bar_w / 2 and abs(y - cy) <= bar_l / 2
        if in_h or in_v:
            return WHITE
        return EMERALD
    return px


def main():
    icons_dir = Path(__file__).resolve().parent.parent / "pwa" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    for s in SIZES:
        out = icons_dir / f"icon-{s}.png"
        write_png(out, s, s, pixel_factory(s))
        print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
