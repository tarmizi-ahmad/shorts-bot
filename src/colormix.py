"""Video 'komposisi warna'.

Angka dihitung oleh KODE (bukan AI). AI hanya menulis narasi dari angka itu, lalu narasinya DIVALIDASI:
kalau angka yang benar tidak muncul, kalimat diganti templat bawaan. Visual digambar dengan Pillow.
"""
import colorsys
import math
import re

from PIL import Image, ImageColor, ImageDraw, ImageFont

from . import script_gen

FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Warna populer (juga antrean otomatis bila kolom warna kosong). Hex dipilih agar hasil campurannya masuk akal.
FRIENDLY = {
    "orange": "#FF8000", "green": "#00FF00", "purple": "#A000FF", "pink": "#FF8FB0", "brown": "#8B5A2B",
    "teal": "#008080", "turquoise": "#30D5C8", "magenta": "#FF00AA", "lime": "#80FF00", "violet": "#8F00FF",
    "peach": "#FFCBA4", "mint": "#98E8C0", "lavender": "#C8A8E8", "coral": "#FF7060", "olive": "#808000",
    "gold": "#E6B800", "maroon": "#800000", "navy": "#000080", "beige": "#E8D8B0", "cyan": "#00FFFF",
}
POPULAR = list(FRIENDLY)
PREFIX = ("dark", "light", "medium", "deep", "pale", "hot", "dim")

PAINT_COL = {"red": (226, 50, 50), "yellow": (250, 210, 40), "blue": (50, 100, 230),
             "white": (240, 240, 240), "black": (40, 40, 48)}
SCREEN_COL = {"red": (255, 70, 70), "green": (60, 220, 100), "blue": (80, 140, 255)}


# ------------------------------------------------------------------ warna
def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(rgb)


def _spoken(key: str) -> str:
    for p in PREFIX:
        if key.startswith(p) and len(key) > len(p):
            return f"{p} {key[len(p):]}"
    return key


def nearest_friendly(rgb) -> str:
    def d(h):
        c = ImageColor.getrgb(h)
        return sum((a - b) ** 2 for a, b in zip(rgb, c))
    return min(FRIENDLY, key=lambda n: d(FRIENDLY[n]))


def parse_color(text: str):
    """'orange' / 'dark orange' / '#FF8800' -> (label, spoken, (r,g,b))."""
    raw = (text or "").strip()
    key = re.sub(r"[\s_-]+", "", raw.lower())
    if key in FRIENDLY:
        return key.title(), key, ImageColor.getrgb(FRIENDLY[key])
    if re.fullmatch(r"#?[0-9a-f]{6}", key):
        rgb = ImageColor.getrgb("#" + key.lstrip("#"))
        return _hex(rgb), f"this shade of {nearest_friendly(rgb)}", rgb
    try:
        rgb = ImageColor.getrgb(key)[:3]
    except ValueError:
        raise ValueError(f"Warna tidak dikenali: '{raw}'. Pakai nama Inggris (orange) atau hex (#FF8800).")
    spoken = _spoken(key)
    return spoken.title(), spoken, rgb


def requested_colors(raw: str, limit: int = 2) -> list:
    items, seen = [], set()
    for part in re.split(r"[,;\n]+", raw or ""):
        p = part.strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            items.append(p)
    if len(items) > limit:
        print(f"⚠️ {len(items)} warna diminta, dibatasi {limit} per run (batas upload YouTube). Sisanya diabaikan.")
    return items[:limit]


def topic_id(label: str) -> str:
    return "color:" + re.sub(r"[^a-z0-9#]+", "", label.lower())


def pick_next(used: set):
    for name in POPULAR:
        if topic_id(name) not in used:
            return parse_color(name)
    return None


def _rgb_to_ryb(r, g, b):
    """Gossett & Chen (2004), nilai 0..1. Perkiraan model cat tradisional merah-kuning-biru."""
    w = min(r, g, b)
    r, g, b = r - w, g - w, b - w
    mg = max(r, g, b)
    y = min(r, g)
    r, g = r - y, g - y
    if b and g:
        b, g = b / 2, g / 2
    y, b = y + g, b + g
    my = max(r, y, b)
    if my:
        n = mg / my
        r, y, b = r * n, y * n, b * n
    return r, y, b


