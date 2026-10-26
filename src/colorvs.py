"""Video 'A vs B': perbedaan dua warna (mis. banana vs lemon). Semua angka dihitung kode, narasi dari templat."""
import math
import os
import re

from PIL import Image, ImageDraw

from . import colormix as cm
from .colormix import INK, _center, _clamp, _confetti, _fit, _font, _out_back, _out_cubic, _rr, _star, _title

SPLIT = re.compile(r"\s+(?:vs\.?|versus)\s+", re.I)
ING = ("red", "yellow", "blue", "white", "black")
ING_COL = {**cm.PAINT_COL}
SCR = ("red", "green", "blue")


def is_versus(item: str) -> bool:
    return bool(SPLIT.search(item or ""))


def split_item(item: str) -> tuple:
    parts = SPLIT.split(item.strip())
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise ValueError(f"Format perbandingan salah: '{item}'. Contoh: banana vs lemon")
    return parts[0].strip(), parts[1].strip()


def topic_id(a: dict, b: dict) -> str:
    x, y = sorted([cm.topic_id(a["label"])[6:], cm.topic_id(b["label"])[6:]])
    return f"color:{x}-vs-{y}"


def build(item: str) -> tuple:
    na, nb = split_item(item)
    pa, pb = cm.parse_color(na), cm.parse_color(nb)
    a, b = cm.composition(*pa), cm.composition(*pb)
    if a["rgb"] == b["rgb"]:
        raise ValueError(f"'{na}' dan '{nb}' adalah warna yang sama persis.")
    return a, b


def _lum(c):
    r, g, bl = c["rgb"]
    return (0.2126 * r + 0.7152 * g + 0.0722 * bl) / 255


def _phrase(c: dict) -> str:
    base = [f"{c['paint'][k]} percent {k}" for k in ING if k in c["paint_keys"] and c["paint"][k] > 0]
    return " and ".join(base) if len(base) < 3 else ", ".join(base[:-1]) + f", and {base[-1]}"


def diffs(a: dict, b: dict) -> list:
    """[(teks tampilan, teks narasi)] maksimal 3 butir perbedaan nyata."""
    out = []
    la, lb = _lum(a), _lum(b)
    if abs(la - lb) >= 0.03:
        hi, lo = (a, b) if la > lb else (b, a)
        out.append((f"{hi['label'].upper()} IS LIGHTER", f"{hi['label']} is lighter than {lo['label']}."))
    rows = sorted(((a["paint"][k] - b["paint"][k], k) for k in ING if abs(a["paint"][k] - b["paint"][k]) >= 8),
                  key=lambda t: -abs(t[0]))
    for d, k in rows[:2]:
        w, o = (a, b) if d > 0 else (b, a)
        out.append((f"{w['label'].upper()}: MORE {k.upper()}",
                    f"{w['label']} has {abs(d)} percent more {k} paint than {o['label']}."))
    sa, sb = a["screen"], b["screen"]
    if not out:
        k = max(SCR, key=lambda k: abs(sa[k] - sb[k]))
        if abs(sa[k] - sb[k]) >= 3:
            w, o = (a, b) if sa[k] > sb[k] else (b, a)
            out.append((f"{w['label'].upper()}: MORE {k.upper()} LIGHT",
                        f"On a screen, {w['label']} has {abs(sa[k] - sb[k])} percent more {k} light."))
    if not out:
        out.append(("ALMOST TWINS!", "They are almost twins! Only tiny differences."))
    return out[:3]


