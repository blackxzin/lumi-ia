"""Generate original provisional 16x16 pixel sprites without external image libraries."""

import struct
import zlib
from pathlib import Path

# Lume: a mint seed with two asymmetric antennae, dark outline and amber feet.
base = [
    "................",
    ".....dd.........",
    ".....dm...dd....",
    ".....dm...md....",
    "....dddddddd....",
    "...dmmmmmmmmd...",
    "..dmmmmmmmmmmd..",
    "..dmmddmmddmmd..",
    "..dmmddmmddmmd..",
    "..dmmmmmmmmmmd..",
    "..dmammmmmammd..",
    "...dmmmddmmmd...",
    "....dmmmmmd.....",
    ".....ddddd......",
    "....da...ad.....",
    "................",
]
palette = {
    ".": (0, 0, 0, 0),
    "d": (29, 44, 54, 255),
    "m": (114, 224, 179, 255),
    "a": (255, 199, 112, 255),
    "w": (245, 248, 255, 255),
    "r": (245, 120, 130, 255),
}
width, height = 16 * 9, 32
pixels = [[palette["."] for _ in range(width)] for _ in range(height)]
for state in range(9):
    for frame in range(2):
        art = [list(row) for row in base]
        if state == 2:
            for x in (5, 6, 9, 10):
                art[7][x] = "m"
        if state == 4 and frame:
            art[11][7] = art[12][7] = "d"
        if state == 5:
            art[7][5] = art[7][10] = "m"
        if state == 6:
            art[7][9] = "m"
        if state == 7:
            art = [["r" if cell == "m" else cell for cell in row] for row in art]
        if state == 3:
            art[2][12] = "a" if frame else "."
        if state == 8:
            art[6][0] = art[7][0] = "a"
        if state == 1 and frame:
            art[14][4] = art[14][10] = "."
            art[14][3] = art[14][11] = "a"
        for y in range(16):
            for x in range(16):
                pixels[y + frame * 16][state * 16 + x] = palette[art[y][x]]


def chunk(name, data):
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))


raw = b"".join(b"\0" + bytes(component for pixel in row for component in pixel) for row in pixels)
png = (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(raw))
    + chunk(b"IEND", b"")
)
Path(__file__).resolve().parents[1].joinpath("apps/desktop/assets/lume.png").write_bytes(png)
