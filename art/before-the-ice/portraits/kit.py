# What every half-length portrait shares: a 64x80 canvas drawn shape by shape in a named palette, then an ink
# outline and a thick paper-white cut-out edge (the bottom stays cut flat), scaled up whole-pixel.
# maggie.py came first and carries its own copy of the finish.
import sys

from PIL import Image, ImageDraw, ImageFilter

W, H = 64, 80
INK = (26, 18, 14, 255)
PAPER = (240, 232, 214, 255)


class Sheet:
    def __init__(self, palette: dict):
        self.c = {k: v + (255,) for k, v in palette.items()}
        self.im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def poly(self, pts, c):
        self.d.polygon(pts, fill=self.c[c])

    def oval(self, box, c):
        self.d.ellipse(box, fill=self.c[c])

    def rect(self, box, c):
        self.d.rectangle(box, fill=self.c[c])

    def line(self, pts, c):
        self.d.line(pts, fill=self.c[c])

    def px(self, pts, c):
        for p in pts:
            self.d.point(p, fill=self.c[c])

    def save(self, path: str, scale: int) -> tuple:
        im = self.im
        grow = im.split()[3].filter(ImageFilter.MaxFilter(3))
        outline = Image.new("RGBA", (W, H), INK)
        outline.putalpha(grow)
        pad = 6
        big = Image.new("RGBA", (W + pad * 2, H + pad), (0, 0, 0, 0))
        mask = Image.new("L", big.size, 0)
        mask.paste(grow, (pad, pad))
        edge = Image.new("RGBA", big.size, PAPER)
        edge.putalpha(mask.filter(ImageFilter.MaxFilter(7)))
        big.alpha_composite(edge)
        big.alpha_composite(outline, (pad, pad))
        big.alpha_composite(im, (pad, pad))
        big.resize((big.width * scale, big.height * scale), Image.NEAREST).save(path)
        return big.size


def finish(sheet: Sheet) -> None:
    """python portraits/<who>.py <out.png> [scale, default 5]"""
    scale = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    print(sheet.save(sys.argv[1], scale))