def generate(a: dict, b: dict) -> dict:
    A, B = a["label"], b["label"]
    sa, sb = a["screen"], b["screen"]
    ds = diffs(a, b)
    texts = {
        "hook": f"{A} or {B}? They look so close! Let's find the difference.",
        "paint": f"With paint, {A} is {_phrase(a)}. And {B} is {_phrase(b)}.",
        "screen": (f"On a screen, {A} uses {sa['red']} percent red light, {sa['green']} green, and {sa['blue']} blue. "
                   f"{B} uses {sb['red']}, {sb['green']}, and {sb['blue']}."),
        "diff": "The big difference: " + " ".join(t for _, t in ds),
        "outro": "Which two colors should we compare next? Comment your pick!",
    }
    def short(c):
        return ", ".join(f"{c['paint'][k]}% {k}" for k in ING if k in c["paint_keys"] and c["paint"][k] > 0)
    sc = lambda c: f"red {c['screen']['red']}%, green {c['screen']['green']}%, blue {c['screen']['blue']}%"
    title = f"{A} vs {B}: What's the Difference? \U0001F3A8 #shorts"[:100]
    desc = (
        f"{A} vs {B}: what is the difference?\n\n"
        f"\U0001F3A8 {A.upper()} ({a['hex']})\nPaint (estimate): {short(a)}\nScreen (RGB): {sc(a)}\n\n"
        f"\U0001F3A8 {B.upper()} ({b['hex']})\nPaint (estimate): {short(b)}\nScreen (RGB): {sc(b)}\n\n"
        f"THE DIFFERENCE\n" + "\n".join(f"- {t}" for _, t in ds) + "\n\n"
        f"Which two colors should we compare next? Comment below!\n\n"
        f"#shorts #colormixing #learncolors #{re.sub(r'[^a-z0-9]', '', A.lower())} #{re.sub(r'[^a-z0-9]', '', B.lower())}"
    )
    return {
        "title": title, "description": desc,
        "tags": [A.lower(), B.lower(), f"{A.lower()} vs {B.lower()}", "color mixing", "learn colors", "color difference"],
        "scenes": [{"kind": k, "narration": texts[k], "image_prompt": ""} for k in ("hook", "paint", "screen", "diff", "outro")],
        "_diff_lines": [d for d, _ in ds],
    }


def _mid(a, b) -> dict:
    return {"rgb": cm._mix(a["rgb"], b["rgb"], 0.5), "label": a["label"] + b["label"], "neutral": True, "hue": 0}


def _panel(d, box, c, keys, vals, colmap, p, u, shadow):
    x0, y0, x1, y1 = box
    sw = 46 * u
    d.ellipse([x0 + 4 * u, y0 + 6 * u, x0 + 4 * u + sw, y0 + 6 * u + sw], fill=c["rgb"], outline=INK, width=max(2, int(4 * u)))
    f = _fit(d, c["label"].upper(), (x1 - x0) - sw - 14 * u, 40 * u)
    d.text((x0 + sw + 14 * u, y0 + 6 * u + sw / 2), c["label"].upper(), font=f, fill=INK, anchor="lm")
    base_y, top_y = y1 - 46 * u, y0 + 120 * u
    slot = (x1 - x0) / len(keys)
    for i, k in enumerate(keys):
        q = _out_cubic(_clamp((p - i * 0.08) / 0.6))
        cx = x0 + slot * (i + 0.5)
        bw = slot * 0.62
        pct = vals[k]
        hh = max(4 * u, (base_y - top_y) * pct / 100 * q)
        _rr(d, [cx - bw / 2, base_y - hh, cx + bw / 2, base_y], 10 * u, fill=colmap[k], outline=INK, width=max(2, int(4 * u)))
        d.text((cx, base_y - hh - 8 * u), f"{int(round(pct * q))}%", font=_fit(d, "100%", slot * 0.95, 34 * u), fill=INK, anchor="ms")
        d.text((cx, base_y + 8 * u), k.upper(), font=_fit(d, "YELLOW", slot * 0.98, 22 * u), fill=INK, anchor="mt")