def _round100(values: dict) -> dict:
    """Bulatkan ke bilangan bulat yang totalnya tepat 100 (largest remainder)."""
    tot = sum(values.values()) or 1
    raw = {k: v * 100 / tot for k, v in values.items()}
    out = {k: int(math.floor(v)) for k, v in raw.items()}
    left = 100 - sum(out.values())
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[:left]:
        out[k] += 1
    return out


def composition(label: str, spoken: str, rgb) -> dict:
    r, g, b = (c / 255 for c in rgb)
    w, k = min(r, g, b), 1 - max(r, g, b)
    chroma = max(r, g, b) - min(r, g, b)
    pure = 1 - w - k  # bagian "warna murni"; sisanya putih/hitam
    parts = {"red": 0.0, "yellow": 0.0, "blue": 0.0, "white": w, "black": k}
    if chroma > 0.001:
        pr, pg, pb = ((c - w) / chroma for c in (r, g, b))  # warna yang sama pada kejenuhan penuh
        ry, yy, by = _rgb_to_ryb(pr, pg, pb)
        s = (ry + yy + by) or 1
        parts["red"], parts["yellow"], parts["blue"] = (pure * v / s for v in (ry, yy, by))
    paint = _round100(parts)
    neutral = chroma <= 0.001
    keys = ["white", "black"] if neutral else ["red", "yellow", "blue"] + [x for x in ("white", "black") if paint[x] >= 5]
    return {
        "label": label, "spoken": spoken, "rgb": tuple(rgb), "hex": _hex(rgb), "neutral": neutral,
        "hue": colorsys.rgb_to_hsv(r, g, b)[0] * 360,
        "paint": paint, "paint_keys": keys,
        "screen": {"red": round(rgb[0] / 255 * 100), "green": round(rgb[1] / 255 * 100), "blue": round(rgb[2] / 255 * 100)},
    }


# ------------------------------------------------------------------ naskah
PROMPT = """You write the narration for a 40-second YouTube Short in English for a US audience.
A friendly cartoon calendar mascot named Cal explains how the color "{spoken}" ({hex}) is made.

FACTS COMPUTED BY CODE. Use EXACTLY these numbers and never change them or invent other numbers:
- Paint mixing (artist's red-yellow-blue color wheel, an estimate): {paint_line}
- Screen light (RGB): {screen_line}

Write each field as spoken sentences (short, warm, curious, easy for teens and adults, no emojis):
- "hook": max 14 words. Pull the viewer in with a surprising question about "{spoken}". No digits.
- "paint": 1-2 sentences. Say EVERY paint number above, each as digits followed by the word percent.
- "screen": 1-2 sentences. Say EVERY screen number above, each as digits followed by the word percent. Contrast it with paint.
- "fact": 1-2 sentences with ONE true, well-known fact about this color, its name, or how our eyes see it. NO digits, no dates, no numbers. If unsure, explain that our eyes use three kinds of cone cells.
- "outro": max 18 words. Ask which color to break down next and invite a comment. No digits.
- "tags": 4 short lowercase tags.

Reply with JSON only: {{"hook":"","paint":"","screen":"","fact":"","outro":"","tags":[]}}"""


def _lines(c: dict):
    paint = ", ".join(f"{c['paint'][k]}% {k}" for k in c["paint_keys"])
    screen = f"red {c['screen']['red']}%, green {c['screen']['green']}%, blue {c['screen']['blue']}%"
    return paint, screen


def _says(text: str, nums) -> bool:
    return all(re.search(rf"(?<![\d.]){n}(?![\d.])", text) for n in nums)


def _fallback(c: dict) -> dict:
    sp = c["spoken"]
    paint = ", ".join(f"{c['paint'][k]} percent {k}" for k in c["paint_keys"])
    s = c["screen"]
    return {
        "hook": f"Ever wondered what colors make {sp}? Let's break it down!",
        "paint": f"With paint, {sp} is roughly {paint}.",
        "screen": (f"On a screen it works differently: {s['red']} percent red light, "
                   f"{s['green']} percent green, and {s['blue']} percent blue."),
        "fact": "Your eyes mix these colors for you, using three kinds of color-sensing cells called cones.",
        "outro": "Which color should I break down next? Tell me in the comments!",
        "tags": ["color mixing", "color theory", "art", "science"],
    }


