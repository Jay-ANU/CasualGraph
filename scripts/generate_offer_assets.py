"""Render the animated hero banner used in recruitment offer emails.

The banner is a looping causal graph: signals travel along the edges from
left to right and converge on one bright node, the candidate. It carries no
text, so it works for every offer and language.

    python scripts/generate_offer_assets.py

writes assets/recruitment/offer-hero.gif. The first frame is a complete
picture on its own, because Outlook for Windows shows only that frame.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "recruitment" / "offer-hero.gif"

WIDTH, HEIGHT = 960, 288  # shown at 600 x 180 in the email
SCALE = 2  # draw at twice the size and downsample for smooth edges
FRAMES = 36
FRAME_MS = 70
COLOURS = 96

BACKGROUND = np.array([6, 8, 18], dtype=np.float32)
CYAN = np.array([34, 211, 238], dtype=np.float32)
VIOLET = np.array([139, 92, 246], dtype=np.float32)
WHITE = np.array([235, 248, 255], dtype=np.float32)

# Layered graph, left to right. Coordinates are fractions of the banner.
LAYERS = [
    [(0.07, 0.34), (0.09, 0.70)],
    [(0.22, 0.20), (0.24, 0.52), (0.21, 0.83)],
    [(0.39, 0.14), (0.41, 0.40), (0.38, 0.64), (0.42, 0.88)],
    [(0.57, 0.26), (0.59, 0.55), (0.56, 0.80)],
    [(0.73, 0.36), (0.75, 0.68)],
    [(0.90, 0.52)],
]
EDGES = [
    ((0, 0), (1, 0)), ((0, 0), (1, 1)), ((0, 1), (1, 1)), ((0, 1), (1, 2)),
    ((1, 0), (2, 0)), ((1, 0), (2, 1)), ((1, 1), (2, 1)), ((1, 1), (2, 2)),
    ((1, 2), (2, 2)), ((1, 2), (2, 3)),
    ((2, 0), (3, 0)), ((2, 1), (3, 0)), ((2, 1), (3, 1)), ((2, 2), (3, 1)),
    ((2, 2), (3, 2)), ((2, 3), (3, 2)),
    ((3, 0), (4, 0)), ((3, 1), (4, 0)), ((3, 1), (4, 1)), ((3, 2), (4, 1)),
    ((4, 0), (5, 0)), ((4, 1), (5, 0)),
]


FINAL = (len(LAYERS) - 1, 0)  # the candidate


def node_xy(layer: int, index: int) -> tuple[float, float]:
    fx, fy = LAYERS[layer][index]
    return fx * WIDTH * SCALE, fy * HEIGHT * SCALE


def colour_at(x: float) -> np.ndarray:
    """Cyan on the left fading to violet on the right."""
    t = min(1.0, max(0.0, x / (WIDTH * SCALE)))
    return CYAN * (1 - t) + VIOLET * t


def rgb(colour: np.ndarray, alpha: float = 1.0) -> tuple[int, int, int]:
    value = np.clip(colour * alpha, 0, 255)
    return tuple(int(v) for v in value)


def radial(width: int, height: int, cx: float, cy: float, radius: float) -> np.ndarray:
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    distance = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / radius
    return np.clip(1 - distance, 0, 1) ** 2


def static_layer() -> np.ndarray:
    """Everything that never moves: background, grid, edges and the glowing nodes."""
    w, h = WIDTH * SCALE, HEIGHT * SCALE
    image = np.tile(BACKGROUND, (h, w, 1))
    image += radial(w, h, w * 0.12, h * 0.15, w * 0.55)[..., None] * CYAN * 0.16
    image += radial(w, h, w * 0.88, h * 0.95, w * 0.60)[..., None] * VIOLET * 0.20

    lines = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(lines)
    step = 32 * SCALE
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=255, width=1)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=255, width=1)
    image += (np.asarray(lines, dtype=np.float32) / 255.0)[..., None] * 9.0

    edges = Image.new("RGB", (w, h), (0, 0, 0))
    draw = ImageDraw.Draw(edges)
    for (a, b) in EDGES:
        x1, y1 = node_xy(*a)
        x2, y2 = node_xy(*b)
        draw.line([(x1, y1), (x2, y2)], fill=rgb(colour_at((x1 + x2) / 2), 0.42), width=2 * SCALE)
    image += np.asarray(edges, dtype=np.float32)

    sharp = Image.new("RGB", (w, h), (0, 0, 0))
    soft = Image.new("RGB", (w, h), (0, 0, 0))
    sharp_draw = ImageDraw.Draw(sharp)
    soft_draw = ImageDraw.Draw(soft)
    for layer, nodes in enumerate(LAYERS):
        for index in range(len(nodes)):
            x, y = node_xy(layer, index)
            colour = colour_at(x)
            is_final = (layer, index) == FINAL
            radius = (9.0 if is_final else 4.6) * SCALE
            halo = radius * (2.6 if is_final else 2.2)
            soft_draw.ellipse([x - halo, y - halo, x + halo, y + halo], fill=rgb(colour, 0.75 if is_final else 0.6))
            sharp_draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=rgb(colour, 0.95))
            core = radius * 0.55
            sharp_draw.ellipse([x - core, y - core, x + core, y + core], fill=rgb(WHITE, 0.8))
    image += glow(soft, 6.0, 0.9) + np.asarray(sharp, dtype=np.float32) + glow(sharp, 14.0, 0.35)
    return image


def glow(shapes: Image.Image, radius: float, strength: float) -> np.ndarray:
    blurred = shapes.filter(ImageFilter.GaussianBlur(radius * SCALE))
    return np.asarray(blurred, dtype=np.float32) * strength


def render_frame(frame: int, base: np.ndarray, phases: list[float]) -> Image.Image:
    """Only small, crisp things move, so each frame changes few pixels and the GIF stays light."""
    w, h = WIDTH * SCALE, HEIGHT * SCALE
    t = frame / FRAMES
    sharp = Image.new("RGB", (w, h), (0, 0, 0))
    soft = Image.new("RGB", (w, h), (0, 0, 0))
    sharp_draw = ImageDraw.Draw(sharp)
    soft_draw = ImageDraw.Draw(soft)
    arrivals = {}

    for (a, b), phase in zip(EDGES, phases):
        x1, y1 = node_xy(*a)
        x2, y2 = node_xy(*b)
        progress = (t + phase) % 1.0
        # Each pulse travels during the first 60% of its cycle, then rests.
        if progress < 0.6:
            p = progress / 0.6
            eased = p * p * (3 - 2 * p)
            hx, hy = x1 + (x2 - x1) * eased, y1 + (y2 - y1) * eased
            halo = 7 * SCALE
            soft_draw.ellipse([hx - halo, hy - halo, hx + halo, hy + halo], fill=rgb(colour_at(hx), 0.8))
            for trail in range(5):
                q = max(0.0, eased - trail * 0.03)
                px, py = x1 + (x2 - x1) * q, y1 + (y2 - y1) * q
                fade = 1 - trail / 5
                r = (3.0 - trail * 0.4) * SCALE
                sharp_draw.ellipse([px - r, py - r, px + r, py + r], fill=rgb(WHITE * 0.6 + colour_at(px) * 0.4, fade))
        elif progress < 0.75:
            # Flash the target node for a moment after the pulse lands.
            arrivals[b] = max(arrivals.get(b, 0.0), 1 - (progress - 0.6) / 0.15)

    for (layer, index), strength in arrivals.items():
        x, y = node_xy(layer, index)
        radius = (9.0 if (layer, index) == FINAL else 4.6) * SCALE * 1.9
        sharp_draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            outline=rgb(WHITE * 0.5 + colour_at(x) * 0.5, strength),
            width=SCALE,
        )

    # Two ripples leave the candidate's node, half a loop apart, so the loop is seamless.
    fx, fy = node_xy(*FINAL)
    for offset in (0.0, 0.5):
        q = (t + offset) % 1.0
        r = (14 + q * 70) * SCALE
        fade = (1 - q) ** 1.6
        sharp_draw.ellipse([fx - r, fy - r, fx + r, fy + r], outline=rgb(colour_at(fx), 0.9 * fade), width=2 * SCALE)

    image = base + np.asarray(sharp, dtype=np.float32) + glow(soft, 3.0, 0.8)
    frame_image = Image.fromarray(np.clip(image, 0, 255).astype(np.uint8), "RGB")
    return frame_image.resize((WIDTH, HEIGHT), Image.LANCZOS)


def main() -> None:
    rng = random.Random(7)
    # Pulses on the same layer are staggered so the graph always has something moving.
    phases = [(layer_a * 0.17 + rng.random() * 0.5) % 1.0 for ((layer_a, _), _) in EDGES]
    base = static_layer()
    frames = [render_frame(i, base, phases) for i in range(FRAMES)]

    # One shared palette keeps colours stable from frame to frame.
    sample = Image.new("RGB", (WIDTH, HEIGHT * 3))
    for slot, index in enumerate((0, FRAMES // 3, 2 * FRAMES // 3)):
        sample.paste(frames[index], (0, HEIGHT * slot))
    palette = sample.quantize(colors=COLOURS, method=Image.Quantize.MEDIANCUT)
    quantised = [np.asarray(frame.quantize(palette=palette, dither=Image.Dither.NONE)) for frame in frames]

    # After the first frame, pixels that did not change are written as a transparent
    # index and the previous frame shows through, which compresses far better.
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
        duration=FRAME_MS,
        loop=0,
        optimize=False,
        disposal=1,
        transparency=transparent,
    )
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB, {FRAMES} frames)")


if __name__ == "__main__":
    main()
