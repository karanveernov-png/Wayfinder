"""
Generates Waymark's app/favicon/PWA icon set from the exact brand mark
already used in-app (AppLayout.jsx's sidebar logo: a navy #203C5A rounded
square with lucide's "Navigation" glyph in white) so the browser tab,
home-screen icon, and splash screens match the app's actual identity
instead of the unrelated placeholder purple icon that shipped before.

Run: python3 generate_icons.py  (requires rsvg-convert on PATH)
"""
import subprocess
from pathlib import Path

OUT = Path(__file__).parent
PUBLIC = OUT.parent / "public"

BRAND_NAVY = "#203C5A"
WHITE = "#ffffff"

# lucide-react's "navigation" icon: a single polygon in a 24x24 box,
# stroke-based, stroke-width 2. Copied verbatim from
# node_modules/lucide-react/dist/esm/icons/navigation.mjs so the mark is
# pixel-faithful to the in-app sidebar logo, not a redrawn approximation.
NAV_POLYGON_POINTS = "3 11 22 2 13 21 11 13 3 11"


def glyph(scale: float, stroke_width: float = 2) -> str:
    """The Navigation glyph, scaled and centered on a 512x512 canvas."""
    return (
        f'<g transform="translate(256 256) scale({scale}) translate(-12 -12)">'
        f'<polygon points="{NAV_POLYGON_POINTS}" fill="none" stroke="{WHITE}" '
        f'stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round"/>'
        f"</g>"
    )


def icon_svg(*, rounded: bool, scale: float) -> str:
    """rounded=True: the 'any' purpose icon (browsers/OS apply their own
    mask on top either way, so a gently rounded square previews best).
    rounded=False: 'maskable' purpose - a full-bleed square background,
    since the OS applies its own (often circular) mask; the glyph is kept
    small enough to survive that per the maskable-icon safe-zone spec."""
    radius = 108 if rounded else 0
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="{radius}" fill="{BRAND_NAVY}"/>
  {glyph(scale)}
</svg>"""


def favicon_svg() -> str:
    """Smaller canvas tuned for crisp rendering at browser-tab sizes."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
  <rect width="48" height="48" rx="10" fill="{BRAND_NAVY}"/>
  <g transform="translate(24 24) scale(1.1) translate(-12 -12)">
    <polygon points="{NAV_POLYGON_POINTS}" fill="none" stroke="{WHITE}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
</svg>"""


def write(path: Path, content: str):
    path.write_text(content)
    print(f"wrote {path}")


def rasterize(svg_path: Path, png_path: Path, size: int):
    subprocess.run(
        ["rsvg-convert", "-w", str(size), "-h", str(size), str(svg_path), "-o", str(png_path)],
        check=True,
    )
    print(f"rasterized {png_path} ({size}x{size})")


def main():
    PUBLIC.mkdir(exist_ok=True)

    # 1. Favicon (SVG, scalable - modern browsers use this directly).
    write(PUBLIC / "favicon.svg", favicon_svg())

    # 2. "any" purpose icon source (rounded square, larger glyph) -> 192/512 PNG + apple-touch-icon.
    any_svg = OUT / "_icon-any.svg"
    write(any_svg, icon_svg(rounded=True, scale=13.5))
    rasterize(any_svg, PUBLIC / "icon-192.png", 192)
    rasterize(any_svg, PUBLIC / "icon-512.png", 512)
    rasterize(any_svg, PUBLIC / "apple-touch-icon.png", 180)
    rasterize(any_svg, PUBLIC / "favicon-32.png", 32)
    rasterize(any_svg, PUBLIC / "favicon-16.png", 16)

    # 3. "maskable" purpose icon source (full-bleed, smaller glyph so it
    #    survives an OS applying a circular/squircle mask on top).
    maskable_svg = OUT / "_icon-maskable.svg"
    write(maskable_svg, icon_svg(rounded=False, scale=9.5))
    rasterize(maskable_svg, PUBLIC / "icon-maskable-192.png", 192)
    rasterize(maskable_svg, PUBLIC / "icon-maskable-512.png", 512)


if __name__ == "__main__":
    main()