def _ask(prompt: str):
    for provider in (script_gen._gemini, script_gen._groq, script_gen._cloudflare_text):
        text = provider(prompt)
        if not text:
            continue
        try:
            return script_gen._parse(text)
        except Exception as e:  # noqa: BLE001
            print(f"Balasan {provider.__name__} tidak valid:", e)
    return None


def generate(c: dict) -> dict:
    fb = _fallback(c)
    paint_line, screen_line = _lines(c)
    ai = _ask(PROMPT.format(spoken=c["spoken"], hex=c["hex"], paint_line=paint_line, screen_line=screen_line)) or {}
    if not ai:
        print("⚠️ AI teks tidak tersedia: memakai narasi templat.")

    def good(key, nums=None, digits_ok=False):
        t = str(ai.get(key) or "").strip()
        if not t or len(t) > 320:
            return fb[key]
        if nums is not None and not _says(t, nums):
            print(f"⚠️ Narasi '{key}' dari AI tidak memuat angka yang benar, pakai templat.")
            return fb[key]
        if nums is None and re.search(r"\d", t):
            print(f"⚠️ Narasi '{key}' dari AI memuat angka, pakai templat.")
            return fb[key]
        return t

    paint_nums = [c["paint"][k] for k in c["paint_keys"]]
    texts = {
        "hook": good("hook"),
        "paint": good("paint", paint_nums),
        "screen": good("screen", list(c["screen"].values())),
        "fact": good("fact"),
        "outro": good("outro"),
    }
    tags = [str(t)[:30] for t in (ai.get("tags") or fb["tags"])][:6]
    title = f"What Colors Make {c['label']}? | Color Mix"[:85]
    recipe = "Paint (estimate): " + paint_line + "\nScreen (RGB): " + screen_line
    desc = (f"How is {c['label']} ({c['hex']}) made? Cal breaks down the exact mix.\n\n{recipe}\n\n"
            f"Which color should we break down next? Comment below!\n#colormixing #colortheory #art")
    return {
        "title": title, "description": desc,
        "tags": tags + ["color mixing", "color theory", c["label"].lower()],
        "scenes": [{"kind": k, "narration": texts[k], "image_prompt": ""}
                   for k in ("hook", "paint", "screen", "fact", "outro")],
    }


# ------------------------------------------------------------------ gambar
def _font(sz):
    return ImageFont.truetype(FONT_B, max(8, int(sz)))


def _fit(d, text, maxw, size):
    while size > 20 and d.textlength(text, font=_font(size)) > maxw:
        size -= 4
    return _font(size)


def _center(d, text, y, w, size, fill, maxw=None, stroke=0):
    f = _fit(d, text, maxw or w * 0.9, size)
    d.text((w / 2, y), text, font=f, fill=fill, anchor="mt", stroke_width=stroke, stroke_fill=(0, 0, 0))


def _bg(c, w, h):
    base = tuple(int(x * 0.16 + y * 0.84) for x, y in zip(c["rgb"], (20, 24, 40)))
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    top, bot = (18, 22, 36), base
    for y in range(h):
        k = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * k) for i in range(3)))
    return img


def _bars(img, c, w, h, title, sub, rows):
    d = ImageDraw.Draw(img)
    u = w / 1080
    _center(d, title, h * 0.05, w, 70 * u, (255, 255, 255))
    _center(d, sub, h * 0.05 + 84 * u, w, 38 * u, (190, 200, 220))
    cx, cy, cr = w * 0.89, h * 0.05 + 36 * u, 30 * u  # titik warna kecil di kanan judul (tidak menimpa subjudul)
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=c["rgb"], outline=(255, 255, 255), width=int(4 * u))
    n = len(rows)
    y0 = h * 0.155
    rh = min(h * 0.085, (h * 0.31) / n - h * 0.01)
    for i, (name, pct, col) in enumerate(rows):
        y = y0 + i * (rh + h * 0.012)
        d.text((w * 0.07, y + rh / 2), name.upper(), font=_font(40 * u), fill=(255, 255, 255), anchor="lm")
        x0, x1 = w * 0.30, w * 0.80
        d.rounded_rectangle([x0, y, x1, y + rh], radius=rh / 2, fill=(46, 52, 72))
        fw = max(rh, (x1 - x0) * pct / 100) if pct > 0 else 0
        if fw:
            d.rounded_rectangle([x0, y, x0 + fw, y + rh], radius=rh / 2, fill=col, outline=(255, 255, 255), width=int(3 * u))
        d.text((w * 0.82, y + rh / 2), f"{pct}%", font=_font(52 * u), fill=(255, 255, 255), anchor="lm")


