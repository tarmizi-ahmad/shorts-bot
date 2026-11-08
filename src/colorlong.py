"""Video color mix versi panjang (sekitar 60 detik): animasi bergerak terus, ditutup ajakan like, subscribe, dan comment.
Semua angka tetap dari kode (colormix.composition). Narasi memakai teks yang sudah divalidasi + templat tetap."""
import math
import os
import random

from PIL import Image, ImageDraw

from . import colormix as cm
from .colormix import CONFETTI, INK, _center, _clamp, _font, _mix, _out_back, _out_cubic, _rr, _star, _title

FPS = 15  # bingkai animasi per detik (FFmpeg menggandakannya ke 30 fps)


def _recap_phrase(c: dict) -> str:
    parts = [f"{c['paint'][k]} percent {k}" for k in cm.PAINT_COL if k in c["paint_keys"] and c["paint"][k] > 0]
    if len(parts) <= 1:
        return parts[0] if parts else "white paint"
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def scenes(c: dict, data: dict) -> list:
    """Susunan scene panjang. hook/paint/screen/fact diambil dari narasi yang sudah divalidasi angkanya."""
    t = {s["kind"]: s["narration"] for s in data["scenes"]}
    sp = c["spoken"]
    return [
        {"kind": "hook", "narration": t["hook"]},
        {"kind": "guess", "narration": f"Take a guess! What colors make {sp}? Think about it. Three, two, one!"},
        {"kind": "mix", "narration": t["paint"]},
        {"kind": "screen", "narration": t["screen"]},
        {"kind": "fact", "narration": t["fact"]},
        {"kind": "shade", "narration": f"Add white paint to make a color lighter, or add black to make it darker. Try it with {sp}!"},
        {"kind": "recap", "narration": f"Quick recap! To make {sp} paint, use {_recap_phrase(c)}. Easy, right?"},
        {"kind": "cta", "narration": "Did you learn something new? Tap like, subscribe for more color recipes, "
                                     "and comment which color we should mix next!"},
    ]


# ------------------------------------------------------------------ elemen bersama
def _sparkle(d, seed, w, h, t):
    """Bintang dan titik yang berkedip dan melayang pelan sepanjang scene."""
    rnd = random.Random(seed)
    u = w / 1080
    for _ in range(18):
        x, y0 = rnd.uniform(0.04, 0.96) * w, rnd.uniform(0.02, 0.47) * h
        ph, sp = rnd.random(), rnd.uniform(0.5, 1.2)
        col, kind = rnd.choice(CONFETTI), rnd.choice("cs")
        if y0 < 0.14 * h and 0.06 * w < x < 0.94 * w:  # jangan menimpa judul
            continue
        r = rnd.uniform(12, 26) * u * (0.55 + 0.45 * math.sin(2 * math.pi * (t * sp + ph)))
        y = y0 + math.sin(2 * math.pi * (t * 0.3 + ph)) * 10 * u
        if r < 2:
            continue
        if kind == "c":
            d.ellipse([x - r, y - r, x + r, y + r], fill=col)
        else:
            _star(d, x, y, r * 1.2, col)


def _heart(d, cx, cy, r, fill, outline, width):
    pts = []
    for i in range(60):
        a = 2 * math.pi * i / 60
        x = 16 * math.sin(a) ** 3
        y = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a))
        pts.append((cx + x * r / 16, cy + y * r / 16))
    d.polygon(pts, fill=fill, outline=outline, width=width)


def _bell(d, cx, cy, r, shake, u):
    cx += shake
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 205, 60), outline=INK, width=max(2, int(4 * u)))
    d.rectangle([cx - r, cy, cx + r, cy + r * 0.7], fill=(255, 205, 60))
    d.rounded_rectangle([cx - r * 1.3, cy + r * 0.55, cx + r * 1.3, cy + r * 0.85], radius=int(r * 0.15),
                        fill=(255, 205, 60), outline=INK, width=max(2, int(4 * u)))
    d.ellipse([cx - r * 0.25, cy + r * 0.85, cx + r * 0.25, cy + r * 1.35], fill=INK)