def _scene(kind, a, b, w, h, p, suggest, base, shadow, mid):
    img = base.copy()
    d = ImageDraw.Draw(img)
    u = w / 1080
    _confetti(d, mid["label"] + kind, w, h, p)
    if kind == "hook":
        _title(d, "WHAT'S THE", h * 0.04, w, 90 * u)
        _title(d, "DIFFERENCE?", h * 0.04 + 100 * u, w, 120 * u)
        s = _out_back(p)
        for c, cx in ((a, w * 0.27), (b, w * 0.73)):
            bw, bh = w * 0.21 * s, h * 0.09 * s
            cy = h * 0.31
            if bw > 4:
                off = 12 * u
                _rr(d, [cx - bw + off, cy - bh + off, cx + bw + off, cy + bh + off], 44 * u, fill=shadow)
                _rr(d, [cx - bw, cy - bh, cx + bw, cy + bh], 44 * u, fill=c["rgb"], outline=INK, width=max(3, int(9 * u)))
            if p > 0.35:
                d.text((cx, h * 0.31 + h * 0.09 + 18 * u), c["label"].upper(), font=_fit(d, c["label"].upper(), w * 0.4, 52 * u),
                       fill=INK, anchor="mt")
        r = 52 * u * _out_back(_clamp((p - 0.2) / 0.5))
        if r > 3:
            d.ellipse([w / 2 - r, h * 0.31 - r, w / 2 + r, h * 0.31 + r], fill=(226, 70, 70), outline=INK, width=max(3, int(7 * u)))
            if r > 30 * u:
                d.text((w / 2, h * 0.31), "VS", font=_font(r * 0.8), fill=(255, 255, 255), anchor="mm", stroke_width=max(2, int(3 * u)), stroke_fill=INK)
    elif kind in ("paint", "screen"):
        title = "PAINT MIX" if kind == "paint" else "SCREEN LIGHT"
        _title(d, title, h * 0.04, w, 84 * u)
        _center(d, "who has more of what?" if kind == "paint" else "phones & TVs mix light (exact)", h * 0.04 + 96 * u, w, 36 * u, INK)
        if kind == "paint":
            keys = [k for k in ING if a["paint"][k] > 0 or b["paint"][k] > 0]
            va, vb, cmap = a["paint"], b["paint"], ING_COL
        else:
            keys = list(SCR)
            va, vb, cmap = a["screen"], b["screen"], cm.SCREEN_COL
        box = [w * 0.04, h * 0.155, w * 0.96, h * 0.455]
        cm._card(d, box, shadow, u)
        mx = w / 2
        d.line([(mx, box[1] + 24 * u), (mx, box[3] - 24 * u)], fill=INK, width=max(2, int(4 * u)))
        _panel(d, [box[0] + 24 * u, box[1] + 18 * u, mx - 14 * u, box[3] - 14 * u], a, keys, va, cmap, p, u, shadow)
        _panel(d, [mx + 14 * u, box[1] + 18 * u, box[2] - 24 * u, box[3] - 14 * u], b, keys, vb, cmap, p, u, shadow)
    elif kind == "diff":
        _title(d, "THE DIFFERENCE", h * 0.04, w, 90 * u)
        lines = a.get("_diff_lines") or []
        box = [w * 0.05, h * 0.155, w * 0.95, h * 0.45]
        cm._card(d, box, shadow, u)
        for i, t in enumerate(lines):
            q = _clamp((p - i * 0.2) / 0.4)
            if q > 0:
                y = box[1] + 70 * u + i * 120 * u + (1 - _out_cubic(q)) * 30 * u
                _center(d, t, y, w, 52 * u, INK, maxw=w * 0.84)
        d.text((w * 0.27, box[3] - 40 * u), a["hex"], font=_font(34 * u), fill=INK, anchor="mm")
        d.text((w * 0.73, box[3] - 40 * u), b["hex"], font=_font(34 * u), fill=INK, anchor="mm")
    else:
        return cm._kid_scene("outro", mid, w, h, p, suggest, base, shadow).copy()
    return img


def render(kind: str, a: dict, b: dict, outdir: str, w: int, h: int, suggest=None, n: int = cm.FRAMES, diff_lines=None) -> str:
    os.makedirs(outdir, exist_ok=True)
    mid = _mid(a, b)
    base, shadow = cm._kid_base(mid, w, h)
    a = dict(a, _diff_lines=diff_lines or [])
    for i in range(n):
        _scene(kind, a, b, w, h, i / (n - 1), suggest, base, shadow, mid).save(os.path.join(outdir, f"f_{i:03d}.png"), compress_level=1)
    return os.path.join(outdir, "f_%03d.png")
