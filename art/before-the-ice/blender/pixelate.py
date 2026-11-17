# The last step of the pixel look: 128 colours, then whole-pixel upscaling for the screens.
# Run: python pixelate.py town.png town-960.png [town-1080.png]
import sys

from PIL import Image

src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB").quantize(128, method=Image.Quantize.MAXCOVERAGE).convert("RGB")
im.save(out)
if len(sys.argv) > 3:
    im.resize((im.width * 2, im.height * 2), Image.NEAREST).save(sys.argv[3])
