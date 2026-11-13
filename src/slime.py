"""Slime penyihir imut yang menjelaskan campuran warna TANPA SUARA (semua kode ada di file ini).

Layout (portrait 1080x1920):
  kiri   : kendi kaca (wadah campuran) berisi sendok kayu
  tengah : slime wizard bertopi + tongkat sihir
  kanan  : rak berisi botol kaca warna bahan
Skenario:
  1. Slime mengajak mewarnai: bola warna hasil (mis. ORANGE) bersinar & berputar di atas kepalanya.
  2. Tiap bahan: tongkat menunjuk botol -> botol melayang ke kendi -> menuang -> kembali ke rak.
  3. Sendok melayang mengaduk, warna berubah perlahan -> reveal -> "warna apa selanjutnya?" + like/subscribe/comment.
Penjelasan lewat teks di layar + efek suara sintetis (numpy) + musik lembut.

Pakai:  python -m src.slime orange out.mp4   (dari folder repo)
"""
import math
import os
import random
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

try:
    import colormix
except ImportError:  # dipanggil sebagai paket
    from . import colormix

FPS = 15
SR = 44100
GYF = 0.78  # tinggi tanah (fraksi tinggi video)
INK = (40, 32, 44)
FONT_B = colormix.FONT_B
PAINT = colormix.PAINT_COL
SLIME_COL = (128, 222, 176)
GOLD = (255, 205, 60)
WOOD = (176, 130, 84)
NAMES = {"red": "RED", "yellow": "YELLOW", "blue": "BLUE", "white": "WHITE", "black": "BLACK"}
CONFETTI = [(255, 99, 99), (255, 205, 60), (80, 160, 255), (90, 210, 120), (255, 130, 200), (170, 110, 255)]

T_INTRO, T_ING, T_STIR, T_REVEAL, T_CTA = 3.4, 5.6, 4.0, 3.0, 3.4
CAU_RIM, CAU_RXO, CAU_RYO = 250, 128, 30  # kuali: tinggi bibir dari tanah, jari-jari mulut (satuan u)
BOTTLE_FULL = 0.92  # isi botol saat penuh


# ------------------------------------------------------------------ util
def _font(sz):
    return ImageFont.truetype(FONT_B, max(8, int(sz)))


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_back(x):
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def lerp(a, b, k):
    return a + (b - a) * k


def mixc(a, b, k):
    return tuple(int(round(lerp(a[i], b[i], k))) for i in range(3))


def lum(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def rot(x, y, deg):
    a = math.radians(deg)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def stext(d, xy, s, size, fill=(255, 255, 255), stroke=0, anchor="mm"):
    d.text(xy, s, font=_font(size), fill=fill, anchor=anchor, stroke_width=int(stroke), stroke_fill=INK)


def chip(d, cx, cy, text, col, u, size=44):
    f = _font(size * u)
    tw = f.getlength(text)
    pw, ph = tw + 46 * u, 74 * u
    d.rounded_rectangle((cx - pw / 2, cy - ph / 2 + 5 * u, cx + pw / 2, cy + ph / 2 + 5 * u), radius=int(ph / 2), fill=INK)
    d.rounded_rectangle((cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2), radius=int(ph / 2), fill=col)
    d.text((cx, cy), text, font=f, fill=(255, 255, 255) if lum(col) < 170 else INK, anchor="mm")


def star(d, cx, cy, r, fill, rot_=0.0):
    pts = []
    for i in range(8):
        a = rot_ + i * math.pi / 4
        rr = r if i % 2 == 0 else r * 0.36
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    d.polygon(pts, fill=fill)


def draw_heart(d, cx, cy, r, fill):
    d.ellipse((cx - r, cy - r * .9, cx, cy + r * .1), fill=fill)
    d.ellipse((cx, cy - r * .9, cx + r, cy + r * .1), fill=fill)
    d.polygon([(cx - r * .98, cy - r * .22), (cx + r * .98, cy - r * .22), (cx, cy + r * 1.0)], fill=fill)


def draw_bell(d, cx, cy, r, fill):
    d.pieslice((cx - r * .8, cy - r * .9, cx + r * .8, cy + r * .7), 180, 360, fill=fill)
    d.polygon([(cx - r * .8, cy - r * .1), (cx + r * .8, cy - r * .1), (cx + r * 1.0, cy + r * .6), (cx - r * 1.0, cy + r * .6)],
              fill=fill)
    d.ellipse((cx - r * .22, cy + r * .5, cx + r * .22, cy + r * .95), fill=fill)


def draw_bubble(d, cx, cy, r, fill):
    d.rounded_rectangle((cx - r, cy - r * .8, cx + r, cy + r * .5), radius=int(r * .35), fill=fill)
    d.polygon([(cx - r * .5, cy + r * .4), (cx - r * .8, cy + r * .95), (cx - r * .1, cy + r * .4)], fill=fill)
    for k in (-1, 0, 1):
        d.ellipse((cx + k * r * .42 - r * .1, cy - r * .3, cx + k * r * .42 + r * .1, cy - r * .1), fill=(255, 255, 255))


HORIZON = 0.60  # garis pertemuan dinding & lantai (fraksi tinggi)


def image_bg(path, w, h):
    """Latar dari gambar (mis. hasil generator AI): dipotong 'cover' ke w x h + scrim gelap tipis di atas/bawah agar teks terbaca."""
    im = Image.open(path).convert("RGB")
    k = max(w / im.width, h / im.height)
    im = im.resize((max(w, int(im.width * k + .5)), max(h, int(im.height * k + .5))), Image.LANCZOS)
    x0, y0 = (im.width - w) // 2, (im.height - h) // 2
    bg = im.crop((x0, y0, x0 + w, y0 + h))
    sc = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sc)
    for y in range(int(h * 0.26)):
        sd.line((0, y, w, y), fill=(10, 4, 30, int(150 * (1 - y / (h * 0.26)) ** 1.4)))
    for y in range(int(h * 0.80), h):
        sd.line((0, y, w, y), fill=(10, 4, 30, int(165 * ((y - h * 0.80) / (h * 0.20)) ** 1.2)))
    bg.paste(sc, (0, 0), sc)
    return bg


def make_bg(c, w, h, gyf=GYF, bg_image=None):
    """Ruang pseudo-3D: dinding di atas, lantai papan kayu berperspektif (titik hilang di tengah). Atau gambar latar sendiri."""
    if bg_image:
        return image_bg(bg_image, w, h)
    u = w / 1080
    yh = int(h * HORIZON)
    wall_t, wall_b = mixc((255, 244, 226), c["rgb"], .10), mixc((250, 226, 196), c["rgb"], .20)
    bg = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(bg)
    for y in range(0, yh, 4):
        px.rectangle((0, y, w, y + 4), fill=mixc(wall_t, wall_b, y / yh))
    # panel dinding (wainscot) + garis papan lis
    px.rectangle((0, yh - 150 * u, w, yh), fill=mixc((233, 208, 178), c["rgb"], .12))
    px.line((0, yh - 150 * u, w, yh - 150 * u), fill=mixc(INK, (233, 208, 178), .55), width=max(2, int(4 * u)))
    for k in range(1, 8):
        xx = k * w / 8
        px.line((xx, yh - 150 * u, xx, yh), fill=mixc((233, 208, 178), INK, .12), width=max(2, int(3 * u)))
    # lantai kayu berperspektif
    f1, f2 = mixc((238, 214, 172), c["rgb"], .08), mixc((226, 198, 152), c["rgb"], .08)
    vp = (w / 2, yh - 60 * u)
    px.rectangle((0, yh, w, h), fill=f1)
    n = 16
    for i in range(-n, n):
        xa, xb = w / 2 + i * w * 0.2, w / 2 + (i + 1) * w * 0.2
        if i % 2 == 0:
            px.polygon([(w / 2 + (xa - w / 2) * 0.02, yh), (w / 2 + (xb - w / 2) * 0.02, yh), (xb, h), (xa, h)], fill=f2)
    for i in range(-n, n + 1):
        xb = w / 2 + i * w * 0.2
        px.line((w / 2 + (xb - w / 2) * 0.02, yh, xb, h), fill=mixc(f2, INK, .28), width=max(2, int(3 * u)))
    for k in range(1, 14):
        yy = yh + (h - yh) * (k / 14) ** 1.7
        px.line((0, yy, w, yy), fill=mixc(f2, INK, .14), width=max(2, int(2 * u)))
    px.line((0, yh, w, yh), fill=INK, width=max(3, int(6 * u)))
    # vinyet halus
    vg = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(vg).rectangle((0, 0, w, h), fill=(40, 20, 60, 70))
    ImageDraw.Draw(vg).ellipse((-w * .15, -h * .1, w * 1.15, h * 1.05), fill=(0, 0, 0, 0))
    vg = vg.filter(ImageFilter.GaussianBlur(120 * u))
    bg.paste(vg, (0, 0), vg)
    rnd = random.Random(7)
    px = ImageDraw.Draw(bg)
    for _ in range(26):  # bintik sihir di dinding
        x, y, r = rnd.randint(0, w), rnd.randint(int(h * .27), yh - 160), rnd.randint(int(6 * u), int(20 * u))
        px.ellipse((x - r, y - r, x + r, y + r), fill=mixc(CONFETTI[rnd.randint(0, 5)], wall_b, .78))
    decor(bg, w, h)
    return bg


def _ring(px, cx, cy, r, fill, outline, wd):
    px.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=outline, width=wd)


def deco_window(bg, px, cx, cy, r, u):
    """Jendela bulat dengan langit malam, bulan sabit & bintang."""
    sky = Image.new("RGB", (int(2 * r), int(2 * r)))
    sd = ImageDraw.Draw(sky)
    for y in range(int(2 * r)):
        sd.line((0, y, 2 * r, y), fill=mixc((44, 40, 110), (110, 70, 170), y / (2 * r)))
    for i, (x_, y_, rr) in enumerate(((.3, .28, 5), (.7, .22, 4), (.55, .6, 5), (.25, .65, 4), (.78, .52, 3), (.42, .42, 3))):
        star(sd, x_ * 2 * r, y_ * 2 * r, rr * u * 1.6, (255, 240, 170), i)
    sd.ellipse((r * .95, r * .22, r * 1.65, r * .92), fill=(255, 236, 160))
    sd.ellipse((r * 1.12, r * .12, r * 1.85, r * .82), fill=mixc((44, 40, 110), (110, 70, 170), .3))
    mask = Image.new("L", sky.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 2 * r, 2 * r), fill=255)
    _ring(px, cx, cy, r + 12 * u, (176, 130, 84), INK, max(3, int(7 * u)))
    bg.paste(sky, (int(cx - r), int(cy - r)), mask)
    px.line((cx - r, cy, cx + r, cy), fill=(176, 130, 84), width=max(3, int(8 * u)))
    px.line((cx, cy - r, cx, cy + r), fill=(176, 130, 84), width=max(3, int(8 * u)))
    px.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK, width=max(3, int(6 * u)))
    px.rounded_rectangle((cx - r - 26 * u, cy + r + 10 * u, cx + r + 26 * u, cy + r + 32 * u), radius=int(6 * u), fill=(176, 130, 84),
                         outline=INK, width=max(3, int(6 * u)))
    # pot tanaman kecil di ambang jendela
    px.polygon([(cx - r * .62, cy + r + 10 * u), (cx - r * .34, cy + r + 10 * u), (cx - r * .38, cy + r - 26 * u),
                (cx - r * .58, cy + r - 26 * u)], fill=(214, 108, 80), outline=INK)
    for a_ in (-30, 0, 30):
        ex = cx - r * .48 + math.sin(math.radians(a_)) * 30 * u
        ey = cy + r - 26 * u - math.cos(math.radians(a_)) * 34 * u
        px.line((cx - r * .48, cy + r - 26 * u, ex, ey), fill=(70, 150, 90), width=max(3, int(6 * u)))
        px.ellipse((ex - 11 * u, ey - 11 * u, ex + 11 * u, ey + 11 * u), fill=(110, 200, 120), outline=INK, width=max(2, int(3 * u)))


def deco_herbs(px, cx, y0, u):
    """Rangkaian ramuan kering & bawang putih tergantung di paku dinding."""
    px.line((cx - 80 * u, y0, cx + 80 * u, y0), fill=(150, 108, 70), width=max(3, int(8 * u)))
    for k, (dx, ln, kind) in enumerate(((-62, 70, "herb"), (0, 105, "garlic"), (62, 80, "herb"))):
        x = cx + dx * u
        y1 = y0 + ln * u
        px.line((x, y0, x, y1), fill=INK, width=max(2, int(4 * u)))
        if kind == "herb":
            for a_ in (-40, -15, 15, 40, 0):
                ex = x + math.sin(math.radians(a_)) * 34 * u
                ey = y1 + math.cos(math.radians(a_)) * 52 * u
                px.line((x, y1, ex, ey), fill=INK, width=max(2, int(5 * u)))
                px.ellipse((ex - 11 * u, ey - 15 * u, ex + 11 * u, ey + 15 * u), fill=(110, 190, 110), outline=INK, width=max(2, int(3 * u)))
        else:
            for i in range(3):
                gy_ = y1 + i * 44 * u
                px.ellipse((x - 26 * u, gy_, x + 26 * u, gy_ + 46 * u), fill=(250, 244, 226), outline=INK, width=max(2, int(4 * u)))
                px.polygon([(x - 7 * u, gy_ + 2 * u), (x + 7 * u, gy_ + 2 * u), (x, gy_ - 14 * u)], fill=(250, 244, 226), outline=INK)
        px.ellipse((x - 9 * u, y1 - 6 * u, x + 9 * u, y1 + 8 * u), fill=(226, 70, 90), outline=INK, width=max(2, int(3 * u)))


