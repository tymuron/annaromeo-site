#!/usr/bin/env python3
"""
Build the link-preview image (Open Graph card) for the Vastu site.

The Tilda page never had an og:image, so shared links showed a bare URL. This
composes a 1200x630 card in Anna's own type and palette: her portrait on the
left, the wordmark and title on the right over the burgundy.

The brand fonts ship with the site as .woff, which Pillow cannot read, so they
are converted to .ttf in memory via fontTools.

  python3 tools/make_og_image.py <vastu_site_root> <out.jpg>
"""
import io
import os
import sys

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

BURGUNDY = (0x42, 0x23, 0x26)
GOLD = (0xCA, 0xBC, 0x90)
CREAM = (0xF4, 0xF2, 0xEC)

W, H = 1200, 630

PORTRAIT = "assets/static/tild3431-6539-4162-b934-636233656161/IMG_1633_1_1.jpg"
FONTS = {
    "display": "assets/static/tild3632-3739-4039-b064-323639613839/WulkanDisplayLight.woff",
    "sans": "assets/static/tild6564-3533-4732-a431-613866306131/VelaSans-SemiBold.woff",
    "sans_light": "assets/static/tild3634-6166-4739-a266-656266376666/VelaSans-Light.woff",
}


def load_font(root, key, size):
    f = TTFont(os.path.join(root, FONTS[key]))
    f.flavor = None
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    return ImageFont.truetype(buf, size)


def tracked(draw, xy, text, font, fill, tracking=0):
    """Draw text with letter spacing; returns the width used."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x - xy[0]


def tracked_width(draw, text, font, tracking=0):
    return sum(draw.textlength(c, font=font) for c in text) + tracking * max(0, len(text) - 1)


def main():
    root = sys.argv[1]
    out = sys.argv[2]
    card = Image.new("RGB", (W, H), BURGUNDY)
    d = ImageDraw.Draw(card)

    # portrait, cover-cropped into the left column
    pw = 470
    src = Image.open(os.path.join(root, PORTRAIT)).convert("RGB")
    scale = max(pw / src.width, H / src.height)
    src = src.resize((round(src.width * scale), round(src.height * scale)), Image.LANCZOS)
    left = (src.width - pw) // 2
    top = max(0, int(src.height * 0.04))
    top = min(top, src.height - H)
    card.paste(src.crop((left, top, left + pw, top + H)), (0, 0))

    # a gold seam so the burgundy meets the photo on a defined edge
    d.rectangle([pw, 0, pw + 3, H], fill=GOLD)

    x = pw + 74
    f_kicker = load_font(root, "sans", 19)
    f_name = load_font(root, "display", 92)
    f_role = load_font(root, "sans_light", 25)
    f_url = load_font(root, "sans", 21)

    tracked(d, (x, 132), "VASTU DESIGN", f_kicker, GOLD, tracking=4.2)
    d.text((x, 186), "ANNA", font=f_name, fill=CREAM)
    d.text((x, 286), "ROMEO", font=f_name, fill=CREAM)

    d.rectangle([x, 412, x + 66, 414], fill=GOLD)

    d.text((x, 444), "Васту-дизайнер", font=f_role, fill=CREAM)
    d.text((x, 480), "и архитектор", font=f_role, fill=CREAM)

    tracked(d, (x, 546), "ANNAROMEOVASTU.COM", f_url, GOLD, tracking=2.4)

    card.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    print(f"{out}  {card.size}  {os.path.getsize(out)/1024:.0f} KB")


if __name__ == "__main__":
    main()