# ------------------------------------------------------------------ scene
def _hook(d, c, w, h, t, u, shadow):
    _center(d, "WHAT COLORS MAKE", h * 0.04, w, 56 * u, INK)
    _title(d, c["label"].upper(), h * 0.04 + 66 * u, w, 150 * u)
    s = _out_back(t / 0.9) * (1 + 0.035 * math.sin(2 * math.pi * t * 1.1))
    cx, cy, bw, bh = w / 2, h * 0.31, w * 0.38 * s, h * 0.105 * s
    if bw > 4:
        off = 12 * u
        _rr(d, [cx - bw + off, cy - bh + off, cx + bw + off, cy + bh + off], 50 * u, fill=shadow)
        _rr(d, [cx - bw, cy - bh, cx + bw, cy + bh], 50 * u, fill=c["rgb"], outline=INK, width=max(3, int(10 * u)))
    _center(d, c["hex"], h * 0.43, w, 46 * u, INK)


def _guess(d, c, w, h, t, dur, u, shadow):
    _title(d, "CAN YOU GUESS?", h * 0.04, w, 90 * u)
    s = _out_back(t / 0.8)
    cx, cy = w / 2 + math.sin(2 * math.pi * t * 1.3) * 8 * u, h * 0.265
    R = w * 0.15 * s
    if R > 4:
        d.ellipse([cx - R + 10 * u, cy - R + 10 * u, cx + R + 10 * u, cy + R + 10 * u], fill=shadow)
        d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=c["rgb"], outline=INK, width=max(3, int(10 * u)))
        d.text((cx, cy), "?", font=_font(R * 1.3), fill=(255, 255, 255), anchor="mm", stroke_width=max(3, int(6 * u)), stroke_fill=INK)
    for i, num in enumerate(("3", "2", "1")):
        t0 = dur - 2.5 + i * 0.8
        if t0 <= t < t0 + 0.8:
            q = (t - t0) / 0.8
            size = 130 * u * _out_back(min(1.0, q * 3)) * (1 - 0.15 * q)
            if size > 10:
                d.text((w / 2, h * 0.405), num, font=_font(size), fill=(226, 70, 70), anchor="mm",
                       stroke_width=max(3, int(7 * u)), stroke_fill=INK)


def _mix_scene(d, c, w, h, t, dur, u, shadow):
    _title(d, "MIXING TIME!", h * 0.04, w, 90 * u)
    rows = cm._paint_rows(c)
    n = len(rows)
    cx, cy, R = w / 2, h * 0.295 + math.sin(2 * math.pi * t * 0.9) * 3 * u, w * 0.17
    t0, t1 = 0.9, max(2.0, dur - 2.4)
    step = (t1 - t0) / n
    landed, falling = [], []
    for i, (name, pct, col) in enumerate(rows):
        td = t0 + i * step
        if t >= td + 0.6:
            landed.append((i, name, pct, col, td + 0.6))
        elif t >= td:
            falling.append((i, name, pct, col, (t - td) / 0.6))
    if landed:
        tot = sum(x[2] for x in landed) or 1
        mixed = tuple(int(sum(x[3][k] * x[2] for x in landed) / tot) for k in range(3))
    else:
        mixed = (238, 240, 248)
    settle = _clamp((t - (dur - 2.4)) / 1.2)
    cur = _mix(mixed, c["rgb"], settle) if landed else mixed
    d.ellipse([cx - R + 12 * u, cy - R + 12 * u, cx + R + 12 * u, cy + R + 12 * u], fill=shadow)
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=cur, outline=INK, width=max(3, int(10 * u)))
    if landed and settle < 1:  # putaran adukan
        ang = t * 220
        for j, x in enumerate(landed[:3]):
            d.arc([cx - R * 0.68, cy - R * 0.68, cx + R * 0.68, cy + R * 0.68], ang + j * 120, ang + j * 120 + 80,
                  fill=_mix(cur, x[3], 0.7 * (1 - settle)), width=max(4, int(22 * u)))
    d.arc([cx - R * 0.8, cy - R * 0.8, cx + R * 0.8, cy + R * 0.8], 200, 250, fill=(255, 255, 255), width=max(3, int(9 * u)))
    for i, name, pct, col, q in falling:  # bola cat jatuh ke mangkuk
        x = cx + (i - (n - 1) / 2) * w * 0.05
        y = h * 0.125 + (cy - R * 0.15 - h * 0.125) * q * q
        r = w * 0.032 + w * 0.03 * pct / 100
        d.ellipse([x - r, y - r, x + r, y + r], fill=col, outline=INK, width=max(2, int(5 * u)))
    for i, name, pct, col, tl in landed:  # cipratan di tempat jatuh
        k = (t - tl) / 0.35
        if 0 <= k < 1:
            rr = R * (0.5 + 0.6 * k)
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=col, width=max(2, int(8 * u * (1 - k))))
    sp = min(w * 0.24, w * 0.92 / n)
    for i, name, pct, col, tl in landed:  # keterangan bahan
        a = _out_back((t - tl) / 0.4)
        x = w / 2 + (i - (n - 1) / 2) * sp
        r = 19 * u * a
        if r > 2:
            d.ellipse([x - r, h * 0.417 - r, x + r, h * 0.417 + r], fill=col, outline=INK, width=max(2, int(4 * u)))
        txt = f"{pct}% {name.upper()}"
        d.text((x, h * 0.436), txt, font=cm._fit(d, txt, sp * 0.96, 32 * u), fill=INK, anchor="mt")
    if settle > 0.7:  # bintang berputar saat warna jadi
        for j in range(6):
            a = math.radians(t * 90 + j * 60)
            r2 = R * 1.28
            _star(d, cx + math.cos(a) * r2, cy + math.sin(a) * r2, 16 * u * (0.7 + 0.3 * math.sin(t * 8 + j)), CONFETTI[j % 6])