def _wheel(img, c, w, h):
    d = ImageDraw.Draw(img)
    u = w / 1080
    _center(d, "DID YOU KNOW?", h * 0.05, w, 76 * u, (255, 255, 255))
    cx, cy, R = w / 2, h * 0.265, w * 0.2
    for a in range(0, 360):
        r, g, b = colorsys.hsv_to_rgb(a / 360, 1, 1)
        d.pieslice([cx - R, cy - R, cx + R, cy + R], a - 90 - 0.8, a - 90 + 0.8, fill=(int(r * 255), int(g * 255), int(b * 255)))
    r2 = R * 0.62
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=c["rgb"], outline=(255, 255, 255), width=int(6 * u))
    ang = math.radians(c["hue"] - 90)
    mx, my, mr = cx + math.cos(ang) * R * 0.81, cy + math.sin(ang) * R * 0.81, 22 * u
    if not c["neutral"]:
        d.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=c["rgb"], outline=(255, 255, 255), width=int(6 * u))
    _center(d, c["label"].upper(), cy + R + 16 * u, w, 54 * u, (255, 255, 255))


def render_scene(kind: str, c: dict, path: str, w: int, h: int, suggest=None) -> None:
    img = _bg(c, w, h)
    d = ImageDraw.Draw(img)
    u = w / 1080
    if kind == "hook":
        _center(d, "WHAT COLORS MAKE", h * 0.05, w, 56 * u, (190, 200, 220))
        _center(d, c["label"].upper(), h * 0.05 + 70 * u, w, 150 * u, (255, 255, 255), stroke=int(4 * u))
        d.rounded_rectangle([w * 0.12, h * 0.19, w * 0.88, h * 0.415], radius=int(48 * u), fill=c["rgb"],
                            outline=(255, 255, 255), width=int(8 * u))
        _center(d, c["hex"], h * 0.43, w, 46 * u, (220, 226, 240))
    elif kind == "paint":
        rows = [(k, c["paint"][k], PAINT_COL[k]) for k in c["paint_keys"]]
        _bars(img, c, w, h, "PAINT MIX", "artist's red-yellow-blue wheel (estimate)", rows)
    elif kind == "screen":
        rows = [(k, c["screen"][k], SCREEN_COL[k]) for k in ("red", "green", "blue")]
        _bars(img, c, w, h, "SCREEN LIGHT", "red-green-blue (RGB), exact", rows)
    elif kind == "fact":
        _wheel(img, c, w, h)
    else:  # outro
        _center(d, "WHICH COLOR NEXT?", h * 0.05, w, 84 * u, (255, 255, 255))
        sug = (suggest or [])[:5]
        for i, name in enumerate(sug):
            cx = w * (0.5 + (i - (len(sug) - 1) / 2) * 0.18)
            cy, r = h * 0.22, w * 0.07
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ImageColor.getrgb(FRIENDLY[name]), outline=(255, 255, 255), width=int(5 * u))
            d.text((cx, cy + r + 10 * u), name.upper(), font=_fit(d, name.upper(), w * 0.17, 30 * u), fill=(220, 226, 240), anchor="mt")
        f = _font(56 * u)
        txt = "COMMENT YOUR PICK"
        tw = d.textlength(txt, font=f)
        d.rounded_rectangle([w / 2 - tw / 2 - 36 * u, h * 0.385, w / 2 + tw / 2 + 36 * u, h * 0.385 + 92 * u],
                            radius=int(46 * u), fill=(226, 70, 70), outline=(255, 255, 255), width=int(4 * u))
        d.text((w / 2, h * 0.385 + 46 * u), txt, font=f, fill=(255, 255, 255), anchor="mm")
    img.save(path)


def suggestions(current_label: str, used: set) -> list:
    cur = current_label.lower()
    out = [n for n in POPULAR if n != cur and topic_id(n) not in used]
    return (out + [n for n in POPULAR if n != cur and n not in out])[:5]
