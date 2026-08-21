import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 500
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "banner.png")

FONT_DIR = r"C:\Windows\Fonts"
FONT_BLACK = os.path.join(FONT_DIR, "ariblk.ttf")
FONT_BOLD = os.path.join(FONT_DIR, "arialbd.ttf")
FONT_REG = os.path.join(FONT_DIR, "arial.ttf")

BLUE = (79, 195, 247)
CYAN = (103, 232, 249)
WHITE = (255, 255, 255)
SOFT = (214, 224, 255)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vertical_gradient(size, top, bottom):
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    w, h = size
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bottom, y / (h - 1)))
    return img


img = vertical_gradient((W, H), (10, 15, 36), (38, 26, 86))
overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(overlay)

# Soft diagonal speed rays (very subtle).
for i in range(6):
    x0 = -200 + i * 250
    pts = [(x0, H + 40), (x0 + 420, H + 40), (x0 + 900, -40), (x0 + 620, -40)]
    d.polygon(pts, fill=(255, 255, 255, 6))

# Glow behind the right badge.
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
for r, alpha in ((300, 38), (230, 60), (170, 70)):
    gd.ellipse((W - 300 - r, H // 2 - r - 40, W - 300 + r, H // 2 + r - 40), fill=(80, 170, 255, alpha))
glow = glow.filter(ImageFilter.GaussianBlur(60))
img.paste(glow, (0, 0), glow)

# Bottom accent stripe.
d.rectangle([0, H - 14, W, H], fill=lerp((40, 160, 240), (140, 90, 255), 0.65))
d.rectangle([0, H - 14, W, H - 5], fill=(24, 32, 62, 90))

# ---- Text ----
font_title = ImageFont.truetype(FONT_BLACK, 104)
font_sub = ImageFont.truetype(FONT_BOLD, 40)
font_tag = ImageFont.truetype(FONT_BOLD, 27)
font_small = ImageFont.truetype(FONT_REG, 24)

d = ImageDraw.Draw(overlay)

# Title with soft shadow.
title = "TurboDL"
tw = d.textbbox((0, 0), title, font=font_title)
tx, ty = 90, 118
d.text((tx + 4, ty + 6), title, font=font_title, fill=(0, 0, 0, 120))
# Gradient title fill via per-letter? simpler: bright white.
d.text((tx, ty), title, font=font_title, fill=WHITE)

# Subtitle: IR AQ B O T with high tracking.
sub = "I R A Q   B O T"
d.text((96, 250), sub, font=font_sub, fill=CYAN)

# Tagline.
tag = "Fast Downloads  -  YouTube  TikTok  Instagram  Facebook  Twitter"
d.text((96, 340), tag, font=font_tag, fill=SOFT)

# Small promo line.
promo = "Free daily quota  +  Premium 2 GB files"
d.text((96, 392), promo, font=font_small, fill=(166, 178, 230))

# Divider line under tagline area.
d.line([(96, 330), (640, 330)], fill=(90, 100, 160, 160), width=2)

# Underline accent for title (short gradient bar).
for x in range(96, 96 + 300):
    t = (x - 96) / 300
    d.line([(x, 228), (x, 234)], fill=lerp((64, 190, 245), (150, 90, 255), t), width=3)

# ---- Download badge on the right ----
bx, by, bs = W - 380, 130, 200
# Badge glass.
badge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
bd = ImageDraw.Draw(badge)
bd.rounded_rectangle([bx, by, bx + bs, by + bs], radius=48, fill=(14, 22, 52, 235), outline=(120, 170, 255, 180), width=3)
bd.rounded_rectangle([bx + 14, by + 14, bx + bs - 14, by + bs - 14], radius=38, fill=(24, 34, 72, 90), outline=(90, 130, 210, 120), width=2)
hd, hw = 26, 88
cx = bx + bs // 2
cy = by + bs // 2
# Arrow shaft.
bd.rounded_rectangle([cx - 14, cy - 6, cx + 14, cy + 14], radius=4, fill=CYAN)
# Arrow head (triangle).
ax0, ax1, ay0, ay1 = cx - hw, cx + hw, cy - 6, cy + hd
bd.polygon([(ax0, cy - 6), (ax1, cy - 6), (cx, cy + hd)], fill=CYAN)
# Loading dots under the arrow.
for i, off in enumerate((-36, 0, 36)):
    bd.ellipse([cx + off - 9, cy + hd + 18, cx + off + 9, cy + hd + 36], fill=(120, 160, 235, 220))
img.paste(badge, (0, 0), badge)
img.paste(overlay, (0, 0), overlay)

img.save(OUT, "PNG")
print("saved", OUT, os.path.getsize(OUT), "bytes", img.size)