def _fact(d, c, w, h, t, u):
    _title(d, "DID YOU KNOW?", h * 0.04, w, 84 * u)
    s = _out_back(t / 0.9)
    cx, cy, R = w / 2, h * 0.265, w * 0.2 * s
    rot = t * 25
    if R > 4:
        d.ellipse([cx - R - 8 * u, cy - R - 8 * u, cx + R + 8 * u, cy + R + 8 * u], fill=INK)
        for a in range(0, 360, 2):
            r, g, b = cm.colorsys.hsv_to_rgb(a / 360, 1, 1)
            d.pieslice([cx - R, cy - R, cx + R, cy + R], a - 90 + rot - 0.3, a - 90 + rot + 2.3, fill=(int(r * 255), int(g * 255), int(b * 255)))
        r2 = R * 0.62
        d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=c["rgb"], outline=INK, width=max(3, int(8 * u)))
        if not c["neutral"]:
            ang = math.radians(c["hue"] - 90 + rot)
            mr = 24 * u * (1 + 0.25 * math.sin(t * 7))
            mx, my = cx + math.cos(ang) * R * 0.81, cy + math.sin(ang) * R * 0.81
            d.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=c["rgb"], outline=INK, width=max(3, int(6 * u)))
    _title(d, c["label"].upper(), h * 0.265 + w * 0.2 + 16 * u, w, 58 * u)


def _shade(d, c, w, h, t, u, shadow):
    _title(d, "LIGHTER & DARKER", h * 0.04, w, 84 * u)
    box = [w * 0.04, h * 0.155, w * 0.96, h * 0.455]
    cm._card(d, box, shadow, u)
    cols = [_mix(c["rgb"], (255, 255, 255), k) for k in (0.75, 0.5, 0.25)] + [c["rgb"]] + \
           [_mix(c["rgb"], (0, 0, 0), k) for k in (0.25, 0.5, 0.75)]
    n = 7
    sw = (w * 0.88) / n
    base_y = box[3] - h * 0.07
    for i, col in enumerate(cols):
        q = _out_back(_clamp((t - 0.3 - i * 0.18) / 0.5))
        wave = math.sin(2 * math.pi * (t * 0.7 - i / n)) * 9 * u if q >= 1 else 0
        big = 1.25 if i == 3 else 1.0
        x = w * 0.06 + sw * (i + 0.5)
        hh = h * 0.15 * big * q
        if hh > 4:
            _rr(d, [x - sw * 0.38, base_y - hh + wave, x + sw * 0.38, base_y + wave], 18 * u, fill=col, outline=INK, width=max(2, int(5 * u)))
    f = _font(30 * u)
    d.text((w * 0.06 + sw * 1.5, box[3] - 40 * u), "+ WHITE", font=f, fill=INK, anchor="mm")
    d.text((w * 0.06 + sw * 3.5, box[3] - 40 * u), c["label"].upper(), font=cm._fit(d, c["label"].upper(), sw * 1.8, 30 * u), fill=INK, anchor="mm")
    d.text((w * 0.06 + sw * 5.5, box[3] - 40 * u), "+ BLACK", font=f, fill=INK, anchor="mm")