def deco_books(bg, px, cx, gy, u):
    """Tumpukan buku mantra + lilin menyala."""
    cols = ((150, 60, 110), (60, 100, 160), (90, 140, 90))
    y = gy
    for i, (cc, wd, off) in enumerate(zip(cols, (190, 165, 140), (0, 14, -10))):
        h_ = 44 * u
        x0, x1 = cx - wd * u / 2 + off * u, cx + wd * u / 2 + off * u
        px.rounded_rectangle((x0, y - h_, x1, y), radius=int(8 * u), fill=cc, outline=INK, width=max(3, int(5 * u)))
        px.rectangle((x0 + 12 * u, y - h_ + 4 * u, x0 + 20 * u, y - 4 * u), fill=GOLD)
        px.line((x0 + 36 * u, y - h_ / 2, x1 - 14 * u, y - h_ / 2), fill=mixc(cc, (255, 255, 255), .55), width=max(2, int(4 * u)))
        y -= h_
    # lilin
    cxx = cx + 6 * u
    px.rounded_rectangle((cxx - 20 * u, y - 70 * u, cxx + 20 * u, y), radius=int(8 * u), fill=(255, 246, 220), outline=INK, width=max(3, int(5 * u)))
    px.polygon([(cxx - 12 * u, y - 70 * u), (cxx - 4 * u, y - 70 * u), (cxx - 8 * u, y - 46 * u)], fill=(250, 232, 190))
    S = int(220 * u)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((S * .25, S * .2, S * .75, S * .7), fill=(255, 190, 70, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(26 * u))
    bg.paste(glow, (int(cxx - S / 2), int(y - 118 * u - S / 2 + 40 * u)), glow)
    px.line((cxx, y - 70 * u, cxx, y - 80 * u), fill=INK, width=max(2, int(4 * u)))
    px.polygon([(cxx, y - 118 * u), (cxx + 15 * u, y - 90 * u), (cxx, y - 76 * u), (cxx - 15 * u, y - 90 * u)], fill=(255, 150, 40), outline=INK)
    px.polygon([(cxx, y - 104 * u), (cxx + 7 * u, y - 88 * u), (cxx, y - 80 * u), (cxx - 7 * u, y - 88 * u)], fill=(255, 230, 120))


def deco_mushrooms(px, cx, gy, u):
    for dx, sz in ((-46, 0.8), (0, 1.1), (48, 0.7)):
        x, k = cx + dx * u, u * sz
        px.rounded_rectangle((x - 17 * k, gy - 60 * k, x + 17 * k, gy), radius=int(8 * k), fill=(250, 240, 220), outline=INK, width=max(2, int(4 * k)))
        px.pieslice((x - 52 * k, gy - 118 * k, x + 52 * k, gy - 6 * k), 180, 360, fill=(226, 70, 90), outline=INK, width=max(2, int(4 * k)))
        for ddx, ddy, rr in ((-24, -70, 8), (10, -88, 9), (26, -62, 7)):
            px.ellipse((x + ddx * k - rr * k, gy + ddy * k - rr * k, x + ddx * k + rr * k, gy + ddy * k + rr * k), fill=(255, 255, 255))


def deco_pumpkin(px, cx, gy, u):
    px.ellipse((cx - 70 * u, gy - 96 * u, cx + 70 * u, gy), fill=(246, 140, 40), outline=INK, width=max(3, int(6 * u)))
    for dx in (-34, 0, 34):
        px.arc((cx + dx * u - 22 * u, gy - 94 * u, cx + dx * u + 22 * u, gy - 2 * u), 100 if dx else 90, 260 if dx else 270,
               fill=(214, 108, 20), width=max(2, int(4 * u)))
    px.rounded_rectangle((cx - 9 * u, gy - 118 * u, cx + 11 * u, gy - 90 * u), radius=int(5 * u), fill=(90, 140, 70), outline=INK, width=max(2, int(4 * u)))


def deco_lantern(px, bg, cx, cy, u):
    """Lentera menyala tergantung (statis)."""
    px.line((cx, cy - 90 * u, cx, cy - 30 * u), fill=INK, width=max(2, int(4 * u)))
    S = int(300 * u)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((S * .25, S * .25, S * .75, S * .75), fill=(255, 200, 90, 130))
    glow = glow.filter(ImageFilter.GaussianBlur(30 * u))
    bg.paste(glow, (int(cx - S / 2), int(cy + 20 * u - S / 2)), glow)
    px.polygon([(cx - 30 * u, cy - 30 * u), (cx + 30 * u, cy - 30 * u), (cx + 18 * u, cy - 48 * u), (cx - 18 * u, cy - 48 * u)], fill=(90, 70, 120), outline=INK)
    px.rounded_rectangle((cx - 30 * u, cy - 30 * u, cx + 30 * u, cy + 66 * u), radius=int(10 * u), fill=(255, 226, 130), outline=INK, width=max(3, int(5 * u)))
    px.ellipse((cx - 10 * u, cy + 4 * u, cx + 10 * u, cy + 44 * u), fill=(255, 150, 40), outline=INK, width=max(2, int(3 * u)))
    for dx in (-30, 0, 30):
        px.line((cx + dx * u, cy - 30 * u, cx + dx * u, cy + 66 * u), fill=INK, width=max(2, int(3 * u)))
    px.rectangle((cx - 34 * u, cy + 66 * u, cx + 34 * u, cy + 78 * u), fill=(90, 70, 120), outline=INK)


def deco_crystal(bg, px, cx, gy, u):
    """Bola kristal di dudukan emas (statis)."""
    px.polygon([(cx - 64 * u, gy), (cx + 64 * u, gy), (cx + 40 * u, gy - 40 * u), (cx - 40 * u, gy - 40 * u)], fill=(150, 90, 190), outline=INK)
    px.rounded_rectangle((cx - 74 * u, gy - 14 * u, cx + 74 * u, gy), radius=int(6 * u), fill=GOLD, outline=INK, width=max(3, int(5 * u)))
    r = 62 * u
    cyy = gy - 40 * u - r * 0.85
    S = int(2 * r)
    ball = Image.new("RGB", (S, S))
    bd = ImageDraw.Draw(ball)
    for y in range(S):
        bd.line((0, y, S, y), fill=mixc((190, 150, 255), (70, 60, 170), y / S))
    for i, (x_, y_) in enumerate(((.35, .45), (.62, .6), (.5, .3))):
        star(bd, x_ * S, y_ * S, 9 * u, (255, 245, 190), i)
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).ellipse((0, 0, S - 1, S - 1), fill=255)
    bg.paste(ball, (int(cx - r), int(cyy - r)), m)
    px.ellipse((cx - r, cyy - r, cx + r, cyy + r), outline=INK, width=max(3, int(6 * u)))
    px.ellipse((cx - r * .62, cyy - r * .68, cx - r * .2, cyy - r * .3), fill=(255, 255, 255))


def decor(bg, w, h):
    """Isi ruang lab penyihir (semua statis, digambar di latar)."""
    u = w / 1080
    px = ImageDraw.Draw(bg)
    yh = int(h * HORIZON)
    deco_window(bg, px, w * 0.15, h * 0.425, 84 * u, u)
    px = ImageDraw.Draw(bg)
    deco_herbs(px, w * 0.335, h * 0.348, u)
    deco_lantern(px, bg, w * 0.86, h * 0.275, u)
    # foreground (lebih dekat kamera: lebih besar)
    deco_books(bg, px, w * 0.12, h * 0.895, u * 1.0)
    deco_mushrooms(px, w * 0.30, h * 0.895, u * 1.0)
    deco_pumpkin(px, w * 0.67, h * 0.895, u * 1.0)
    deco_crystal(bg, px, w * 0.88, h * 0.90, u * 1.0)


