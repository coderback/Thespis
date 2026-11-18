# A portrait made outside the kit, by an image model, put into the game's portrait format.
#
# The model draws true pixel art but hands it back large and as a JPEG: each pixel a block of about 12x12, softened
# at the edges. So:
#   - restore: find the block size and where the grid starts, and take each block's middle (its median colour),
#     which gives the drawing back at its own size (74x99 for the Klondike set); the colours then go down to a small
#     palette, since the JPEG left near-copies of each;
#   - the background cut out: everything joined to the edge that's close to the corner's colour;
#   - the bottom cut flat: the closing outline and paper rows under the figure dropped, as kit.py leaves its bottom;
#   - stood on the bottom edge of a 95x107 frame and scaled x4 to 380x428, so the conversation screen (which fits
#     every portrait to a 380x430 box) draws it pixel for pixel.
#
#   python portraits/from_ai.py <in.jpg|png> <out.png> [<restored.png>]
#
# A small input (already at its own size, under 200 pixels wide) skips the restore.
import sys
from collections import deque

import numpy as np
from PIL import Image

FRAME = (95, 107)
SCALE = 4
PAD = 6
COLOURS = 40


def _cell(lum: np.ndarray, axis: int) -> tuple:
    """The block size and the offset of the grid along one axis: where the edges between blocks line up best."""
    g = np.abs(np.diff(lum, axis=axis)).sum(axis=1 - axis)
    best = (0.0, 0.0, 0.0)
    for p in np.arange(6.0, 20.01, 0.05):
        for o in np.arange(0, p, 0.5):
            idx = np.round(np.arange(o, len(g), p)).astype(int)
            s = g[idx[idx < len(g)]].mean()
            if s > best[0]:
                best = (s, p, o)
    return best[1], best[2]


def restore(im: Image.Image) -> Image.Image:
    a = np.asarray(im.convert("RGB"), dtype=float)
    lum = a.mean(axis=2)
    p, ox = _cell(lum, 1)
    g = np.abs(np.diff(lum, axis=0)).sum(axis=1)
    oy = max(np.arange(0, p, 0.5),
             key=lambda o: g[np.clip(np.round(np.arange(o, len(g), p)).astype(int), 0, len(g) - 1)].mean())
    xs = np.arange(ox + 1 + p / 2, a.shape[1], p)
    ys = np.arange(oy + 1 + p / 2, a.shape[0], p)
    r = max(1, int(p / 4))
    small = np.zeros((len(ys), len(xs), 3), np.uint8)
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            y0, x0 = int(y), int(x)
            small[j, i] = np.median(a[max(0, y0 - r):y0 + r + 1, max(0, x0 - r):x0 + r + 1].reshape(-1, 3), axis=0)
    out = Image.fromarray(small)
    return out.quantize(COLOURS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")


def _near(c, d, tol=40) -> bool:
    return sum((int(x) - int(y)) ** 2 for x, y in zip(c[:3], d[:3])) < tol * tol


def convert(src: str, out: str, restored: str = "") -> tuple:
    im = Image.open(src).convert("RGB")
    if im.width >= 200:
        im = restore(im)
    if restored:
        im.save(restored)
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    bg = px[0, 0]
    seen = set()
    todo = deque((x, y) for x in range(w) for y in (0, h - 1)) + deque((x, y) for y in range(h) for x in (0, w - 1))
    while todo:  # the background: what's joined to the edge and near the corner's colour
        x, y = todo.popleft()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h) or not _near(px[x, y], bg):
            continue
        seen.add((x, y))
        todo.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    for x, y in seen:
        px[x, y] = (0, 0, 0, 0)
    ink = min((px[x, y] for y in range(h) for x in range(w) if px[x, y][3]), key=lambda c: sum(c[:3]))
    mid = h // 2
    paper = next(px[x, mid] for x in range(w) if px[x, mid][3])  # the first thing in from the left edge
    rows = [y for y in range(h) if any(px[x, y][3] for x in range(w))]
    top, bottom = rows[0], rows[-1]
    while bottom > top and all(px[x, bottom][3] == 0 or _near(px[x, bottom], paper) or _near(px[x, bottom], ink, 30)
                               for x in range(w)):
        bottom -= 1  # the outline and paper that close the figure underneath
    fig = im.crop((0, top, w, bottom + 1))
    if fig.width > FRAME[0] or fig.height > FRAME[1] - PAD:
        raise SystemExit(f"{src}: the figure is {fig.size}, too big for the frame with a {PAD}-pixel margin over it")
    framed = Image.new("RGBA", FRAME, (0, 0, 0, 0))
    framed.alpha_composite(fig, ((FRAME[0] - w) // 2, FRAME[1] - fig.height))  # standing on the bottom edge
    framed.resize((FRAME[0] * SCALE, FRAME[1] * SCALE), Image.NEAREST).save(out)
    return fig.size


if __name__ == "__main__":
    print(convert(*sys.argv[1:4]))
