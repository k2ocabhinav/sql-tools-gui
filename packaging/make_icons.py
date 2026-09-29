"""Regenerate the raster icons from assets/icon.svg.

Run with the project environment (needs PySide6; the .icns step needs macOS `iconutil`):

    uv run python packaging/make_icons.py

Outputs, all in assets/:
    icon.png   512 px, body cropped tight - window icon and sidebar mark at runtime
    icon.ico   16-256 px - Windows executable, installer and taskbar
    icon.icns  macOS bundle icon, keeps the 10% margin macOS expects (macOS only)
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parents[1] / "assets"
BODY = QRectF(100, 100, 824, 824)  # the squircle inside the 1024 canvas
FULL = QRectF(0, 0, 1024, 1024)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICNS_SIZES = (16, 32, 128, 256, 512)


def render(renderer: QSvgRenderer, size: int, source: QRectF) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.setViewBox(source)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def write_ico(path: Path, images: list[tuple[int, bytes]]) -> None:
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, payload = b"", b""
    for size, data in images:
        entries += struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset + len(payload)
        )
        payload += data
    path.write_bytes(header + entries + payload)


def write_icns(renderer: QSvgRenderer, path: Path) -> bool:
    if sys.platform != "darwin" or not shutil.which("iconutil"):
        print("Skipping icon.icns (needs macOS iconutil)")
        return False
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for size in ICNS_SIZES:
            render(renderer, size, FULL).save(str(iconset / f"icon_{size}x{size}.png"))
            render(renderer, size * 2, FULL).save(str(iconset / f"icon_{size}x{size}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(path)], check=True)
    return True


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    renderer = QSvgRenderer(str(ASSETS / "icon.svg"))
    if not renderer.isValid():
        print("assets/icon.svg could not be parsed", file=sys.stderr)
        return 1
    render(renderer, 512, BODY).save(str(ASSETS / "icon.png"))
    write_ico(
        ASSETS / "icon.ico",
        [(size, png_bytes(render(renderer, size, BODY))) for size in ICO_SIZES],
    )
    write_icns(renderer, ASSETS / "icon.icns")
    del app
    print("Icons written to", ASSETS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