def add_shadow(img, cx, cy, rx, ry, alpha=90):
    """Bayangan kontak lembut di lantai."""
    S = (int(rx * 2.6), int(ry * 4.0))
    layer = Image.new("RGBA", S, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((S[0] / 2 - rx, S[1] / 2 - ry, S[0] / 2 + rx, S[1] / 2 + ry), fill=(40, 20, 50, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(max(2, ry * 0.45)))
    img.paste(layer, (int(cx - S[0] / 2), int(cy - S[1] / 2)), layer)


def volume(img, pts, hi=70, lo=80, light=(-0.45, -0.55)):
    """Pencahayaan volume: sorot terang di sisi cahaya, gelap di sisi sebaliknya (dipotong bentuk objek)."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0, x1, y1 = int(min(xs)) - 2, int(min(ys)) - 2, int(max(xs)) + 2, int(max(ys)) + 2
    w_, h_ = x1 - x0, y1 - y0
    if w_ < 8 or h_ < 8:
        return
    mask = Image.new("L", (w_, h_), 0)
    ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in pts], fill=255)
    cx, cy = w_ / 2 + light[0] * w_ * 0.55, h_ / 2 + light[1] * h_ * 0.55
    dark = Image.new("L", (w_, h_), lo)
    ImageDraw.Draw(dark).ellipse((cx - w_ * .75, cy - h_ * .75, cx + w_ * .75, cy + h_ * .75), fill=0)
    dark = dark.filter(ImageFilter.GaussianBlur(max(4, min(w_, h_) * 0.18)))
    light_l = Image.new("L", (w_, h_), 0)
    ImageDraw.Draw(light_l).ellipse((cx - w_ * .28, cy - h_ * .22, cx + w_ * .12, cy + h_ * .08), fill=hi)
    light_l = light_l.filter(ImageFilter.GaussianBlur(max(4, min(w_, h_) * 0.12)))
    dk = Image.new("RGBA", (w_, h_), (30, 14, 60, 255))
    dk.putalpha(ImageChops.multiply(dark, mask))
    lt_ = Image.new("RGBA", (w_, h_), (255, 255, 255, 255))
    lt_.putalpha(ImageChops.multiply(light_l, mask))
    img.paste(dk, (x0, y0), dk)
    img.paste(lt_, (x0, y0), lt_)


# ------------------------------------------------------------------ slime
def _ghost(cx, gy, W, H, t, n=100):
    """Siluet slime-hantu: kepala kubah, badan melebar, rok bawah bergelombang."""
    pts = []
    for k in range(n // 2 + 1):  # busur atas, kiri -> kanan
        a = math.pi + k / (n // 2) * math.pi
        ca, sa = math.cos(a), math.sin(a)
        x = cx + W * 0.46 * math.copysign(abs(ca) ** (2 / 2.6), ca)
        y = gy - 0.16 * H - 0.84 * H * (abs(sa) ** 0.85)
        pts.append((x, y))
    for k in range(n // 2 + 1):  # rok, kanan -> kiri
        p = k / (n // 2)
        x = cx + W * 0.5 * (1 - 2 * p) * (1 + 0.04 * math.sin(p * math.pi))
        edge = math.sin(p * math.pi) ** 0.35
        y = gy - 0.10 * H + 0.10 * H * edge + 0.05 * H * math.sin(p * 6 * math.pi + t * 2.2) * edge - 0.06 * H
        pts.append((x, y))
    return pts


def glow_spot(img, x, y, r, col, alpha=120):
    """Cahaya lembut (gaussian) ditempel di atas gambar."""
    S = int(r * 4)
    if S < 8:
        return
    lay = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(lay).ellipse((S * .25, S * .25, S * .75, S * .75), fill=tuple(col) + (alpha,))
    lay = lay.filter(ImageFilter.GaussianBlur(r * 0.55))
    img.paste(lay, (int(x - S / 2), int(y - S / 2)), lay)


def hand_pos(cx, gy, u, q, side, t):
    """Posisi tangan yang melayang; tongkat sihir dipegang di sini."""
    W = 290 * u * (1 + q)
    H = 235 * u * (1 - q * 0.9)
    return (cx + side * W * 0.62, gy - 0.46 * H - 0.18 * W + math.sin(t * 3 + side) * 3 * u)


def slime_body(d, cx, gy, u, q, mood, t, hat_col, look=0.0, img=None):
    """Slime-hantu penyihir tembus pandang: kilau bintang & gelembung di dalam, glow, lengan memegang tongkat, topi ungu."""
    W = 290 * u * (1 + q)
    H = 235 * u * (1 - q * 0.9)
    side = 1 if look >= 0 else -1
    top_c, bot_c, rim_c = (126, 246, 214), (36, 186, 150), (214, 255, 240)
    hp = hand_pos(cx, gy, u, q, side, t)
    sh = (cx + side * W * 0.40, gy - 0.50 * H)          # bahu sisi tongkat
    if img is not None:
        glow_spot(img, cx, gy - 0.45 * H, W * 0.62, (110, 255, 220), 105)
        # cincin sihir di lantai
        lay = Image.new("RGBA", (int(W * 2.6), int(W * 0.9)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        for i, col in enumerate(((255, 120, 220, 170), (120, 230, 255, 170), (255, 230, 120, 150))):
            pad = (8 + i * 12) * u
            ld.ellipse((W * 0.2 + pad * 2, W * 0.1 + pad, W * 2.4 - pad * 2, W * 0.8 - pad), outline=col, width=max(2, int(4 * u)))
        lay = lay.filter(ImageFilter.GaussianBlur(1.2 * u))
        img.paste(lay, (int(cx - W * 1.3), int(gy - W * 0.45 + 6 * u)), lay)
        d = ImageDraw.Draw(img)
    # lengan sisi tongkat (tebal, ujung membulat) + tangan melayang
    aw = 0.075 * W
    arm = [sh, ((sh[0] + hp[0]) / 2 + side * 0.03 * W, (sh[1] + hp[1]) / 2 + 0.02 * W), hp]
    d.line(arm, fill=rim_c, width=int(aw * 2), joint="curve")
    d.ellipse((sh[0] - aw, sh[1] - aw, sh[0] + aw, sh[1] + aw), fill=rim_c)
    d.ellipse((hp[0] - aw * 1.05, hp[1] - aw * 1.05, hp[0] + aw * 1.05, hp[1] + aw * 1.05), fill=rim_c)
    # tangan sisi lain: gumpalan + tetesan
    hx, hy = cx - side * W * 0.50, gy - 0.40 * H
    d.ellipse((hx - 0.085 * W, hy - 0.085 * W, hx + 0.085 * W, hy + 0.085 * W), fill=rim_c)
    dx_, dy_ = hx - side * 0.11 * W, hy - 0.14 * W + math.sin(t * 3) * 3 * u
    d.ellipse((dx_ - 0.046 * W, dy_ - 0.046 * W, dx_ + 0.046 * W, dy_ + 0.046 * W), fill=rim_c)
    # badan: gradasi vertikal dipotong siluet hantu
    pts = _ghost(cx, gy, W, H, t)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0, x1, y1 = int(min(xs)) - 4, int(min(ys)) - 4, int(max(xs)) + 4, int(max(ys)) + 4
    bw, bh = x1 - x0, y1 - y0
    grad = Image.new("RGB", (bw, bh))
    gd = ImageDraw.Draw(grad)
    for yy in range(bh):
        gd.line((0, yy, bw, yy), fill=mixc(top_c, bot_c, (yy / bh) ** 0.9))
    gd.ellipse((bw * .18, bh * .38, bw * .82, bh * 1.05), fill=mixc(top_c, bot_c, .40))   # perut lebih terang
    gd = ImageDraw.Draw(grad)
    rnd = random.Random(11)
    for i in range(26):  # kilau bintang di dalam badan
        px_, py_ = bw * (.14 + .72 * rnd.random()), bh * (.28 + .66 * rnd.random())
        if .17 < px_ / bw < .83 and .26 < py_ / bh < .74:   # jangan menimpa wajah
            continue
        tw = 0.5 + 0.5 * math.sin(t * 3.2 + i * 1.7)
        star(gd, px_, py_, (3 + 5 * tw) * u * 1.2, (235, 255, 250), i)
    for bxr, byr, br in ((.18, .84, .045), (.80, .86, .04), (.62, .90, .028)):  # gelembung
        gd.ellipse((bw * bxr - br * bw, bh * byr - br * bw, bw * bxr + br * bw, bh * byr + br * bw),
                   outline=(225, 255, 248), width=max(2, int(3 * u)))
        gd.ellipse((bw * bxr - br * bw * .5, bh * byr - br * bw * .6, bw * bxr - br * bw * .1, bh * byr - br * bw * .2),
                   fill=(255, 255, 255))
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in pts], fill=255)
    if img is not None:
        img.paste(grad, (x0, y0), mask)
        d = ImageDraw.Draw(img)
    else:
        d.polygon(pts, fill=mixc(top_c, bot_c, .5))
    d.line(pts + [pts[0]], fill=rim_c, width=max(3, int(5 * u)), joint="curve")   # tepi terang
    # kilau besar di kiri
    d.ellipse((cx - 0.40 * W, gy - 0.50 * H, cx - 0.32 * W, gy - 0.50 * H + 0.08 * W), fill=(255, 255, 255))
    d.ellipse((cx - 0.40 * W, gy - 0.38 * H, cx - 0.37 * W, gy - 0.38 * H + 0.05 * W), fill=(255, 255, 255))
    # topi penyihir ungu + pita warna hasil + gesper emas + bintang
    hb = gy - 0.93 * H
    hw = W * 0.40
    sway = math.sin(t * 2.4) * 6 * u
    hcx = cx - 4 * u
    mid = (hcx + 0.02 * W, hb - 0.40 * H)
    tip = (hcx + 0.14 * W + sway, hb - 0.74 * H)
    ungu = (96, 52, 160)
    hat = [(hcx - hw, hb), (mid[0] - hw * 0.34, mid[1]), tip, (mid[0] + hw * 0.36, mid[1] + 0.05 * H), (hcx + hw, hb)]
    d.polygon(hat, fill=ungu)
    d.polygon([tip, (mid[0] + hw * 0.36, mid[1] + 0.05 * H), (hcx + hw, hb), (hcx + hw * 0.1, hb)], fill=(76, 38, 134))
    d.polygon([(hcx - hw, hb), (hcx + hw, hb), (hcx + hw * 0.92, hb - 0.08 * H), (hcx - hw * 0.92, hb - 0.08 * H)], fill=hat_col)
    for sx_, sy_, sr in ((-0.35, -0.20, 0.035), (0.30, -0.33, 0.03), (-0.1, -0.42, 0.025)):
        star(d, mid[0] + sx_ * hw * 2, hb + sy_ * H, sr * H * 2, (255, 230, 120), 0.3)
    star(d, mid[0] + 2 * u, hb - 0.27 * H, 0.12 * H, (255, 230, 70), 0.3)
    d.ellipse((hcx - hw * 1.3, hb - 0.05 * H, hcx + hw * 1.3, hb + 0.08 * H), fill=ungu)
    d.rounded_rectangle((hcx - 0.045 * W, hb - 0.095 * H, hcx + 0.045 * W, hb - 0.005 * H), radius=int(5 * u), outline=GOLD,
                        width=max(3, int(6 * u)))
    d.ellipse((tip[0] - 0.045 * H, tip[1] - 0.045 * H, tip[0] + 0.045 * H, tip[1] + 0.045 * H), fill=GOLD)
    # wajah: mata oval gelap + kilau, pipi, mulut
    ey = gy - 0.56 * H
    eye_c = (24, 70, 80)
    blink = (t % 3.3) < 0.12
    for sg in (-1, 1):
        ex = cx + sg * 0.17 * W + look * 7 * u
        rw, rh = 0.062 * W, 0.105 * H * 1.35
        if blink or mood == "happy":
            d.arc((ex - rw * 1.1, ey - rh * .35, ex + rw * 1.1, ey + rh * .55), 200, 340, fill=eye_c, width=max(3, int(6 * u)))
        else:
            k_ = 1.1 if mood == "o" else 1.0
            d.ellipse((ex - rw * k_, ey - rh * k_, ex + rw * k_, ey + rh * k_), fill=eye_c)
            d.ellipse((ex - rw * .45, ey - rh * .78, ex + rw * .55, ey - rh * .78 + rw * 1.0), fill=(255, 255, 255))
            d.ellipse((ex + rw * .1, ey + rh * .2, ex + rw * .45, ey + rh * .2 + rw * .35), fill=(255, 255, 255))
        bx = cx + sg * 0.30 * W
        d.ellipse((bx - 0.05 * W, ey + 0.15 * H, bx + 0.05 * W, ey + 0.15 * H + 0.07 * W), fill=(255, 160, 185))
    my, mc = ey + 0.17 * H, (226, 100, 112)
    if mood in ("grin", "happy"):
        d.pieslice((cx - 0.085 * W, my - 0.05 * H, cx + 0.085 * W, my + 0.12 * H * 1.4), 0, 180, fill=(40, 40, 70))
        d.pieslice((cx - 0.05 * W, my + 0.03 * H, cx + 0.05 * W, my + 0.12 * H * 1.4), 0, 180, fill=mc)
    elif mood == "o":
        d.ellipse((cx - 0.03 * W, my - 0.02 * H, cx + 0.03 * W, my + 0.10 * H), fill=mc)
    elif mood == "focus":
        d.rounded_rectangle((cx - 0.035 * W, my, cx + 0.035 * W, my + 0.035 * H), radius=int(4 * u), fill=mc)
    else:
        d.pieslice((cx - 0.055 * W, my - 0.035 * H, cx + 0.055 * W, my + 0.075 * H * 1.3), 0, 180, fill=mc)
    return gy - 0.5 * H, gy - H, W * 1.16


def draw_wand(d, base, target, u, t, glow):
    ang = math.atan2(target[1] - base[1], target[0] - base[0])
    L = 150 * u
    tip = (base[0] + math.cos(ang) * L, base[1] + math.sin(ang) * L)
    d.line([base, tip], fill=INK, width=max(4, int(14 * u)))
    d.line([base, tip], fill=(150, 110, 70), width=max(2, int(8 * u)))
    star(d, tip[0], tip[1], (26 + 12 * glow * (0.6 + 0.4 * math.sin(t * 12))) * u, GOLD, t * 2)
    d.ellipse((tip[0] - 8 * u, tip[1] - 8 * u, tip[0] + 8 * u, tip[1] + 8 * u), fill=(255, 255, 255))
    return tip


def beam(d, a, b, t, u, n=8):
    cols = ((255, 214, 80), (255, 140, 210), (140, 220, 255))
    for i in range(n):
        p = (i / n + t * 1.3) % 1.0
        x = lerp(a[0], b[0], p) + math.sin(p * 9 + t * 5) * 16 * u
        y = lerp(a[1], b[1], p) + math.cos(p * 7 + t * 4) * 16 * u
        star(d, x, y, (7 + 9 * math.sin(math.pi * p)) * u, cols[i % 3], p * 6)


def draw_orb(img, cx, cy, r, col, t, strength=1.0):
    """Bola warna bersinar yang berputar (cincin bintang mengorbit)."""
    if r < 4:
        return
    S = int(r * 5)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for k in range(6, 0, -1):
        rr = r * (1.0 + k * 0.2)
        ld.ellipse((S / 2 - rr, S / 2 - rr, S / 2 + rr, S / 2 + rr), fill=col + (int(46 * strength),))
    layer = layer.filter(ImageFilter.GaussianBlur(max(2, r * 0.3)))
    img.paste(layer, (int(cx - S / 2), int(cy - S / 2)), layer)
    d = ImageDraw.Draw(img)
    # cincin belakang
    for i in range(10):
        a = t * 2.6 + i * 0.628
        if math.sin(a) < 0:
            star(d, cx + math.cos(a) * r * 1.75, cy + math.sin(a) * r * 0.5, r * 0.13, GOLD, a)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col, outline=INK, width=max(3, int(r * 0.07)))
    d.ellipse((cx - r * 0.62, cy - r * 0.7, cx - r * 0.18, cy - r * 0.38), fill=mixc(col, (255, 255, 255), .65))
    for i in range(3):  # pusaran putih yang berputar di bola
        a0 = math.degrees(t * 3 + i * 2.1)
        d.arc((cx - r * .65, cy - r * .65, cx + r * .65, cy + r * .65), a0, a0 + 55, fill=mixc(col, (255, 255, 255), .55),
              width=max(2, int(r * .07)))
    for i in range(10):  # cincin depan
        a = t * 2.6 + i * 0.628
        if math.sin(a) >= 0:
            star(d, cx + math.cos(a) * r * 1.75, cy + math.sin(a) * r * 0.5, r * 0.15, GOLD, a)
    for i in range(5):  # percikan
        a = t * 1.5 + i * 1.256
        star(d, cx + math.cos(a) * r * 1.3, cy - r * 1.1 + math.sin(a * 2) * r * .3, r * .1 * (0.6 + 0.4 * math.sin(t * 6 + i)),
              (255, 255, 255), a)


# ------------------------------------------------------------------ botol kaca, rak, kendi
BOTTLE_H = 178  # tinggi botol (satuan lokal)


def _bpts(pts, anchor, theta, s):
    out = []
    for x, y in pts:
        rx, ry = rot(x * s, y * s, theta)
        out.append((anchor[0] + rx, anchor[1] + ry))
    return out


def bottle_lip(anchor, theta, s):
    rx, ry = rot(0, -108 * s, theta)
    return anchor[0] + rx, anchor[1] + ry


def draw_bottle(d, anchor, theta, s, col, fill):
    """Botol kaca. anchor = pusat badan. fill 0..1 isi cairan."""
    body = [(-38, 52), (38, 52), (38, -52), (15, -76), (15, -100), (-15, -100), (-15, -76), (-38, -52)]
    glass = _bpts(body, anchor, theta, s)
    d.polygon(glass, fill=(232, 244, 250))
    if fill > 0.02:
        top = 52 - fill * 104
        liq = [(-38, 52), (38, 52), (38, top), (-38, top)]
        d.polygon(_bpts(liq, anchor, theta, s), fill=col)
        d.polygon(_bpts([(-38, top), (38, top), (38, top + 7), (-38, top + 7)], anchor, theta, s), fill=mixc(col, (255, 255, 255), .3))
    d.line(glass + [glass[0]], fill=INK, width=max(3, int(6 * s)), joint="curve")
    hl = _bpts([(-27, 38), (-27, -40)], anchor, theta, s)
    d.line(hl, fill=(255, 255, 255), width=max(3, int(7 * s)))
    lab = _bpts([(-38, 6), (38, 6), (38, 30), (-38, 30)], anchor, theta, s)
    d.polygon(lab, fill=(255, 251, 240))
    d.line(lab + [lab[0]], fill=INK, width=max(2, int(3 * s)))
    lip = _bpts([(-19, -100), (19, -100), (19, -108), (-19, -108)], anchor, theta, s)
    d.polygon(lip, fill=(232, 244, 250), outline=INK)


def draw_cork(d, center, ang, s):
    """Tutup botol gabus (bisa melayang & miring)."""
    pts = []
    for x, y in ((-15, -10), (15, -10), (13, 10), (-13, 10)):
        rx, ry = rot(x * s, y * s, ang)
        pts.append((center[0] + rx, center[1] + ry))
    d.polygon(pts, fill=(190, 140, 90), outline=INK)
    d.line([pts[0], pts[1]], fill=(222, 178, 126), width=max(2, int(4 * s)))


SHELF_DX, SHELF_DY = -34, -18  # kedalaman rak (sisi belakang bergeser ke arah titik hilang)


def draw_shelf(d, x0, x1, ys, gy, u, tiers_names):
    """Rak kayu 3D: tampak sisi kiri + permukaan atas + papan berkedalaman. ys = y papan (atas ke bawah)."""
    top = ys[0] - 215 * u
    dx, dy = SHELF_DX * u, SHELF_DY * u
    wd, wd2, wd3 = (214, 172, 120), (170, 126, 82), (236, 200, 150)
    lw = max(3, int(6 * u))
    # panel belakang + sisi kiri + atas
    d.rectangle((x0 + dx, top + dy, x1 + dx, gy + dy), fill=(188, 142, 96), outline=INK, width=lw)
    d.polygon([(x0, top), (x0 + dx, top + dy), (x0 + dx, gy + dy), (x0, gy)], fill=wd2, outline=INK)
    d.polygon([(x0, top), (x0 + dx, top + dy), (x1 + dx, top + dy), (x1, top)], fill=wd3, outline=INK)
    d.line([(x0, top), (x0 + dx, top + dy), (x0 + dx, gy + dy), (x0, gy)], fill=INK, width=lw)
    # papan: permukaan atas (berkedalaman) + tepi depan
    for y in ys:
        d.polygon([(x0, y), (x0 + dx, y + dy), (x1 + dx, y + dy), (x1, y)], fill=(224, 186, 134), outline=INK)
        d.rounded_rectangle((x0 - 6 * u, y, x1 + 6 * u, y + 24 * u), radius=int(6 * u), fill=(176, 130, 84), outline=INK, width=lw)
    # rangka depan (tiang kiri-kanan + balok atas)
    for xa, xb in ((x0 - 6 * u, x0 + 14 * u), (x1 - 14 * u, x1 + 6 * u)):
        d.rectangle((xa, top, xb, gy), fill=wd, outline=INK, width=lw)
    d.rectangle((x0 - 6 * u, top, x1 + 6 * u, top + 16 * u), fill=wd, outline=INK, width=lw)


def cauldron_surface(level, u):
    """Offset vertikal permukaan cairan (makin penuh makin naik ke bibir kuali)."""
    lv = min(level, 0.9) / 0.9
    return (1 - lv) * 22 * u


def draw_cauldron(d, img, jx, gy, u, liquid, level, stick, t, swirl):
    """Kuali penyihir (tanpa gagang): badan besi bulat, 3 kaki, cairan bergelembung, sendok kayu bersandar."""
    rim_y = gy - CAU_RIM * u
    rxo, ryo = CAU_RXO * u, CAU_RYO * u
    iron, iron_hi = (62, 64, 88), (112, 116, 148)
    # aura sihir di atas kuali
    if level > 0.02:
        S = int(520 * u)
        layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse((S * .18, S * .32, S * .82, S * .78), fill=liquid + (int(110 * min(1, level / 0.5)),))
        layer = layer.filter(ImageFilter.GaussianBlur(40 * u))
        img.paste(layer, (int(jx - S / 2), int(rim_y - S * .52)), layer)
        d = ImageDraw.Draw(img)
    # alas batu
    for dx, wd in ((-70, 120), (60, 140), (0, 90)):
        d.ellipse((jx + dx * u - wd * u, gy - 14 * u, jx + dx * u + wd * u, gy + 22 * u), fill=(112, 104, 122), outline=INK, width=max(3, int(5 * u)))
    # kaki
    for dx in (-100, 100):
        d.rounded_rectangle((jx + dx * u - 20 * u, gy - 55 * u, jx + dx * u + 20 * u, gy), radius=int(10 * u), fill=iron,
                            outline=INK, width=max(3, int(6 * u)))
    # badan
    pts_l, pts_r = [], []
    y0, y1 = rim_y, gy - 30 * u
    for k in range(21):
        sq = k / 20
        hw = ((1 - sq) ** 2 * 140 + 2 * sq * (1 - sq) * 215 + sq ** 2 * 100) * u
        y = y0 + sq * (y1 - y0)
        pts_l.append((jx - hw, y))
        pts_r.append((jx + hw, y))
    body = pts_l + pts_r[::-1]
    d.polygon(body, fill=iron)
    volume(img, body, hi=85, lo=100)
    d = ImageDraw.Draw(img)
    d.ellipse((jx - 100 * u, y1 - 22 * u, jx + 100 * u, y1 + 22 * u), fill=iron)
    d.line(pts_l + [(jx - 100 * u, y1 + 8 * u), (jx + 100 * u, y1 + 8 * u)] + pts_r[::-1], fill=INK, width=max(4, int(9 * u)),
           joint="curve")
    hl = [(jx - 0.7 * ((1 - sq) ** 2 * 140 + 2 * sq * (1 - sq) * 215 + sq ** 2 * 100) * u, y0 + 40 * u + sq * 150 * u)
          for sq in (0.0, 0.25, 0.5, 0.75, 1.0)]
    d.line(hl, fill=iron_hi, width=max(4, int(12 * u)), joint="curve")
    # bulan sabit + bintang di badan kuali
    S2 = int(120 * u)
    mn = Image.new("RGBA", (S2, S2), (0, 0, 0, 0))
    md = ImageDraw.Draw(mn)
    md.ellipse((S2 * .08, S2 * .08, S2 * .92, S2 * .92), fill=(255, 220, 90, 255))
    md.ellipse((S2 * .30, S2 * .02, S2 * 1.0, S2 * .86), fill=(0, 0, 0, 0))
    img.paste(mn, (int(jx - 78 * u), int(gy - 195 * u)), mn)
    d = ImageDraw.Draw(img)
    star(d, jx + 52 * u, gy - 150 * u, 20 * u, (255, 160, 50), 0.2)
    star(d, jx + 18 * u, gy - 92 * u, 13 * u, (255, 160, 50), 0.5)
    star(d, jx - 92 * u, gy - 100 * u, 11 * u, (255, 160, 50), 0.1)
    # bibir + mulut
    d.ellipse((jx - 150 * u, rim_y - 36 * u, jx + 150 * u, rim_y + 36 * u), fill=(86, 88, 116), outline=INK, width=max(4, int(8 * u)))
    d.ellipse((jx - rxo, rim_y - ryo, jx + rxo, rim_y + ryo), fill=(26, 22, 38), outline=INK, width=max(3, int(5 * u)))
    oy = cauldron_surface(level, u)
    if level > 0.01:
        bw, bh = int(2 * rxo) + 4, int(2 * ryo) + 4
        layer = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.ellipse((2, 2 + oy, bw - 2, bh - 2 + oy), fill=liquid + (255,))
        ld.ellipse((bw * .22, 2 + oy + bh * .18, bw * .78, 2 + oy + bh * .5), fill=mixc(liquid, (255, 255, 255), .25) + (255,))
        mask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(mask).ellipse((2, 2, bw - 2, bh - 2), fill=255)
        layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
        img.paste(layer, (int(jx - rxo - 2), int(rim_y - ryo - 2)), layer)
        d = ImageDraw.Draw(img)
        if swirl > 0.05:
            for i in range(3):
                a0 = math.degrees(t * 7 + i * 2.1)
                d.arc((jx - rxo * .8, rim_y - ryo * .6 + oy, jx + rxo * .8, rim_y + ryo * .6 + oy), a0, a0 + 70,
                      fill=mixc(liquid, (255, 255, 255), .6), width=max(2, int(5 * u)))
        for i in range(7):  # gelembung naik
            p = (t * 0.55 + i * 0.143) % 1.0
            bx_ = jx + (((i * 37) % 100) - 50) / 50 * rxo * 0.7
            by_ = rim_y + oy - p * 85 * u
            br = (6 + 7 * (1 - p)) * u
            d.ellipse((bx_ - br, by_ - br, bx_ + br, by_ + br), outline=mixc(liquid, (255, 255, 255), .55), width=max(2, int(3 * u)))
    # sendok kayu: bagian kering di udara, bagian basah menembus permukaan & hilang di dalam cairan
    if stick:
        T, B = stick
        ys_ = rim_y + oy
        wet = B[1] > ys_ + 1 and T[1] < ys_
        if wet:
            sf = (ys_ - T[1]) / (B[1] - T[1])
            E = (T[0] + (B[0] - T[0]) * sf, ys_)
        else:
            E = B
        d.line([T, E], fill=INK, width=max(4, int(17 * u)))
        d.line([T, E], fill=WOOD, width=max(2, int(11 * u)))
        if wet:
            bw, bh = int(2 * rxo) + 4, int(2 * ryo) + 4
            ox, oy0 = jx - rxo - 2, rim_y - ryo - 2
            layer = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            wc = mixc(WOOD, liquid, .55)
            ImageDraw.Draw(layer).line([(E[0] - ox, E[1] - oy0), (B[0] - ox, B[1] - oy0)], fill=wc + (255,), width=max(4, int(15 * u)))
            mask = Image.new("L", (bw, bh), 0)
            ImageDraw.Draw(mask).ellipse((2, 2, bw - 2, bh - 2), fill=255)
            layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
            img.paste(layer, (int(ox), int(oy0)), layer)
            d = ImageDraw.Draw(img)
            rr = (30 + 8 * math.sin(t * 6)) * u
            for k_, a_ in ((1.0, .8), (1.7, .45)):
                d.ellipse((E[0] - rr * k_, E[1] - rr * k_ * .26, E[0] + rr * k_, E[1] + rr * k_ * .26),
                          outline=mixc(liquid, (255, 255, 255), a_), width=max(2, int(3 * u)))
        else:
            d.ellipse((E[0] - 17 * u, E[1] - 12 * u, E[0] + 17 * u, E[1] + 12 * u), fill=WOOD, outline=INK, width=max(2, int(4 * u)))
    # bibir depan menutupi ujung sendok
    d.arc((jx - 150 * u, rim_y - 36 * u, jx + 150 * u, rim_y + 36 * u), 5, 175, fill=(86, 88, 116), width=max(6, int(16 * u)))
    d.arc((jx - 150 * u, rim_y - 36 * u, jx + 150 * u, rim_y + 36 * u), 5, 175, fill=INK, width=max(3, int(5 * u)))
    return rim_y + oy


# ------------------------------------------------------------------ timeline
def timeline(c):
    segs, t = [("intro", None, 0.0, T_INTRO)], T_INTRO
    for k in c["paint_keys"]:
        segs.append(("ing", k, t, T_ING))
        t += T_ING
    for nm, d_ in (("stir", T_STIR), ("reveal", T_REVEAL), ("cta", T_CTA)):
        segs.append((nm, None, t, d_))
        t += d_
    return segs, t


# ------------------------------------------------------------------ frame
def frame(t, c, segs, total, bg, w, h):
    u = w / 1080
    us = u * 1.25          # skala slime
    sb = u * 0.94 * (1.2 if len(c['paint_keys']) <= 4 else 0.95)  # skala botol (di rak)
    gy = int(h * GYF)
    gy_s, u_s = gy - 70 * u, u * 0.94      # rak: agak di belakang (lebih jauh)
    gy_c, u_c = gy + 16 * u, u * 1.0      # kuali: agak di depan (lebih dekat)
    img = bg.copy()
    d = ImageDraw.Draw(img)
    final = tuple(c["rgb"])
    keys = list(c["paint_keys"])
    n_k = len(keys)

    cx_s = w * 0.5          # slime di tengah
    jx = w * 0.19           # kendi di kiri
    sh0, sh1 = w * 0.70, w * 0.985  # rak di kanan
    board = [gy_s - 570 * u_s, gy_s - 300 * u_s]  # y papan atas, bawah
    per = math.ceil(n_k / 2)

    def slot(j):
        tier = 0 if j < per else 1
        idx = j if tier == 0 else j - per
        cnt = per if tier == 0 else n_k - per
        span = sh1 - sh0 - 60 * u
        gap = min(112 * u, span / max(cnt, 1))
        x = (sh0 + sh1) / 2 + (idx - (cnt - 1) / 2) * gap
        return (x, board[tier] - 52 * sb - 8 * u_s), board[tier]

    cur = segs[-1]
    for s_ in segs:
        if s_[2] <= t < s_[2] + s_[3]:
            cur = s_
            break
    kind, key, t0, dur = cur
    lt = t - t0

    # posisi kuali + sendok kayu (bersandar di dalam kuali)
    rim_y = gy_c - CAU_RIM * u_c
    bot_rest = (jx + 26 * u_c, rim_y + 70 * u_c)
    top_rest = (jx - 115 * u_c, rim_y - 280 * u_c)
    stick = (top_rest, bot_rest)
    stir_amt = 0.0

    def bfill(kk):  # isi botol: penuh, lalu berkurang sebanding jumlah yang dituang
        for s_ in segs:
            if s_[0] == "ing" and s_[1] == kk:
                after = BOTTLE_FULL * (1 - 0.85 * c["paint"][kk] / 100)
                return lerp(BOTTLE_FULL, after, clamp((t - (s_[2] + 2.4)) / 1.3))
        return BOTTLE_FULL

    # isi kuali
    acc_w, acc_col, level, pouring = 0.0, [0.0, 0.0, 0.0], 0.0, None
    for s_ in segs:
        if s_[0] != "ing":
            continue
        share = c["paint"][s_[1]]
        prog = clamp((t - (s_[2] + 2.4)) / 1.3)
        if prog > 0:
            acc_w += share * prog
            for i in range(3):
                acc_col[i] += PAINT[s_[1]][i] * share * prog
            level += share / 100 * 0.85 * prog
            if 0 < prog < 1:
                pouring = (s_[1], prog)
    liquid = tuple(int(v / acc_w) for v in acc_col) if acc_w > 0 else (240, 240, 240)
    stirred = 0.0
    if kind == "stir":
        stirred = ease_io((lt - 0.8) / 2.2)
    elif kind in ("reveal", "cta"):
        stirred = 1.0
    liquid = mixc(liquid, final, stirred)

    # ------------------------------------------------------------ pose slime / sihir
    q = 0.05 * math.sin(t * 4)
    mood, jump, scale_in = "smile", 0.0, 1.0
    target, glow = None, 0.0
    bottle = None       # (anchor, theta, key, fill)
    held = None
    orb = None          # (cx, cy, r, col, strength)
    orb_y = gy - 800 * u

    if kind == "intro":
        scale_in = ease_out_back((t - 0.1) / 0.7)
        mood = "grin" if t > 0.8 else "smile"
        so = ease_out_back((t - 0.9) / 0.7)
        fade = 1 - ease_io((t - 2.8) / 0.5)
        r_ = 78 * u * clamp(so, 0, 1.15) * (0.4 + 0.6 * fade)
        orb = (cx_s, orb_y - 30 * u * (1 - fade), r_, final, fade)
        if t > 1.5:
            target = (cx_s, orb_y)
            glow = fade
        else:
            target = (cx_s + 200 * u, gy - 560 * u)
    elif kind == "ing":
        i = keys.index(key)
        H, _ = slot(i)
        lip_t = (jx - 6 * u, rim_y - 75 * u)
        lo = rot(0, -108 * sb, -105)
        P = (lip_t[0] - lo[0], lip_t[1] - lo[1])
        theta = 0.0
        arc = 300 * u

        def fly(k, a_, b_):
            return (lerp(a_[0], b_[0], k), lerp(a_[1], b_[1], k) - math.sin(math.pi * k) * arc)

        Hl = (H[0], H[1] - 34 * u)
        if lt < 0.7:
            k = ease_io(lt / 0.7)
            pos, glow, mood = (H[0], lerp(H[1], Hl[1], k)), k, "grin"
        elif lt < 1.9:
            k = ease_io((lt - 0.7) / 1.2)
            pos, theta, glow = fly(k, Hl, P), -10 * math.sin(math.pi * k), 1.0
        elif lt < 2.4:
            k = ease_io((lt - 1.9) / 0.5)
            pos, theta, glow = P, -105 * k, 1.0
        elif lt < 3.7:
            pos, theta, glow, mood = P, -105, 1.0, "o"
        elif lt < 4.1:
            k = ease_io((lt - 3.7) / 0.4)
            pos, theta, glow = P, -105 * (1 - k), 1.0
        elif lt < 5.3:
            k = ease_io((lt - 4.1) / 1.2)
            pos, theta, glow = fly(k, P, Hl), -10 * math.sin(math.pi * k), 1.0
        else:
            k = ease_io((lt - 5.3) / 0.3)
            pos, glow = (H[0], lerp(Hl[1], H[1], k)), 1 - k
        pos = (pos[0], pos[1] + math.sin(t * 5) * 4 * u)
        # tutup botol: terbuka & melayang selama botol dipakai, lalu kembali menutup di rak
        cl_c = (pos[0] + rot(0, -118 * sb, theta)[0], pos[1] + rot(0, -118 * sb, theta)[1])
        lp = bottle_lip(pos, theta, sb)
        fl_c = (lp[0] + 14 * sb, lp[1] - 100 * sb + math.sin(t * 4) * 6 * u)
        fl_a = math.sin(t * 3) * 20
        if lt < 0.9:
            cork = (cl_c, theta)
        elif lt < 1.3:
            k = ease_io((lt - 0.9) / 0.4)
            cork = ((lerp(cl_c[0], fl_c[0], k), lerp(cl_c[1], fl_c[1], k)), lerp(theta, fl_a, k))
        elif lt < 5.2:
            cork = (fl_c, fl_a)
        else:
            k = ease_io((lt - 5.2) / 0.4)
            cork = ((lerp(fl_c[0], cl_c[0], k), lerp(fl_c[1], cl_c[1], k)), lerp(fl_a, theta, k))
        bottle = (pos, theta, key, bfill(key), cork)
        held = key
        target = (pos[0], pos[1] - 20 * sb)
        if 0.7 <= lt < 1.9 or 4.1 <= lt < 5.3:
            q += 0.04 * math.sin(lt * 9)
    elif kind == "stir":
        lift = ease_io(lt / 0.8) * (1 - ease_io((lt - 3.2) / 0.6))
        ang = lt * 9.5
        k_in = ease_io((lt - 0.8) / 0.4) * (1 - ease_io((lt - 3.0) / 0.4))
        bot_st = (jx + math.cos(ang) * 62 * u_c, rim_y + 70 * u_c + math.sin(ang) * 18 * u_c)
        bot = (lerp(bot_rest[0], bot_st[0], k_in), lerp(bot_rest[1], bot_st[1], k_in) - 130 * u_c * lift * (1 - k_in))
        stick = ((top_rest[0] - (bot[0] - bot_rest[0]) * 2.2, top_rest[1] - (bot[1] - bot_rest[1]) * 2.2), bot)
        stir_amt = k_in
        target = (lerp(stick[0][0], stick[1][0], 0.2), lerp(stick[0][1], stick[1][1], 0.2))
        glow, mood = clamp(lift), "focus"
    elif kind == "reveal":
        jump = abs(math.sin(lt * 6.5)) * 150 * u * (1 if lt > 0.3 else lt / 0.3)
        q += 0.1 * (1 - abs(math.sin(lt * 6.5)))
        mood, glow = "happy", 1.0
        so = ease_out_back(lt / 0.8)
        orb = (cx_s, orb_y, 84 * u * clamp(so, 0, 1.15), final, 1.0)
        target = (cx_s, orb_y)
    elif kind == "cta":
        jump = abs(math.sin(lt * 5)) * 30 * u
        mood = "grin"
        target = (cx_s + 200 * u, gy - 560 * u + math.sin(lt * 8) * 30 * u)

    # ------------------------------------------------------------ bintang langit, judul, rumus
    rnd_s = random.Random(21)
    for i in range(16):
        x_, y_ = rnd_s.random() * w, h * (0.33 + 0.12 * rnd_s.random())
        r_ = (8 + 8 * rnd_s.random()) * u * (0.6 + 0.4 * math.sin(t * 3 + i))
        star(d, x_, y_, r_, mixc(GOLD, (255, 247, 230), 0.45), i)

    title = f"How to Make {c['label'].upper()}" if kind != "cta" else "Did you like it?"
    ts = ease_out_back((t - 0.2) / 0.5)
    stext(d, (w / 2, h * 0.075), title, 70 * u * clamp(ts, 0, 1.1), stroke=7 * u)
    dark_bg = lum(bg.resize((1, 1), Image.BOX).getpixel((0, 0))) < 130
    stext(d, (w / 2, h * 0.118), "magic color mixing", 38 * u, fill=(235, 225, 245) if dark_bg else (120, 96, 110), stroke=(5 * u if dark_bg else 0))
    items = []
    for s_ in segs:
        if s_[0] == "ing" and t >= s_[2] + 0.7:
            items.append((s_[1], clamp((t - s_[2] - 0.7) / 0.35)))
    if items:
        f = _font(44 * u)
        widths = [f.getlength(f"{c['paint'][k]}% {NAMES[k]}") + 46 * u for k, _ in items]
        plus = 54 * u
        tot = sum(widths) + plus * (len(items) - 1)
        x = w / 2 - tot / 2
        yy = h * 0.19
        for idx, ((k, a), wd) in enumerate(zip(items, widths)):
            chip(d, x + wd / 2, yy + (1 - ease_out_back(a)) * 40 * u, f"{c['paint'][k]}% {NAMES[k]}", PAINT[k], u)
            x += wd
            if idx < len(items) - 1:
                stext(d, (x + plus / 2, yy), "+", 56 * u, fill=INK)
                x += plus
    if kind in ("reveal", "cta"):
        a = ease_out_back(lt / 0.5) if kind == "reveal" else 1.0
        stext(d, (w / 2, h * 0.265), f"= {c['label'].upper()}", 78 * u * clamp(a, 0, 1.15), fill=final if lum(final) < 215 else INK, stroke=(8 * u if dark_bg else 0))
        if kind == "reveal":
            stext(d, (w / 2, h * 0.305), c["hex"], 40 * u, fill=(120, 96, 110))

    # ------------------------------------------------------------ rak + botol (kanan)
    add_shadow(img, (sh0 + sh1) / 2 - 10 * u, gy_s + 6 * u, (sh1 - sh0) / 2 + 40 * u, 30 * u, 95)
    d = ImageDraw.Draw(img)
    draw_shelf(d, sh0, sh1, board, gy_s, u_s, None)
    for j, kk in enumerate(keys):
        a_, by = slot(j)
        if held != kk:
            draw_bottle(d, a_, 0.0, sb, PAINT[kk], bfill(kk))
            draw_cork(d, (a_[0], a_[1] - 118 * sb), 0.0, sb)
        stext(d, (a_[0], by + 12 * u_s), NAMES[kk], 21 * u_s, fill=INK)

    # ------------------------------------------------------------ kendi (kiri)
    add_shadow(img, jx + 10 * u, gy_c + 8 * u, 175 * u_c, 34 * u_c, 105)
    d = ImageDraw.Draw(img)
    draw_cauldron(d, img, jx, gy_c, u_c, liquid, level, stick, t, stir_amt)
    d = ImageDraw.Draw(img)

    # ------------------------------------------------------------ slime (tengah)
    sc = clamp(scale_in, 0, 1.15)
    gys = gy - jump
    side = 1 if (target is None or target[0] >= cx_s) else -1
    add_shadow(img, cx_s, gy + 10 * u, 150 * us * sc * (1 - jump / (900 * u)), 28 * us * sc, 105 - int(40 * jump / (150 * u)))
    d = ImageDraw.Draw(img)
    cyb, top, Wb = slime_body(d, cx_s, gys, us * sc, q, mood, t, final, look=0.6 * side, img=img)
    d = ImageDraw.Draw(img)
    wand_base = hand_pos(cx_s, gys, us * sc, q, side, t)
    tip = None
    if sc > 0.3:
        tip = draw_wand(d, wand_base, target or (cx_s + 200 * u, gys - 400 * u), us * sc, t, glow)
        glow_spot(img, tip[0], tip[1], (34 + 26 * glow) * u, (150, 240, 255), 110 + int(90 * glow))
        d = ImageDraw.Draw(img)
    if tip and target and glow > 0.05 and kind in ("ing", "stir", "intro"):
        beam(d, tip, target, t, u, n=8)
    if kind == "intro" and t < 1.4:  # asap sihir saat muncul
        rnd = random.Random(5)
        for i in range(14):
            a = rnd.random() * 6.28
            r_ = (60 + 220 * ease_io(t / 1.1)) * u * (0.5 + rnd.random())
            star(d, cx_s + math.cos(a) * r_, gy - 150 * us + math.sin(a) * r_ * .7, 10 * u * clamp(1 - t / 1.3), CONFETTI[i % 6], a)
    if orb and orb[2] > 3:
        draw_orb(img, orb[0], orb[1], orb[2], orb[3], t, orb[4])
        d = ImageDraw.Draw(img)

    # ------------------------------------------------------------ botol yang melayang
    if bottle:
        a_, theta, kk, fill_, cork_ = bottle
        if glow > 0.05:
            for rr in (130, 98):
                d.ellipse((a_[0] - rr * u * glow, a_[1] - rr * u * glow, a_[0] + rr * u * glow, a_[1] + rr * u * glow),
                          outline=mixc((255, 247, 230), GOLD, 0.55), width=max(2, int(4 * u)))
        draw_bottle(d, a_, theta, sb, PAINT[kk], fill_)
        draw_cork(d, cork_[0], cork_[1], sb)
        if 0.9 <= lt < 5.2 and (cork_[1] != theta):
            star(d, cork_[0][0] + 22 * sb, cork_[0][1] - 20 * sb, (9 + 4 * math.sin(t * 9)) * u, (255, 214, 80), t * 2)
        if pouring and theta < -80:
            lx, ly = bottle_lip(a_, theta, sb)
            ys = rim_y + cauldron_surface(level, u_c)
            d.line((lx, ly, lx, ys), fill=PAINT[kk], width=int(15 * u))
            rnd = random.Random(int(t * 15))
            for _ in range(5):
                px, py = lx + rnd.uniform(-20, 20) * u, ys - rnd.uniform(0, 28) * u
                rr = rnd.uniform(3, 8) * u
                d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=PAINT[kk])

    # ------------------------------------------------------------ confetti, CTA, caption
    if kind == "reveal" or (kind == "cta" and lt < 1.2):
        tt = (t - segs[-2][2]) if kind == "reveal" else (T_REVEAL + lt)
        rnd = random.Random(3)
        for i in range(70):
            x0 = rnd.random() * w
            sp_ = (260 + rnd.random() * 380) * u
            y = (-200 * u + sp_ * tt + rnd.random() * 300 * u) % (h * 1.05)
            sz = (10 + rnd.random() * 14) * u
            xx = x0 + math.sin(tt * 3 + i) * 30 * u
            if i % 2:
                d.rectangle((xx, y, xx + sz, y + sz * .6), fill=CONFETTI[i % 6])
            else:
                d.ellipse((xx, y, xx + sz, y + sz), fill=CONFETTI[i % 6])
    if kind == "cta":
        row_y = h * 0.36
        for i, (lab, fn, colr) in enumerate((("LIKE", draw_heart, (240, 70, 90)), ("SUBSCRIBE", draw_bell, (255, 170, 30)),
                                              ("COMMENT", draw_bubble, (70, 140, 250)))):
            cx_ = w * (0.2 + 0.3 * i)
            pulse = 1 + 0.16 * max(0.0, math.sin((lt - i * 0.7) * 5)) if lt > i * 0.7 else 1
            ap = clamp(ease_out_back((lt - i * 0.25) / 0.4), 0, 1.2)
            R = 88 * u * clamp(ap, 0, 1)
            d.ellipse((cx_ - R, row_y - R + 6 * u, cx_ + R, row_y + R + 6 * u), fill=INK)
            d.ellipse((cx_ - R, row_y - R, cx_ + R, row_y + R), fill=(255, 255, 255))
            fn(d, cx_, row_y, 62 * u * pulse * ap * .85, colr)
            stext(d, (cx_, row_y + 118 * u), lab, 38 * u * clamp(ap, 0, 1), fill=(255, 255, 255) if dark_bg else INK, stroke=(6 * u if dark_bg else 0))
    if kind == "ing":
        cap = f"Summon the {key} potion!" if lt < 1.9 else f"Add {c['paint'][key]}% {key} paint"
    else:
        cap = {"intro": f"Let's make {c['label']} together!", "stir": "Stir, stir, stir...",
               "reveal": f"Ta-da! {c['label']}!", "cta": "Which color next? Comment!"}[kind]
    stext(d, (w / 2, h * 0.925), cap, 56 * u, stroke=7 * u)
    return img


# ================================================================== LAYOUT LAB (latar gambar)
# koordinat dalam ruang 1080 x 1920 (gambar latar dipotong 'cover' ke ukuran ini)
JARS_X = [640, 754, 875, 999]
JAR_BASE, JAR_TOP, JAR_HW = 1371, 1226, 43
JAR_FMAX = 116            # tinggi isi maksimum toples
BOT_X, BOT_TOP, BOT_BASE = 300, 1296, 1486
BOT_FMAX = 124            # tinggi isi maksimum botol (dari dasar)
T_LING, T_MIX = 3.6, 6.0

# tata letak per gambar latar (koordinat ruang 1080 x 1920)
def _mk_lab1():
    return dict(
        smalls=[dict(cx=x, top=JAR_TOP, base=JAR_BASE, hw=JAR_HW) for x in JARS_X],
        slots=lambda n: list(range(n)),
        big=dict(poly=lambda: _bottle_poly(BOT_X), base=BOT_BASE, fmax=BOT_FMAX, entry=(BOT_X, 1292), glow=(BOT_X, 1420, 150), ry=8),
        slime=dict(cx=502, gy=1625, us=1.0), orb=(502, 1000), ctl_y=790, label="above", behind=False,
        mix_target=(802, 1010), res="bottle")


def _mk_lab2():
    sm = [(263, 1462, 1600, 38), (357, 1458, 1590, 38), (446, 1452, 1578, 36), (530, 1450, 1572, 36), (616, 1448, 1568, 36)]
    return dict(
        smalls=[dict(cx=a, top=b, base=c_, hw=d_) for a, b, c_, d_ in sm],
        slots=lambda n: {1: [2], 2: [1, 3], 3: [0, 2, 4], 4: [0, 1, 3, 4]}.get(n, [0, 1, 2, 3, 4][:n]),
        big=dict(poly=lambda: _rb_poly(763, 1240, 1536, 88, 38), base=1536, fmax=232, entry=(763, 1232), glow=(763, 1420, 190), ry=22),
        slime=dict(cx=480, gy=1350, us=1.0), orb=(480, 840), ctl_y=770, label="below", behind=True,
        mix_target=(763, 1200), res="jar")


LAYOUTS = {}
_LAYOUT = "lab1"


def set_layout(bg_path):
    global _LAYOUT
    if not LAYOUTS:
        LAYOUTS.update(lab1=_mk_lab1(), lab2=_mk_lab2())
    _LAYOUT = "lab2" if bg_path and "lab_bg2" in os.path.basename(str(bg_path)) else "lab1"


def _seg_dur(base, cue, voice):
    v = (voice or {}).get(cue)
    return max(base, v["off"] + v["dur"] + 0.35) if v else base


def timeline_lab(c, voice=None):
    d0 = _seg_dur(T_INTRO, "intro", voice)
    segs, t = [("intro", None, 0.0, d0)], d0
    for k in c["paint_keys"]:
        d_ = _seg_dur(T_LING, f"ling:{k}", voice)
        segs.append(("ling", k, t, d_))
        t += d_
    for nm, base in (("mix", T_MIX), ("reveal", T_REVEAL), ("cta", T_CTA)):
        d_ = _seg_dur(base, nm, voice)
        segs.append((nm, None, t, d_))
        t += d_
    return segs, t


# ------------------------------------------------------------------ narasi (suara kartun ala anak-anak)
VOICE_PITCH = 1.3   # >1 = lebih tinggi (suara Piper dinaikkan pitch-nya; bukan suara anak sungguhan)


def narration_cues(c):
    """[(id, teks, offset detik dari awal segmen)] - kalimat pendek, satu per segmen."""
    sp, keys = c["spoken"], list(c["paint_keys"])
    cues = [("intro", f"Hi friends! Let's make {sp} together!", 0.9)]
    for i, k in enumerate(keys):
        lead = "And finally," if (i == len(keys) - 1 and len(keys) > 1) else ["First,", "Next,", "Then,"][min(i, 2)]
        cues.append((f"ling:{k}", f"{lead} {c['paint'][k]} percent {k}!", 0.2))
    cues += [("mix", "Now watch the colors swirl together!", 0.4),
             ("reveal", f"Ta-da! It's {sp}!", 0.3),
             ("cta", "Which color next? Comment below, and subscribe!", 0.25)]
    return cues


def _wav_dur(path):
    with wave.open(path, "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def make_voice_track(c, workdir, voice="en_US-lessac-medium", pitch=VOICE_PITCH, synth=None):
    """Buat klip suara per segmen -> {id: {path, dur, off}}. Klip yang gagal dibuat dilewati (segmen itu tanpa suara)."""
    os.makedirs(workdir, exist_ok=True)
    if synth is None:
        try:
            from . import tts
        except ImportError:
            import tts
        synth = lambda text, path: tts.make_voice(text, voice, path)
    out = {}
    for n, (cid, text, off) in enumerate(narration_cues(c)):
        raw, fin = os.path.join(workdir, f"vo{n}.mp3"), os.path.join(workdir, f"vo{n}.wav")
        try:
            synth(text, raw)
            af = f"asetrate={int(44100 * pitch)},aresample=44100,atempo={1 / pitch:.5f}" if abs(pitch - 1) > 0.01 else "anull"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", af, "-ar", "44100", "-ac", "1", fin], check=True)
            out[cid] = dict(path=fin, dur=_wav_dur(fin), off=off)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Suara '{cid}' gagal dibuat, segmen ini tanpa narasi: {str(e)[:120]}")
    return out


def _load_wav(path):
    with wave.open(path, "rb") as wf:
        x = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float64) / 32768.0
    return x


def _rb_poly(cx, top, base, hw, r):
    """Siluet tabung dengan dasar membulat."""
    pts = [(cx - hw, top), (cx - hw, base - r)]
    for a in range(180, 89, -10):
        pts.append((cx - hw + r + r * math.cos(math.radians(a)), base - r + r * math.sin(math.radians(a))))
    for a in range(90, -1, -10):
        pts.append((cx + hw - r + r * math.cos(math.radians(a)), base - r + r * math.sin(math.radians(a))))
    pts.append((cx + hw, top))
    return pts


def _bottle_poly(cx):
    L = [(-19, 1300), (-19, 1345), (-24, 1360), (-34, 1372), (-42, 1388), (-42, 1460)]
    pts = [(cx + x, y) for x, y in L]
    r = 26
    for a in range(180, 89, -10):
        pts.append((cx - 42 + r + r * math.cos(math.radians(a)), 1486 - r + r * math.sin(math.radians(a))))
    for a in range(90, -1, -10):
        pts.append((cx + 42 - r + r * math.cos(math.radians(a)), 1486 - r + r * math.sin(math.radians(a))))
    pts += [(cx + 42, 1388), (cx + 34, 1372), (cx + 24, 1360), (cx + 19, 1345), (cx + 19, 1300)]
    return pts


def fill_liquid(img, poly, y_top, col, t, u, alpha=222, ry_=8):
    """Cairan bening di dalam wadah kaca: dipotong siluet, permukaan elips terang, kilau kiri, gelembung."""
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    x0, y0, x1, y1 = int(min(xs)) - 3, int(min(ys)) - 12 * int(u + 1), int(max(xs)) + 3, int(max(ys)) + 3
    bw, bh = x1 - x0, y1 - y0
    if bw < 8 or bh < 8 or y_top >= max(ys) - 2:
        return
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in poly], fill=255)
    m = np.array(mask)
    cut = int(max(0, y_top - y0))
    m[:cut, :] = 0
    row = m[min(bh - 1, cut + 3)]
    nz = np.nonzero(row)[0]
    if nz.size == 0:
        return
    xl, xr = int(nz[0]), int(nz[-1])
    mask = Image.fromarray(m)
    ry = ry_ * u
    ImageDraw.Draw(mask).ellipse((xl, cut - ry, xr, cut + ry), fill=255)
    yy = np.linspace(1.0, 0.72, bh)[:, None, None]
    rgb = (np.ones((bh, bw, 3)) * np.array(col)[None, None, :] * yy).clip(0, 255).astype(np.uint8)
    lay = Image.fromarray(rgb, "RGB")
    ld = ImageDraw.Draw(lay)
    light = mixc(col, (255, 255, 255), .55)
    ld.ellipse((xl, cut - ry, xr, cut + ry), fill=light)
    ld.ellipse((xl + 5 * u, cut - ry * .55, xr - 5 * u, cut + ry * .55), fill=mixc(col, (255, 255, 255), .25))
    ld.rectangle((xl + 6 * u, cut + 6 * u, xl + 13 * u, bh), fill=mixc(col, (255, 255, 255), .5))
    for i in range(4):  # gelembung naik
        p = (t * 0.4 + i * 0.25) % 1.0
        bxx = xl + (xr - xl) * (0.25 + 0.5 * ((i * 37) % 10) / 10)
        byy = bh - 6 * u - p * max(1.0, bh - cut - 10 * u)
        if byy > cut + 4 * u:
            rr = (3 + 2 * (1 - p)) * u
            ld.ellipse((bxx - rr, byy - rr, bxx + rr, byy + rr), outline=mixc(col, (255, 255, 255), .75), width=max(1, int(2 * u)))
    lay.putalpha(mask.point(lambda v: int(v * alpha / 255)))
    img.paste(lay, (x0, y0), lay)


def _bez(p0, pc, p1, k):
    a = (1 - k) ** 2
    b = 2 * k * (1 - k)
    e = k * k
    return (a * p0[0] + b * pc[0] + e * p1[0], a * p0[1] + b * pc[1] + e * p1[1])


def frame_lab(t, c, segs, total, bg, w, h):
    u = w / 1080
    if not LAYOUTS:
        set_layout(None)
    L = LAYOUTS[_LAYOUT]
    sm = L['smalls']
    slots = L['slots'](len(c['paint_keys']))
    big = L['big']
    dy = L['slime']['gy'] - 1625
    img = bg.copy()
    d = ImageDraw.Draw(img)
    final = tuple(c["rgb"])
    keys = list(c["paint_keys"])
    S = lambda x, y: (x * u, y * u)
    cur = segs[-1]
    for s_ in segs:
        if s_[2] <= t < s_[2] + s_[3]:
            cur = s_
            break
    kind, key, t0, dur = cur
    lt = t - t0
    mix_t0 = next(s_[2] for s_ in segs if s_[0] == "mix")
    mix_lt = t - mix_t0
    gy = L['slime']['gy'] * u
    cx_s = L['slime']['cx'] * u
    us = u * L['slime']['us']

    # ---- level toples & botol
    def jar_fill0(k):
        return 0.18 + 0.72 * c["paint"][k] / 100

    def jar_level(k):
        for s_ in segs:
            if s_[0] == "ling" and s_[1] == k:
                f = jar_fill0(k) * ease_io(clamp((t - (s_[2] + 1.8)) / 1.3))
                return f * (1 - clamp((t - mix_t0 - 0.4) / 4.0))
        return 0.0

    acc_w, acc_col = 0.0, [0.0, 0.0, 0.0]
    for k in keys:
        pr = clamp((t - mix_t0 - 1.4) / 4.0)
        acc_w += c["paint"][k] * pr
        for i in range(3):
            acc_col[i] += PAINT[k][i] * c["paint"][k] * pr
    fb = clamp(acc_w / 100.0)
    liquid = tuple(int(v / acc_w) for v in acc_col) if acc_w > 0 else final
    liquid = mixc(liquid, final, clamp((t - mix_t0 - 4.4) / 1.4))
    if kind in ("reveal", "cta"):
        fb, liquid = 1.0, final

    # ---- pose slime
    q = 0.05 * math.sin(t * 4)
    mood, jump, scale_in = "smile", 0.0, 1.0
    target, glow = None, 0.0
    orb = None
    ball = None   # (key, pos, radius)
    orb_pos = (L['orb'][0] * u, L['orb'][1] * u)
    if kind == "intro":
        scale_in = ease_out_back((t - 0.1) / 0.7)
        mood = "grin" if t > 0.8 else "smile"
        so = ease_out_back((t - 0.9) / 0.7)
        fade = 1 - ease_io((t - 2.8) / 0.5)
        orb = (orb_pos[0], orb_pos[1] - 30 * u * (1 - fade), 78 * u * clamp(so, 0, 1.15) * (0.4 + 0.6 * fade), final, fade)
        target, glow = (orb_pos if t > 1.5 else (cx_s + 240 * u, (1150 + dy) * u)), (fade if t > 1.5 else 0.0)
    elif kind == "ling":
        jr = sm[slots[keys.index(key)]]
        mouth = (jr['cx'] * u, (jr['top'] - 4) * u)
        target = mouth
        glow = 1.0 if lt < 1.9 else clamp(1 - (lt - 1.9) / 0.5)
        mood = "grin" if lt < 1.7 else "o"
    elif kind == "mix":
        target = (L['mix_target'][0] * u, (L['mix_target'][1] + 40 * math.sin(lt * 3)) * u)
        glow, mood = 1.0 if mix_lt < 5.4 else clamp(1 - (mix_lt - 5.4) / 0.6), "focus"
        q += 0.03 * math.sin(lt * 7)
    elif kind == "reveal":
        jump = abs(math.sin(lt * 6.5)) * 150 * u * (1 if lt > 0.3 else lt / 0.3)
        q += 0.1 * (1 - abs(math.sin(lt * 6.5)))
        mood, glow = "happy", 1.0
        target = (cx_s + 260 * u, (1080 + dy) * u)
    elif kind == "cta":
        jump = abs(math.sin(lt * 5)) * 30 * u
        mood = "grin"
        target = (cx_s + 260 * u, (1100 + dy) * u + math.sin(lt * 8) * 30 * u)

    # ---- judul + rumus
    title = f"How to Make {c['label'].upper()}" if kind != "cta" else "Did you like it?"
    ts = ease_out_back((t - 0.2) / 0.5)
    stext(d, (w / 2, h * 0.075), title, 70 * u * clamp(ts, 0, 1.1), stroke=7 * u)
    stext(d, (w / 2, h * 0.118), "magic color mixing", 38 * u, fill=(235, 225, 245), stroke=5 * u)
    items = [(s_[1], clamp((t - s_[2] - 1.7) / 0.35)) for s_ in segs if s_[0] == "ling" and t >= s_[2] + 1.7]
    if items:
        f0 = _font(44 * u)
        full = [f0.getlength(f"{c['paint'][k]}% {NAMES[k]}") + 46 * u for k in keys]
        n_all = len(keys)
        sc_ch = min(1.0, 0.94 * w / (sum(full) + 54 * u * (n_all - 1)))   # muat di layar untuk 3-4 bahan
        f = _font(44 * u * sc_ch)
        widths = [f.getlength(f"{c['paint'][k]}% {NAMES[k]}") + 46 * u * sc_ch for k, _ in items]
        plus = 54 * u * sc_ch
        x = w / 2 - (sum(widths) + plus * (len(items) - 1)) / 2
        yy = h * 0.19
        for idx, ((k, a), wd) in enumerate(zip(items, widths)):
            chip(d, x + wd / 2, yy + (1 - ease_out_back(a)) * 40 * u, f"{c['paint'][k]}% {NAMES[k]}", PAINT[k], u * sc_ch)
            x += wd
            if idx < len(items) - 1:
                stext(d, (x + plus / 2, yy), "+", 56 * u * sc_ch, fill=(255, 255, 255), stroke=5 * u)
                x += plus
    if kind in ("reveal", "cta"):
        a = ease_out_back(lt / 0.5) if kind == "reveal" else 1.0
        stext(d, (w / 2, h * 0.265), f"= {c['label'].upper()}", 78 * u * clamp(a, 0, 1.15), fill=mixc(final, (255, 255, 255), .5) if lum(final) < 120 else final,
              stroke=8 * u)
        if kind == "reveal":
            stext(d, (w / 2, h * 0.305), c["hex"], 40 * u, fill=(235, 225, 245), stroke=5 * u)

    # ---- wadah hasil (botol/toples besar)
    if fb > 0.004:
        poly = [(x * u, y * u) for x, y in big['poly']()]
        fill_liquid(img, poly, (big['base'] - fb * big['fmax']) * u, liquid, t, u, ry_=big['ry'])
        d = ImageDraw.Draw(img)
    if kind == "mix" or kind in ("reveal", "cta"):
        pulse = 0.5 + 0.5 * math.sin(t * 5)
        a_ = 0.0
        if kind == "mix":
            a_ = 0.25 + 0.45 * clamp(mix_lt / 5.0)
        elif kind == "reveal":
            a_ = 0.75 + 0.2 * pulse
        else:
            a_ = 0.45
        glow_spot(img, big['glow'][0] * u, big['glow'][1] * u, big['glow'][2] * u, liquid, int(150 * a_))
        d = ImageDraw.Draw(img)

    # ---- slime
    sc = clamp(scale_in, 0, 1.15)
    gys = gy - jump
    side = 1 if (target is None or target[0] >= cx_s) else -1
    add_shadow(img, cx_s, gy + 8 * u, 140 * us * sc * (1 - jump / (900 * u)), 24 * us * sc, 120 - int(50 * jump / (150 * u)))
    d = ImageDraw.Draw(img)
    cyb, top, Wb = slime_body(d, cx_s, gys, us * sc, q, mood, t, final, look=0.6 * side, img=img)
    d = ImageDraw.Draw(img)
    wand_base = hand_pos(cx_s, gys, us * sc, q, side, t)
    tip = None
    if sc > 0.3:
        tip = draw_wand(d, wand_base, target or (cx_s + 200 * u, gys - 400 * u), us * sc, t, glow)
        glow_spot(img, tip[0], tip[1], (34 + 26 * glow) * u, (150, 240, 255), 110 + int(90 * glow))
        d = ImageDraw.Draw(img)
    if tip and target and glow > 0.05 and kind in ("intro", "mix"):
        beam(d, tip, target, t, u, n=8)
    if kind == "intro" and t < 1.4:
        rnd = random.Random(5)
        for i in range(14):
            a = rnd.random() * 6.28
            r_ = (60 + 220 * ease_io(t / 1.1)) * u * (0.5 + rnd.random())
            star(d, cx_s + math.cos(a) * r_, gy - 150 * us + math.sin(a) * r_ * .7, 10 * u * clamp(1 - t / 1.3), CONFETTI[i % 6], a)
    if orb and orb[2] > 3:
        draw_orb(img, orb[0], orb[1], orb[2], orb[3], t, orb[4])
        d = ImageDraw.Draw(img)

    # ---- toples bahan (di depan slime): salin ulang dari latar bila slime berdiri di belakang
    if L['behind']:
        for jr in sm:
            box = (int((jr['cx'] - jr['hw'] - 6) * u), int((jr['top'] - 8) * u), int((jr['cx'] + jr['hw'] + 6) * u), int((jr['base'] + 6) * u))
            bw_, bh_ = box[2] - box[0], box[3] - box[1]
            m_ = Image.new("L", (bw_, bh_), 0)
            ImageDraw.Draw(m_).rounded_rectangle((6 * u, 6 * u, bw_ - 6 * u, bh_ - 6 * u), radius=int(16 * u), fill=255)
            m_ = m_.filter(ImageFilter.GaussianBlur(5 * u))
            img.paste(bg.crop(box), box[:2], m_)
        d = ImageDraw.Draw(img)
    for i, k in enumerate(keys[:5]):
        jr = sm[slots[i]]
        cxj = jr['cx'] * u
        lvl = jar_level(k)
        if lvl > 0.005:
            poly = _rb_poly(cxj, (jr['top'] + 6) * u, (jr['base'] - 4) * u, (jr['hw'] - 5) * u, 20 * u)
            fmax_ = 0.74 * (jr['base'] - jr['top'])
            fill_liquid(img, poly, (jr['base'] - 4 - lvl * fmax_) * u, PAINT[k], t, u)
        d = ImageDraw.Draw(img)
        done = any(s_[0] == "ling" and s_[1] == k and t >= s_[2] + 1.9 for s_ in segs)
        if done:
            a = ease_out_back((t - next(s_[2] for s_ in segs if s_[0] == "ling" and s_[1] == k) - 1.9) / 0.4)
            lsz = 28 if len(keys) <= 2 else 20
            f_ = _font(lsz * u * clamp(a, 0, 1.1))
            pw = f_.getlength(NAMES[k]) + (30 if len(keys) <= 2 else 18) * u
            py = (jr['top'] - 40 if L['label'] == "above" else jr['base'] + 40) * u
            d.rounded_rectangle((cxj - pw / 2, py - 22 * u + 4 * u, cxj + pw / 2, py + 22 * u + 4 * u), radius=int(22 * u), fill=INK)
            d.rounded_rectangle((cxj - pw / 2, py - 22 * u, cxj + pw / 2, py + 22 * u), radius=int(22 * u), fill=PAINT[k])
            stext(d, (cxj, py), NAMES[k], lsz * u * clamp(a, 0, 1.1), fill=(255, 255, 255) if lum(PAINT[k]) < 170 else INK)

    # ---- bola warna: dari ujung tongkat terbang ke toples
    if kind == "ling" and tip:
        col = PAINT[key]
        jr = sm[slots[keys.index(key)]]
        mouth = (jr['cx'] * u, (jr['top'] - 4) * u)
        if lt < 0.6:
            pos, r_ = tip, 26 * u * ease_out_back(lt / 0.6)
        elif lt < 1.7:
            k_ = ease_io((lt - 0.6) / 1.1)
            pos = (lerp(tip[0], mouth[0], k_), lerp(tip[1], mouth[1], k_) - math.sin(math.pi * k_) * 170 * u)
            r_ = 26 * u * (1 - 0.2 * k_)
            for tr in range(1, 5):  # jejak bintang
                kk = max(0.0, k_ - tr * 0.05)
                px_ = (lerp(tip[0], mouth[0], kk), lerp(tip[1], mouth[1], kk) - math.sin(math.pi * kk) * 170 * u)
                star(d, px_[0], px_[1], (10 - tr) * u, mixc(col, (255, 255, 255), .5), tr)
        elif lt < 1.95:
            k_ = (lt - 1.7) / 0.25
            pos, r_ = (mouth[0], mouth[1] + 50 * u * k_), 20 * u * (1 - k_)
        else:
            pos, r_ = mouth, 0
        if r_ > 2:
            glow_spot(img, pos[0], pos[1], r_ * 2.2, col, 140)
            d = ImageDraw.Draw(img)
            d.ellipse((pos[0] - r_, pos[1] - r_, pos[0] + r_, pos[1] + r_), fill=col, outline=(255, 255, 255), width=max(2, int(4 * u)))
            d.ellipse((pos[0] - r_ * .5, pos[1] - r_ * .6, pos[0] - r_ * .1, pos[1] - r_ * .2), fill=(255, 255, 255))
        if 1.8 <= lt < 2.6:  # percikan di mulut toples
            rnd = random.Random(int(t * 12))
            for _ in range(6):
                a_ = rnd.uniform(0, 6.28)
                rr_ = rnd.uniform(10, 46) * u * (lt - 1.7)
                star(d, mouth[0] + math.cos(a_) * rr_, mouth[1] + math.sin(a_) * rr_ * .6, 8 * u, mixc(col, (255, 255, 255), .4), a_)

    # ---- aliran warna: toples -> botol kiri
    if kind == "mix":
        dst = (big['entry'][0] * u, big['entry'][1] * u)
        for i, k in enumerate(keys[:5]):
            jr = sm[slots[i]]
            src = (jr['cx'] * u, (jr['top'] - 4) * u)
            ctl = ((src[0] + dst[0]) / 2, L['ctl_y'] * u)
            nP = max(5, int(c["paint"][k] / 100 * 30))
            for m_ in range(nP):
                age = t - (mix_t0 + 0.4 + (m_ + 0.5) / nP * 4.0)
                if 0 <= age <= 1.15:
                    k_ = ease_io(age / 1.15) if False else age / 1.15
                    p = _bez(src, ctl, dst, k_)
                    r_ = (9 + 4 * math.sin(k_ * math.pi)) * u
                    glow_spot(img, p[0], p[1], r_ * 2.0, PAINT[k], 150)
                    d = ImageDraw.Draw(img)
                    d.ellipse((p[0] - r_, p[1] - r_, p[0] + r_, p[1] + r_), fill=PAINT[k], outline=(255, 255, 255), width=max(2, int(3 * u)))
                    for tr in (1, 2):
                        pp = _bez(src, ctl, dst, max(0.0, k_ - tr * 0.045))
                        star(d, pp[0], pp[1], (6 - tr) * u, mixc(PAINT[k], (255, 255, 255), .55), tr)
        if mix_lt > 1.3:  # kilau di atas botol
            for i in range(6):
                a_ = t * 2 + i
                star(d, (big['entry'][0] + math.cos(a_) * 60) * u, (big['entry'][1] - 22 - 24 * math.sin(a_ * 1.3) - i * 8) * u, 8 * u * (0.6 + 0.4 * math.sin(t * 6 + i)),
                     (255, 245, 200), i)
    if kind == "reveal":
        rnd = random.Random(9)
        for i in range(16):
            ph = (lt * 0.7 + i / 16) % 1.0
            star(d, (big['entry'][0] + rnd.uniform(-70, 70)) * u, (big['entry'][1] + 8 - ph * 280) * u, 10 * u * (1 - ph), CONFETTI[i % 6], ph * 6)

    # ---- confetti, CTA, caption
    if kind == "reveal" or (kind == "cta" and lt < 1.2):
        tt = (t - segs[-2][2]) if kind == "reveal" else (segs[-2][3] + lt)
        rnd = random.Random(3)
        for i in range(70):
            x0 = rnd.random() * w
            sp_ = (260 + rnd.random() * 380) * u
            y = (-200 * u + sp_ * tt + rnd.random() * 300 * u) % (h * 1.05)
            sz = (10 + rnd.random() * 14) * u
            xx = x0 + math.sin(tt * 3 + i) * 30 * u
            if i % 2:
                d.rectangle((xx, y, xx + sz, y + sz * .6), fill=CONFETTI[i % 6])
            else:
                d.ellipse((xx, y, xx + sz, y + sz), fill=CONFETTI[i % 6])
    if kind == "cta":
        row_y = h * 0.36
        for i, (lab, fn, colr) in enumerate((("LIKE", draw_heart, (240, 70, 90)), ("SUBSCRIBE", draw_bell, (255, 170, 30)),
                                              ("COMMENT", draw_bubble, (70, 140, 250)))):
            cx_ = w * (0.2 + 0.3 * i)
            pulse = 1 + 0.16 * max(0.0, math.sin((lt - i * 0.7) * 5)) if lt > i * 0.7 else 1
            ap = clamp(ease_out_back((lt - i * 0.25) / 0.4), 0, 1.2)
            R = 88 * u * clamp(ap, 0, 1)
            d.ellipse((cx_ - R, row_y - R + 6 * u, cx_ + R, row_y + R + 6 * u), fill=INK)
            d.ellipse((cx_ - R, row_y - R, cx_ + R, row_y + R), fill=(255, 255, 255))
            fn(d, cx_, row_y, 62 * u * pulse * ap * .85, colr)
            stext(d, (cx_, row_y + 118 * u), lab, 38 * u * clamp(ap, 0, 1), fill=(255, 255, 255), stroke=6 * u)
    if kind == "ling":
        cap = f"Summon the {key} magic!" if lt < 1.8 else f"Fill the jar: {c['paint'][key]}% {key}"
    else:
        cap = {"intro": f"Let's make {c['label']} together!", "mix": f"Mix them in the {L['res']}...",
               "reveal": f"Ta-da! {c['label']}!", "cta": "Which color next? Comment!"}[kind]
    stext(d, (w / 2, h * 0.925), cap, 56 * u, stroke=7 * u)
    return img


# ------------------------------------------------------------------ audio (sintetis)
def _env(n, a=0.005, r=0.05):
    e = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _lp(x, k):
    return np.convolve(x, np.ones(k) / k, mode="same")


def sfx_pop(rng):
    n = int(.14 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * np.cumsum(500 + 900 * (t / .14)) / SR) * np.exp(-t * 28) * .9


def sfx_whoosh(rng, dur=.5):
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    return _lp(rng.standard_normal(n), 40) * 6 * np.sin(np.pi * t) ** 2 * .5


def sfx_glug(rng, dur):
    n = int(dur * SR)
    out = np.zeros(n)
    step = 0.17
    for k in range(int(dur / step)):
        s0, m = int(k * step * SR), int(.13 * SR)
        tt = np.arange(m) / SR
        f = 190 + 70 * rng.random() + 220 * (tt / .13)
        seg = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 14) * .55
        seg = seg[:max(0, min(m, n - s0))]
        out[s0:s0 + len(seg)] += seg
    out += _lp(rng.standard_normal(n), 25) * 2.2 * _env(n, .1, .15) * .35
    return out * _env(n, .05, .1)


def sfx_swish(rng, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    return _lp(rng.standard_normal(n), 30) * 5 * (.5 + .5 * np.sin(2 * np.pi * 1.6 * t)) * _env(n, .1, .2) * .5


def sfx_chime(notes, gap=.09):
    n = int((1.0 + gap * len(notes)) * SR)
    out = np.zeros(n)
    for i, f in enumerate(notes):
        s0 = int(i * gap * SR)
        tt = np.arange(n - s0) / SR
        out[s0:] += (np.sin(2 * np.pi * f * tt) + .3 * np.sin(2 * np.pi * 2 * f * tt)) * np.exp(-tt * 3.2) * .35
    return out


def sfx_sparkle(rng, dur=.5):
    n = int(dur * SR)
    out = np.zeros(n)
    for _ in range(6):
        s0 = int(rng.random() * max(1, n - 4000))
        f = rng.choice([1318.5, 1568.0, 1760.0, 2093.0, 2637.0])
        tt = np.arange(min(4000, n - s0)) / SR
        out[s0:s0 + len(tt)] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 18) * .3
    return out


def sfx_boing(dur=.35):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 220 + 260 * np.sin(np.pi * t / dur) ** 0.7
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6) * .5


def music(total, rng):
    n = int(total * SR)
    out = np.zeros(n)
    beat = 60 / 108
    scale = [261.63, 293.66, 329.63, 392.0, 440.0, 523.25]
    pattern = [0, 2, 4, 2, 3, 5, 4, 2]
    i = 0
    while i * beat / 2 < total:
        f = scale[pattern[i % len(pattern)]] * (0.5 if i % 4 == 0 else 1)
        s0 = int(i * beat / 2 * SR)
        m = min(int(.35 * SR), n - s0)
        if m <= 0:
            break
        tt = np.arange(m) / SR
        out[s0:s0 + m] += (2 * np.abs(2 * ((f * tt) % 1) - 1) - 1) * np.exp(-tt * 7) * .5
        i += 1
    return out * .22


def build_audio(c, segs, total, path, voice=None):
    rng = np.random.default_rng(11)
    n = int((total + .3) * SR)
    mix = np.zeros(n)
    mus = np.zeros(n)
    m = music(total, rng)
    mus[:min(n, m.size)] += m[:n]

    def put(x, at):
        s0 = int(at * SR)
        if s0 < n:
            x = x[:n - s0]
            mix[s0:s0 + len(x)] += x

    put(sfx_pop(rng), .15)
    put(sfx_sparkle(rng, .9), .2)
    put(sfx_boing(), 1.0)
    put(sfx_chime([784.0, 988.0, 1175.0]), 1.0)
    for kind, key, t0, dur in segs:
        if kind == "ing":
            put(sfx_sparkle(rng, .7), t0)
            put(sfx_whoosh(rng, 1.1), t0 + .8)
            put(sfx_glug(rng, 1.3), t0 + 2.4)
            put(sfx_whoosh(rng, 1.1), t0 + 4.2)
            put(sfx_pop(rng) * .6, t0 + 5.35)
        elif kind == "ling":
            put(sfx_sparkle(rng, .7), t0 + .1)
            put(sfx_whoosh(rng, 1.0), t0 + .65)
            put(sfx_glug(rng, 1.2), t0 + 1.75)
            put(sfx_pop(rng) * .6, t0 + 1.9)
        elif kind == "mix":
            put(sfx_sparkle(rng, .8), t0 + .2)
            for k_ in range(3):
                put(sfx_whoosh(rng, 1.2), t0 + .5 + k_ * 1.4)
            put(sfx_glug(rng, 2.0), t0 + 1.6)
            put(sfx_glug(rng, 1.8), t0 + 3.4)
            put(sfx_swish(rng, 2.0), t0 + 3.6)
            put(sfx_chime([659.25, 880.0, 1046.5]), t0 + 5.2)
        elif kind == "stir":
            put(sfx_sparkle(rng, .7), t0)
            put(sfx_swish(rng, 2.2), t0 + .9)
        elif kind == "reveal":
            put(sfx_chime([523.25, 659.25, 783.99, 1046.5]), t0 + .05)
            for k in range(3):
                put(sfx_boing(), t0 + k * .97)
        elif kind == "cta":
            for i in range(3):
                put(sfx_pop(rng) * .8, t0 + .25 * i)
    if voice:  # narasi: musik & efek diturunkan saat berbicara
        vox, duck = np.zeros(n), np.ones(n)
        for kind, key, t0, dur in segs:
            cid = f"ling:{key}" if kind == "ling" else kind
            v = voice.get(cid)
            if not v:
                continue
            x = _load_wav(v["path"])
            s0 = int((t0 + v["off"]) * SR)
            x = x[:max(0, n - s0)]
            vox[s0:s0 + len(x)] += x
            duck[max(0, s0 - int(.12 * SR)):s0 + len(x) + int(.25 * SR)] = 0.35
        duck = np.convolve(duck, np.ones(int(.12 * SR)) / int(.12 * SR), mode="same")
        mix = mus * duck + mix * (0.55 + 0.45 * duck)
        vp = np.max(np.abs(vox)) or 1
        mix = mix / (np.max(np.abs(mix)) or 1) * 0.45 + vox / vp * 0.55
    else:
        mix = mix + mus
    pk = np.max(np.abs(mix)) or 1
    pcm = (mix / pk * .8 * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ------------------------------------------------------------------ render
def render(c, out_path, w=1080, h=1920, sound=True, bg_image=None, narration=None):
    """narration: None = tanpa suara; atau {"voice": "en_US-lessac-medium", "pitch": 1.3} (hanya untuk tata letak latar gambar)."""
    set_layout(bg_image)
    tl, fr = (timeline_lab, frame_lab) if bg_image else (timeline, frame)
    vt = None
    if narration and bg_image and sound:
        wd = os.path.join(os.path.dirname(os.path.abspath(out_path)), "vo")
        vt = make_voice_track(c, wd, narration.get("voice") or "en_US-lessac-medium", float(narration.get("pitch") or VOICE_PITCH),
                              narration.get("synth")) or None
    segs, total = tl(c, vt) if tl is timeline_lab else tl(c)
    bg = make_bg(c, w, h, bg_image=bg_image)
    n = int(total * FPS)
    tmp = out_path + ".wav"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
           "-framerate", str(FPS), "-i", "-"]
    if sound:
        build_audio(c, segs, total, tmp, vt)
        cmd += ["-i", tmp]
    cmd += ["-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    if sound:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += ["-movflags", "+faststart", out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n):
            p.stdin.write(fr(i / FPS, c, segs, total, bg, w, h).tobytes())
    finally:
        p.stdin.close()
        p.wait()
    if sound and os.path.exists(tmp):
        os.remove(tmp)
    return total


def sample_frames(c, outdir, times, w=540, h=960, bg_image=None):
    set_layout(bg_image)
    os.makedirs(outdir, exist_ok=True)
    tl, fr = (timeline_lab, frame_lab) if bg_image else (timeline, frame)
    segs, total = tl(c)
    bg = make_bg(c, w, h, bg_image=bg_image)
    for t in times:
        fr(t, c, segs, total, bg, w, h).save(os.path.join(outdir, f"s_{t:05.2f}.png"))


_AD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
DEFAULT_BG = next((p for p in (os.path.join(_AD, "lab_bg2.png"), os.path.join(_AD, "lab_bg.png")) if os.path.exists(p)), None)


if __name__ == "__main__":
    label, spoken, rgb = colormix.parse_color(sys.argv[1] if len(sys.argv) > 1 else "orange")
    comp = colormix.composition(label, spoken, rgb)
    print("durasi", render(comp, sys.argv[2] if len(sys.argv) > 2 else "slime_sample.mp4",
                            bg_image=(sys.argv[3] if len(sys.argv) > 3 else os.environ.get("SLIME_BG") or DEFAULT_BG)))