def _cta(d, c, w, h, t, dur, u, shadow, suggest):
    _title(d, "ENJOYED IT?", h * 0.04, w, 90 * u)
    a = t / dur
    y = h * 0.215
    # LIKE
    q = _out_back((a - 0.2) / 0.1)
    if q > 0.02:
        pulse = 1 + 0.12 * math.sin(2 * math.pi * (t * 1.6)) if a > 0.2 else 1
        cx = w * 0.19
        _heart(d, cx, y, w * 0.085 * q * pulse, (226, 50, 80), INK, max(3, int(7 * u)))
        d.text((cx, y + w * 0.1), "LIKE", font=_font(44 * u), fill=INK, anchor="mt")
    # SUBSCRIBE
    q = _out_back((a - 0.36) / 0.1)
    if q > 0.02:
        pressed = a > 0.5
        cx, bw, bh = w * 0.5, w * 0.15 * q, h * 0.03 * q
        col = (110, 110, 125) if pressed else (226, 40, 40)
        _rr(d, [cx - bw + 7 * u, y - bh + 7 * u, cx + bw + 7 * u, y + bh + 7 * u], bh, fill=shadow)
        _rr(d, [cx - bw, y - bh, cx + bw, y + bh], bh, fill=col, outline=INK, width=max(3, int(6 * u)))
        label = "SUBSCRIBED" if pressed else "SUBSCRIBE"
        if q > 0.6:
            d.text((cx, y), label, font=cm._fit(d, label, bw * 1.75, 36 * u), fill=(255, 255, 255), anchor="mm")
        shake = math.sin(t * 16) * 7 * u * _clamp(1 - (a - 0.5) * 6) if pressed else 0
        _bell(d, cx + bw * 0.82, y - bh * 1.25, 20 * u * q, shake, u)
    # COMMENT
    q = _out_back((a - 0.6) / 0.1)
    if q > 0.02:
        cx = w * 0.81
        bw, bh = w * 0.085 * q, w * 0.065 * q
        bob = math.sin(2 * math.pi * t * 1.4) * 5 * u
        _rr(d, [cx - bw, y - bh + bob, cx + bw, y + bh + bob], 26 * u, fill=(255, 255, 255), outline=INK, width=max(3, int(7 * u)))
        d.polygon([(cx - bw * 0.5, y + bh + bob - 2 * u), (cx - bw * 0.2, y + bh + bob - 2 * u), (cx - bw * 0.65, y + bh * 1.45 + bob)],
                  fill=(255, 255, 255), outline=INK)
        for k in (-1, 0, 1):
            rr = 8 * u * q * (1 + 0.3 * math.sin(t * 9 + k))
            d.ellipse([cx + k * bw * 0.42 - rr, y + bob - rr, cx + k * bw * 0.42 + rr, y + bob + rr], fill=INK)
        d.text((cx, y + w * 0.1), "COMMENT", font=_font(44 * u), fill=INK, anchor="mt")
    # warna berikutnya
    sug = (suggest or [])[:5]
    if a > 0.72 and sug:
        _center(d, "WHICH COLOR NEXT?", h * 0.325, w, 46 * u, INK)
        for i, name in enumerate(sug):
            qq = _clamp((a - 0.72 - i * 0.03) / 0.12)
            cx = w * (0.5 + (i - (len(sug) - 1) / 2) * 0.18)
            r = w * 0.05 * _out_back(qq) * (1 + 0.06 * math.sin(t * 5 + i))
            if r > 2:
                d.ellipse([cx - r, h * 0.395 - r, cx + r, h * 0.395 + r], fill=cm.ImageColor.getrgb(cm.FRIENDLY[name]), outline=INK, width=max(3, int(6 * u)))
            if qq > 0.7:
                d.text((cx, h * 0.395 + w * 0.06), name.upper(), font=cm._fit(d, name.upper(), w * 0.17, 28 * u), fill=INK, anchor="mt")


