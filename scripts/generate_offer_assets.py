"""Render the animated banner at the top of recruitment offer emails.

The banner shows the offer as a card-stock credential lying on warm paper: the
organisation's mark, ruled lines, a perforated stub with a code strip, and the
organisation's seal pressed onto the card in cinnabar. It carries no words apart
from the organisation's name, so it works for every offer and language, and it
uses the same paper, ink and hairline colours as the offer page.

    python scripts/generate_offer_assets.py

writes assets/recruitment/offer-hero.gif (960 x 288, shown at 600 x 180). The
first frame is the complete, sealed credential, because Outlook for Windows shows
only that frame. The loop then lifts the seal for a moment and presses it again.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "recruitment" / "offer-hero.gif"
# Bundled with the front end; the wordmark is left out if the file is not there.
WORDMARK_FONT = ROOT / "frontend" / "node_modules" / "@fontsource" / "ibm-plex-sans" / "files" / "ibm-plex-sans-latin-600-normal.woff"
ORGANISATION = "CausalGraph AI"

WIDTH, HEIGHT = 960, 288  # shown at 600 x 180 in the email
SCALE = 2  # drawn at twice the size and downsampled for smooth edges
COLOURS = 96

PAPER = (245, 243, 239)
CARD = (255, 255, 255)
LINE = (231, 228, 221)
LINE_STRONG = (213, 209, 200)
INK = (26, 25, 21)
ACCENT = (181, 67, 44)

# Geometry in final pixels: the card, its stub and the seal.
CARD_BOX = (128, 38, 832, 250)
CARD_RADIUS = 12
STUB_X = 660
SEAL_CENTRE = (572, 178)
SEAL_RADIUS = 50

# (seal opacity, seal scale, frame duration in ms). Frame 0 is the resting, sealed card.
TIMELINE = [
    (1.0, 1.0, 1900),
    (0.66, 1.02, 70),
    (0.33, 1.05, 70),
    (0.0, 1.08, 70),
    (0.0, 1.08, 520),
    (0.2, 1.26, 50),
    (0.5, 1.15, 50),
    (0.8, 1.07, 50),
    (0.95, 1.02, 50),
    (1.0, 0.99, 50),
]


def px(value: float) -> int:
    return int(round(value * SCALE))


def code_bars(seed: str, count: int = 24) -> list[tuple[int, int]]:
    """Bar and gap widths for the code strip, the same way the offer page derives its own."""

    def fnv1a(text: str) -> int:
        value = 0x811C9DC5
        for char in text:
            value = ((value ^ ord(char)) * 0x01000193) & 0xFFFFFFFF
        return value

    bars = []
    bits = 0
    for index in range(count):
        if index % 10 == 0:
            bits = fnv1a(f"{seed}/{index}")
        chunk = (bits >> ((index % 10) * 3)) & 7
        bars.append((1 + (chunk & 1) + ((chunk >> 1) & 1), 1 + ((chunk >> 2) & 1)))
    return bars


def ellipse_points(cx: float, cy: float, rx: float, ry: float, angle: float) -> list[tuple[float, float]]:
    rotation = math.radians(angle)
    points = []
    for step in range(73):
        theta = 2 * math.pi * step / 72
        x, y = rx * math.cos(theta), ry * math.sin(theta)
        points.append((cx + x * math.cos(rotation) - y * math.sin(rotation), cy + x * math.sin(rotation) + y * math.cos(rotation)))
    return points


def draw_mark(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, colour: tuple, width: float) -> None:
    """The organisation's mark: a core with three orbits, as in the front end's logo."""
    draw.ellipse([px(cx - size * 0.15), px(cy - size * 0.15), px(cx + size * 0.15), px(cy + size * 0.15)], fill=colour)
    for angle in (0, 60, 120):
        points = [(px(x), px(y)) for x, y in ellipse_points(cx, cy, size * 0.5, size * 0.2, angle)]
        draw.line(points, fill=colour, width=max(1, px(width)), joint="curve")


def load_wordmark_font() -> Optional[ImageFont.FreeTypeFont]:
    try:
        return ImageFont.truetype(str(WORDMARK_FONT), px(16))
    except OSError:
        return None


def base_layer() -> Image.Image:
    """Everything that never moves: paper, the card with its shadow, rules, stub and code strip."""
    size = (px(WIDTH), px(HEIGHT))
    image = Image.new("RGB", size, PAPER)
    x0, y0, x1, y1 = CARD_BOX

    # A soft, slightly warm shadow under the card.
    shadow = Image.new("L", size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle([px(x0), px(y0 + 10), px(x1), px(y1 + 10)], radius=px(CARD_RADIUS), fill=int(255 * 0.2))
    shadow = shadow.filter(ImageFilter.GaussianBlur(px(14)))
    image.paste((196, 190, 178), (0, 0), shadow)

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([px(x0), px(y0), px(x1), px(y1)], radius=px(CARD_RADIUS), fill=CARD, outline=LINE, width=px(1))

    # Head: mark and wordmark.
    draw.rounded_rectangle([px(160), px(66), px(186), px(92)], radius=px(7), fill=INK)
    draw_mark(draw, 173, 79, 17, CARD, 1.2)
    font = load_wordmark_font()
    if font is not None:
        draw.text((px(198), px(79)), ORGANISATION, font=font, fill=INK, anchor="lm")

    # Ruled lines where the letter would go; the seal sits across the lower ones.
    for y, length in ((132, 440), (158, 356), (184, 292)):
        draw.line([(px(160), px(y)), (px(160 + length), px(y))], fill=LINE, width=px(1.4))

    # Perforation between the card and its stub, with the cut-outs of a real ticket.
    y = y0
    while y < y1:
        draw.line([(px(STUB_X), px(y)), (px(STUB_X), px(min(y + 5, y1)))], fill=LINE_STRONG, width=px(1.2))
        y += 9
    for notch_y in (y0, y1):
        draw.ellipse([px(STUB_X - 9), px(notch_y - 9), px(STUB_X + 9), px(notch_y + 9)], fill=PAPER, outline=LINE, width=px(1))

    # Stub: the code strip and two field rules.
    x = 686
    for bar, gap in code_bars("offer-hero"):
        draw.rectangle([px(x), px(68), px(x + bar) - 1, px(92)], fill=INK)
        x += bar + gap
    for y, length in ((124, 110), (150, 78)):
        draw.line([(px(686), px(y)), (px(686 + length), px(y))], fill=LINE, width=px(1.4))
    return image


def seal_layer(rng: np.random.Generator) -> Image.Image:
    """The seal on its own, in cinnabar with slightly uneven ink, ready to be pressed onto the card."""
    radius = SEAL_RADIUS
    size = px(radius * 2 + 12)
    cx = cy = size / 2 / SCALE
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    colour = ACCENT + (255,)
    draw.ellipse([px(cx - radius), px(cy - radius), px(cx + radius), px(cy + radius)], outline=colour, width=px(3))
    inner = radius * 0.62
    draw.ellipse([px(cx - inner), px(cy - inner), px(cx + inner), px(cy + inner)], outline=colour, width=px(1))
    draw_mark(draw, cx, cy, radius * 0.62, colour, 2.0)

    # Ink never lands perfectly evenly: modulate the alpha with soft noise.
    grain = rng.random((size // 12 + 1, size // 12 + 1)).astype(np.float32)
    grain = np.asarray(Image.fromarray((grain * 255).astype(np.uint8)).resize((size, size), Image.BILINEAR), dtype=np.float32) / 255
    alpha = np.asarray(layer.getchannel("A"), dtype=np.float32) * (0.82 + 0.18 * grain)
    layer.putalpha(Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8)))
    return layer.rotate(8, resample=Image.BICUBIC, expand=False)


def render_frame(base: Image.Image, seal: Image.Image, opacity: float, scale: float) -> Image.Image:
    frame = base.copy()
    if opacity > 0:
        stamp = seal
        if abs(scale - 1.0) > 1e-3:
            side = max(1, int(round(seal.width * scale)))
            stamp = seal.resize((side, side), Image.LANCZOS)
        if opacity < 1:
            alpha = stamp.getchannel("A").point(lambda value: int(value * opacity))
            stamp = stamp.copy()
            stamp.putalpha(alpha)
        left = px(SEAL_CENTRE[0]) - stamp.width // 2
        top = px(SEAL_CENTRE[1]) - stamp.height // 2
        frame.paste(stamp, (left, top), stamp)
    return frame.resize((WIDTH, HEIGHT), Image.LANCZOS)


def encode(frames: Sequence[Image.Image], durations: Sequence[int]) -> None:
    # One shared palette keeps colours stable from frame to frame.
    sample = Image.new("RGB", (WIDTH, HEIGHT * 2))
    sample.paste(frames[0], (0, 0))
    sample.paste(frames[len(frames) // 2], (0, HEIGHT))
    palette = sample.quantize(colors=COLOURS, method=Image.Quantize.MEDIANCUT)
    quantised = [np.asarray(frame.quantize(palette=palette, dither=Image.Dither.NONE)) for frame in frames]

    # After the first frame, pixels that did not change are written as a transparent
    # index and the previous frame shows through, which keeps the file small.
    transparent = COLOURS
    colours = palette.getpalette()[: COLOURS * 3] + [0, 0, 0]
    encoded = []
    for index, pixels in enumerate(quantised):
        data = pixels.copy()
        if index:
            data[pixels == quantised[index - 1]] = transparent
        image = Image.fromarray(data, "P")
        image.putpalette(colours)
        image.info["transparency"] = transparent
        encoded.append(image)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    encoded[0].save(
        OUT,
        save_all=True,
        append_images=encoded[1:],
        duration=list(durations),
        loop=0,
        optimize=False,
        disposal=1,
        transparency=transparent,
    )


def main() -> None:
    base = base_layer()
    seal = seal_layer(np.random.default_rng(7))
    frames = [render_frame(base, seal, opacity, scale) for opacity, scale, _ in TIMELINE]
    encode(frames, [duration for _, _, duration in TIMELINE])
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
