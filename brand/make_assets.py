"""Derive every web asset from the one source logo.

    python brand/make_assets.py

Source of truth: brand/lifey-logo.png (white background, symbol above wordmark).
Outputs are committed so the Docker build needs no image tooling.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "brand" / "lifey-logo.png"
PUBLIC = ROOT / "web" / "public"
APP = ROOT / "web" / "app"
WHITE = (255, 255, 255)
SYMBOL_BOTTOM = 840            # wordmark starts below this row in the 1254px source


def ink_bbox(im: Image.Image, top: int = 0, bottom: int | None = None) -> tuple[int, int, int, int]:
    """Bounding box of everything that is not (near) white, within the given rows."""
    bottom = bottom or im.height
    region = im.crop((0, top, im.width, bottom)).convert("L").point(lambda v: 255 if v < 245 else 0)
    x0, y0, x1, y1 = region.getbbox()
    return x0, y0 + top, x1, y1 + top


def pad(im: Image.Image, margin: float) -> Image.Image:
    """Centre on a white square, leaving `margin` (fraction of the side) on each edge."""
    side = round(max(im.size) / (1 - 2 * margin))
    out = Image.new("RGB", (side, side), WHITE)
    out.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    return out


def save_png(im: Image.Image, path: Path, size: int | None = None, width: int | None = None) -> None:
    """PNG, or lossy WebP when the path ends in .webp (in-page images; icons stay PNG)."""
    if size:
        im = im.resize((size, size), Image.LANCZOS)
    elif width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".webp":
        im.save(path, quality=92, method=6)
    else:
        im.save(path, optimize=True)
    print(f"{path.relative_to(ROOT)}  {im.width}x{im.height}  {path.stat().st_size // 1024} KB")


def main() -> None:
    src = Image.open(SRC).convert("RGB")

    # Full logo: symbol and wordmark, tight crop with a little air.
    x0, y0, x1, y1 = ink_bbox(src)
    full = src.crop((x0, y0, x1, y1))
    framed = Image.new("RGB", (full.width + 120, full.height + 120), WHITE)
    framed.paste(full, (60, 60))
    save_png(framed, PUBLIC / "brand" / "lifey-logo.webp", width=520)

    # Mark: the symbol alone, square.
    sx0, sy0, sx1, sy1 = ink_bbox(src, 0, SYMBOL_BOTTOM)
    mark = src.crop((sx0, sy0, sx1, sy1))
    mark_sq = pad(mark, 0.06)
    save_png(mark_sq, PUBLIC / "brand" / "lifey-mark.webp", size=160)

    # App and install icons: the mark with room around it.
    icon = pad(mark, 0.12)
    save_png(icon, PUBLIC / "icons" / "icon-192.png", size=192)
    save_png(icon, PUBLIC / "icons" / "icon-512.png", size=512)
    save_png(pad(mark, 0.22), PUBLIC / "icons" / "icon-512-maskable.png", size=512)  # inside the safe zone
    save_png(icon, APP / "icon.png", size=512)
    save_png(icon, APP / "apple-icon.png", size=180)

    # Next decodes .ico frames strictly: they must be RGBA.
    ico = icon.resize((64, 64), Image.LANCZOS).convert("RGBA")
    ico.save(APP / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"{(APP / 'favicon.ico').relative_to(ROOT)}  {(APP / 'favicon.ico').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