def frame(kind, c, w, h, t, dur, suggest, base, shadow):
    img = base.copy()
    d = ImageDraw.Draw(img)
    u = w / 1080
    _sparkle(d, c["label"] + kind, w, h, t)
    if kind == "hook":
        _hook(d, c, w, h, t, u, shadow)
    elif kind == "guess":
        _guess(d, c, w, h, t, dur, u, shadow)
    elif kind == "mix":
        _mix_scene(d, c, w, h, t, dur, u, shadow)
    elif kind == "screen":
        rows = [(k, c["screen"][k], cm.SCREEN_COL[k]) for k in ("red", "green", "blue")]
        cm._kid_bars(d, c, w, h, "SCREEN LIGHT", "phones & TVs mix light (exact)", rows, min(1.0, t / 1.4), shadow)
    elif kind == "recap":
        cm._kid_bars(d, c, w, h, "QUICK RECAP", cm._paint_sub(c), cm._paint_rows(c), min(1.0, t / 1.4), shadow)
    elif kind == "fact":
        _fact(d, c, w, h, t, u)
    elif kind == "shade":
        _shade(d, c, w, h, t, u, shadow)
    else:
        _cta(d, c, w, h, t, dur, u, shadow, suggest)
    return img


def render(kind: str, c: dict, outdir: str, w: int, h: int, dur: float, suggest=None, fps: int = FPS) -> str:
    """Tulis bingkai untuk seluruh durasi audio. Mengembalikan pola nama file (f_%04d.png)."""
    os.makedirs(outdir, exist_ok=True)
    base, shadow = cm._kid_base(c, w, h)
    n = max(2, int(math.ceil(dur * fps)) + 1)
    for i in range(n):
        frame(kind, c, w, h, i / fps, dur, suggest, base, shadow).save(os.path.join(outdir, f"f_{i:04d}.png"), compress_level=1)
    return os.path.join(outdir, "f_%04d.png")


# ================================================================== versi panjang untuk "A vs B"
def vs_scenes(a: dict, b: dict, data: dict) -> list:
    """hook/paint/screen/diff dari narasi perbandingan (angka dari kode), ditambah scene tebak, pilih favorit, dan ajakan."""
    t = {s["kind"]: s["narration"] for s in data["scenes"]}
    A, B = a["label"], b["label"]
    return [
        {"kind": "hook", "narration": t["hook"]},
        {"kind": "guess", "narration": "Can you spot the difference? Look closely! Three, two, one!"},
        {"kind": "paint", "narration": t["paint"]},
        {"kind": "screen", "narration": t["screen"]},
        {"kind": "diff", "narration": t["diff"]},
        {"kind": "pick", "narration": f"So, which one do you like more, {A} or {B}? Vote in the comments!"},
        {"kind": "cta", "narration": "Did you learn something new? Tap like, subscribe for more color recipes, "
                                     "and comment which colors we should compare next!"},
    ]


def _vs_swatch(d, c, cx, cy, bw, bh, u, shadow):
    if bw > 4 and bh > 4:
        off = 12 * u
        _rr(d, [cx - bw + off, cy - bh + off, cx + bw + off, cy + bh + off], 44 * u, fill=shadow)
        _rr(d, [cx - bw, cy - bh, cx + bw, cy + bh], 44 * u, fill=c["rgb"], outline=INK, width=max(3, int(9 * u)))


def vs_frame(kind, a, b, w, h, t, dur, suggest, base, shadow, mid, diff_lines):
    from . import colorvs  # impor lokal: hindari ketergantungan melingkar
    u = w / 1080
    if kind == "cta":
        return frame("cta", mid, w, h, t, dur, suggest, base, shadow)
    img = base.copy()
    d = ImageDraw.Draw(img)
    _sparkle(d, mid["label"] + kind, w, h, t)
    if kind == "hook":
        _title(d, "WHAT'S THE", h * 0.04, w, 90 * u)
        _title(d, "DIFFERENCE?", h * 0.04 + 100 * u, w, 120 * u)
        s = _out_back(t / 0.9) * (1 + 0.03 * math.sin(2 * math.pi * t * 1.1))
        for c, cx in ((a, w * 0.27), (b, w * 0.73)):
            _vs_swatch(d, c, cx, h * 0.31, w * 0.21 * s, h * 0.09 * s, u, shadow)
            if t > 0.35:
                d.text((cx, h * 0.31 + h * 0.09 + 18 * u), c["label"].upper(), font=cm._fit(d, c["label"].upper(), w * 0.4, 52 * u), fill=INK, anchor="mt")
        r = 52 * u * _out_back(_clamp((t - 0.2) / 0.5)) * (1 + 0.06 * math.sin(2 * math.pi * t * 1.6))
        if r > 3:
            d.ellipse([w / 2 - r, h * 0.31 - r, w / 2 + r, h * 0.31 + r], fill=(226, 70, 70), outline=INK, width=max(3, int(7 * u)))
            if r > 30 * u:
                d.text((w / 2, h * 0.31), "VS", font=_font(r * 0.8), fill=(255, 255, 255), anchor="mm", stroke_width=max(2, int(3 * u)), stroke_fill=INK)
    elif kind == "guess":
        _title(d, "SPOT THE DIFFERENCE!", h * 0.04, w, 80 * u)
        s = _out_back(t / 0.8)
        for c, cx in ((a, w * 0.3), (b, w * 0.7)):
            R = w * 0.14 * s
            if R > 4:
                cy = h * 0.255 + math.sin(2 * math.pi * (t * 1.2 + (0.5 if c is b else 0))) * 8 * u
                d.ellipse([cx - R + 9 * u, cy - R + 9 * u, cx + R + 9 * u, cy + R + 9 * u], fill=shadow)
                d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=c["rgb"], outline=INK, width=max(3, int(9 * u)))
        for i, num in enumerate(("3", "2", "1")):
            t0 = dur - 2.5 + i * 0.8
            if t0 <= t < t0 + 0.8:
                q = (t - t0) / 0.8
                size = 130 * u * _out_back(min(1.0, q * 3)) * (1 - 0.15 * q)
                if size > 10:
                    d.text((w / 2, h * 0.405), num, font=_font(size), fill=(226, 70, 70), anchor="mm", stroke_width=max(3, int(7 * u)), stroke_fill=INK)
    elif kind == "pick":
        _title(d, "YOUR FAVORITE?", h * 0.04, w, 90 * u)
        s = _out_back(t / 0.8)
        for i, (c, cx) in enumerate(((a, w * 0.27), (b, w * 0.73))):
            glow = 1 + 0.08 * math.sin(2 * math.pi * (t * 1.0 + i * 0.5))
            _vs_swatch(d, c, cx, h * 0.28, w * 0.17 * s * glow, h * 0.085 * s * glow, u, shadow)
            if t > 0.4:
                d.text((cx, h * 0.28 + h * 0.085 + 18 * u), c["label"].upper(), font=cm._fit(d, c["label"].upper(), w * 0.4, 50 * u), fill=INK, anchor="mt")
        r = 44 * u * _out_back(_clamp((t - 0.3) / 0.5))
        if r > 3:
            d.ellipse([w / 2 - r, h * 0.28 - r, w / 2 + r, h * 0.28 + r], fill=(226, 70, 70), outline=INK, width=max(3, int(6 * u)))
            if r > 26 * u:
                d.text((w / 2, h * 0.28), "OR", font=_font(r * 0.75), fill=(255, 255, 255), anchor="mm", stroke_width=max(2, int(3 * u)), stroke_fill=INK)
        if t > 1.2:
            _center(d, "COMMENT YOUR PICK", h * 0.425, w, 52 * u * (1 + 0.04 * math.sin(t * 6)), INK)
    else:  # paint / screen / diff memakai gambar perbandingan yang sudah ada; latar sudah berkedip
        p = min(1.0, t / (3.8 if kind == "diff" else 1.4))
        aa = dict(a, _diff_lines=diff_lines)
        return colorvs._scene(kind, aa, b, w, h, p, suggest, _with_layer(img), shadow, mid)
    return img


def _with_layer(img):
    return img


def vs_render(kind, a, b, outdir, w, h, dur, suggest=None, diff_lines=None, fps=FPS) -> str:
    from . import colorvs
    os.makedirs(outdir, exist_ok=True)
    mid = colorvs._mid(a, b)
    base, shadow = cm._kid_base(mid, w, h)
    n = max(2, int(math.ceil(dur * fps)) + 1)
    for i in range(n):
        vs_frame(kind, a, b, w, h, i / fps, dur, suggest, base, shadow, mid, diff_lines or []).save(
            os.path.join(outdir, f"f_{i:04d}.png"), compress_level=1)
    return os.path.join(outdir, "f_%04d.png")
