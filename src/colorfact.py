"""Mode color_fact: video fakta menarik tentang tema warna (mis. 'buta warna'). Tema diisi saat menjalankan workflow.
Alur: tema -> kata kunci Inggris -> teks sumber Wikipedia -> AI menulis naskah HANYA dari sumber -> angka divalidasi -> animasi."""
import math
import os
import re

import requests
from PIL import Image, ImageDraw

from . import colorlong as CL
from . import colormix as cm
from .colormix import CONFETTI, INK, _center, _clamp, _font, _mix, _out_back, _out_cubic, _rr, _title

HEADERS = {"User-Agent": "shorts-bot/1.0 (educational project)"}
WIKI = "https://en.wikipedia.org/w/api.php"
MAX_SOURCE = 6000


# Antrean tema otomatis (label tampilan, judul artikel Wikipedia). Urutan = prioritas. Dipakai bila kolom tema kosong.
THEMES = [
    ("Color Blindness", "Color blindness"), ("Why the Sky Is Blue", "Rayleigh scattering"), ("How Rainbows Form", "Rainbow"),
    ("Color Psychology", "Color psychology"), ("Tetrachromacy", "Tetrachromacy"), ("Structural Colors in Nature", "Structural coloration"),
    ("Tyrian Purple", "Tyrian purple"), ("Vantablack", "Vantablack"), ("The Dress Illusion", "The dress"),
    ("Mantis Shrimp Vision", "Mantis shrimp"), ("Synesthesia", "Synesthesia"), ("Why Sunsets Are Red", "Sunset"),
    ("Aurora Colors", "Aurora"), ("Why Leaves Are Green", "Chlorophyll"), ("Ultramarine", "Ultramarine"),
    ("Egyptian Blue", "Egyptian blue"), ("Cochineal Red", "Cochineal"), ("Mauveine", "Mauveine"),
    ("Scheele's Green", "Scheele's Green"), ("Primary Colors", "Primary color"), ("The Color Wheel", "Color wheel"),
    ("RGB Colors", "RGB color model"), ("CMYK Printing", "CMYK color model"), ("Pantone Colors", "Pantone"),
    ("The Color Red", "Red"), ("The Color Blue", "Blue"), ("The Color Yellow", "Yellow"), ("The Color Green", "Green"),
    ("The Color Purple", "Purple"), ("The Color Pink", "Pink"), ("The Color Black", "Black"), ("The Color White", "White"),
    ("False Color Images", "False color"), ("Color Temperature", "Color temperature"), ("Checker Shadow Illusion", "Checker shadow illusion"),
    ("The Ishihara Test", "Ishihara test"), ("How We See Color", "Color vision"), ("Cone Cells", "Cone cell"),
    ("Color Symbolism", "Color symbolism"), ("The Visible Spectrum", "Visible spectrum"),
]


def topic_for(query: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:50] or "theme"
    return f"fact:{slug}"


def pick_auto(used: set, taken: set):
    """Tema otomatis berikutnya yang belum pernah dibuat (db) dan belum dicoba di run ini."""
    for label, query in THEMES:
        tid = topic_for(query)
        if tid not in used and tid not in taken:
            return label, query
    return None


# ------------------------------------------------------------------ sumber
def split_themes(raw: str) -> list:
    """Tema dipisah titik koma, garis tegak, atau baris baru (koma boleh ada di dalam tema)."""
    out, seen = [], set()
    for p in re.split(r"[;|\n]+", raw or ""):
        p = p.strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


class ThemeRejected(ValueError):
    """Tema ditolak karena bukan tentang warna atau artikel sumbernya tidak cocok."""


COLOR_WORDS = re.compile(r"colou?r|hue|pigment|wavelength|spectrum|rainbow|light|vision|paint|dye|"
                         r"\b(?:red|green|blue|yellow|orange|purple|violet|pink|black|white|brown)\b", re.I)


def english_query(theme: str) -> dict:
    """Terjemah tema ke kata kunci Inggris untuk Wikipedia, label tampilan singkat, dan penilaian relevansi."""
    ai = cm._ask(
        'You help a channel that only makes videos about COLOR (color science, color vision, color theory, color in art, '
        'nature, culture, psychology, history of colors and pigments).\n'
        f'Theme: "{theme}" (may be Indonesian)\n'
        'Reply with JSON only: {"query": "<English Wikipedia search query, 1-4 words>", '
        '"label": "<display label, 1-3 words, Title Case>", '
        '"about_color": <true if the theme is really about color, otherwise false>}'
    ) or {}
    q = str(ai.get("query") or theme).strip()[:80]
    lab = str(ai.get("label") or q).strip()[:40]
    flag = ai.get("about_color")
    if isinstance(flag, str):
        flag = flag.strip().lower() in ("true", "yes", "1")
    return {"query": q, "label": lab, "about_color": flag if isinstance(flag, bool) else None}


def wiki_source(query: str) -> tuple:
    """(judul artikel, teks) dari Wikipedia Inggris, atau ('', '') bila gagal."""
    try:
        r = requests.get(WIKI, headers=HEADERS, timeout=30, params={
            "action": "query", "list": "search", "srsearch": query, "srlimit": 5, "format": "json"})
        r.raise_for_status()
        hits = [x for x in r.json()["query"]["search"]
                if "disambiguation" not in x["title"].lower() and "may refer to" not in x.get("snippet", "").lower()]
        if not hits:
            return "", ""
        title = hits[0]["title"]
        r = requests.get(WIKI, headers=HEADERS, timeout=30, params={
            "action": "query", "prop": "extracts", "explaintext": 1, "exlimit": 1, "redirects": 1,
            "titles": title, "format": "json"})
        r.raise_for_status()
        page = next(iter(r.json()["query"]["pages"].values()))
        text = re.sub(r"\n{2,}", "\n", page.get("extract") or "").strip()
        return title, text[:MAX_SOURCE]
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Wikipedia tidak terjangkau: {str(e)[:120]}")
        return "", ""


# ------------------------------------------------------------------ naskah
PROMPT = """You write narration for a 9:16 YouTube Short of surprising, true facts about a color-related theme.
THEME: {theme}
AUDIENCE: curious teens and adults. Spoken, vivid, simple English. Short sentences. Each fact stands alone and makes people think "wow".

SOURCE TEXT (the ONLY place you may take facts from{empty_note}):
\"\"\"
{source}
\"\"\"

RULES
- Use ONLY facts stated in SOURCE TEXT. If a fact is uncertain or debated, hedge it ("scientists think...").
- Write every statistic or count as DIGITS and only if it appears in SOURCE TEXT. {nonum}
- No medical advice, no diagnosis, no cure claims. No URLs. No emojis.
- hook: ONE question or surprising statement, 8-16 words, does NOT give the answer away.
- Write exactly {n} facts. Each narration is {lo}-{hi} words, ends with a clear point or a small twist.
- headline: 2-4 words, the key idea of that fact (shown big on screen).
- color: a hex color (#RRGGBB) that fits the mood of that fact.
- title: a curiosity-driven YouTube title under 70 characters that contains the main keyword of the theme. Honest, no lies.
- label: the theme as a 1-3 word display label.
- tags: up to 8 short English tags.

Reply with JSON only:
{{"title": "...", "label": "...", "hook": "...", "facts": [{{"headline": "...", "narration": "...", "color": "#RRGGBB"}}], "tags": ["..."]}}"""

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_ok(text: str, source: str) -> list:
    """Angka dalam narasi yang TIDAK ada di teks sumber."""
    src = source.replace(",", "")
    bad = []
    for m in NUM.findall(text):
        n = m.replace(",", "").rstrip(".")
        if n and n not in src:
            bad.append(m)
    return bad


def _valid_fact(f: dict, source: str, lo: int, hi: int):
    nar = re.sub(r"\s+", " ", str(f.get("narration") or "")).strip()
    head = re.sub(r"\s+", " ", str(f.get("headline") or "")).strip()
    words = len(nar.split())
    if not nar or not head or words < max(8, lo - 8) or words > hi + 14 or len(head.split()) > 6:
        return None, "panjang tidak sesuai"
    if re.search(r"https?://|www\.", nar):
        return None, "memuat URL"
    bad = _numbers_ok(nar, source)
    if bad:
        return None, f"angka tidak ada di sumber: {bad}"
    col = str(f.get("color") or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", col):
        col = ""
    return {"headline": head, "narration": nar, "color": col}, ""


def generate(theme: str, n_facts: int, long_mode: bool, preset=None) -> dict:
    """preset = (label, judul artikel) dari antrean otomatis: melewati terjemahan AI dan memakai artikel itu langsung."""
    q = {"query": preset[1], "label": preset[0], "about_color": True} if preset else english_query(theme)
    if q["about_color"] is False:
        raise ThemeRejected(f"Tema '{theme}' ditolak: bukan tentang warna. Channel ini khusus fakta tentang warna "
                            "(sains warna, penglihatan warna, seni, alam, budaya, sejarah pigmen).")
    src_title, source = wiki_source(q["query"])
    print(f"ℹ️ Tema '{theme}' -> pencarian '{q['query']}' -> sumber: {src_title or '(tidak ada)'} ({len(source)} karakter)")
    if source and len(COLOR_WORDS.findall(source)) < 4:
        raise ThemeRejected(f"Artikel Wikipedia yang ditemukan ('{src_title}') tampaknya tidak membahas warna, jadi tema '{theme}' "
                            f"dihentikan agar tidak menghasilkan fakta yang salah. Coba kata kunci yang lebih spesifik, mis. '{q['label']} color'.")
    lo, hi = (22, 30) if long_mode else (18, 26)
    prompt = PROMPT.format(
        theme=f"{theme} ({q['query']})", source=source or "(empty)", n=n_facts, lo=lo, hi=hi,
        empty_note="; SOURCE is empty, so use only very well-known, uncontroversial facts" if not source else "",
        nonum="SOURCE is empty: use NO numbers at all." if not source else "")
    good, hook, ai = [], "", {}
    for attempt in range(2):
        ai = cm._ask(prompt) or {}
        facts, notes = [], []
        for f in (ai.get("facts") or []):
            if not isinstance(f, dict):
                continue
            ok, why = _valid_fact(f, source, lo, hi)
            if ok:
                facts.append(ok)
            else:
                notes.append(why)
        if notes:
            print(f"⚠️ {len(notes)} fakta dibuang oleh validator: {notes[:3]}")
        if len(facts) > len(good):
            good, hook = facts, str(ai.get("hook") or "").strip()
        if len(good) >= n_facts:
            break
        if attempt == 0:
            prompt += f"\n\nIMPORTANT: your last answer had {len(facts)} valid facts. Return exactly {n_facts}, using only numbers present in SOURCE TEXT."
    if len(good) < 2:
        raise RuntimeError("AI tidak menghasilkan cukup fakta yang lolos validasi (butuh minimal 2). Coba tema lain atau jalankan ulang.")
    good = good[:n_facts]
    if not hook or len(hook.split()) > 22 or re.search(r"\d", hook) and _numbers_ok(hook, source):
        hook = f"What do you really know about {q['label'].lower()}?"
    label = (str(ai.get("label") or q["label"]).strip() or q["label"])[:40]
    for i, f in enumerate(good):
        f["color"] = f["color"] or "#%02X%02X%02X" % CONFETTI[i % len(CONFETTI)]
    title = re.sub(r"\s+", " ", str(ai.get("title") or "")).replace("#", "").strip()
    if not title or len(title) > 80:
        title = f"{label}: Facts You Didn't Know"
    tags = [str(t).strip()[:30] for t in (ai.get("tags") or []) if str(t).strip()][:8]
    outro = ("Did you learn something new? Tap like, subscribe for more color facts, "
             "and comment which color topic we should explore next!") if long_mode else \
            "Like, subscribe, and comment which color topic we should explore next!"
    credit = f"Source: Wikipedia - {src_title} (CC BY-SA 4.0)\n\n" if src_title else ""
    desc = (f"{title}\n\n" + "\n".join(f"- {f['headline'].title()}" for f in good) + "\n\n"
            f"Which color topic should we explore next? Comment below!\nSubscribe for more color facts.\n\n{credit}"
            f"#shorts #colorfacts #{re.sub(r'[^a-z0-9]', '', label.lower())} #didyouknow #learnsomethingnew")
    scenes = [{"kind": "hook", "narration": hook, "headline": label, "color": good[0]["color"]}]
    for i, f in enumerate(good):
        scenes.append({"kind": "fact", "idx": i, "n": len(good), "headline": f["headline"], "narration": f["narration"], "color": f["color"]})
    scenes.append({"kind": "cta", "narration": outro, "headline": "", "color": good[-1]["color"]})
    return {
        "title": title[:90], "description": desc,
        "tags": tags + ["color facts", "did you know", label.lower()],
        "scenes": scenes, "topic_id": topic_for(q["query"]), "label": label, "source": src_title,
    }


# ------------------------------------------------------------------ animasi
def _wrap(d, text: str, size: float, maxw: float, max_lines: int):
    words = text.split()
    while size >= 36:
        f = _font(size)
        lines, cur = [], ""
        for wd in words:
            t = (cur + " " + wd).strip()
            if d.textlength(t, font=f) <= maxw:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = wd
        lines.append(cur)
        if len(lines) <= max_lines and all(d.textlength(x, font=f) <= maxw for x in lines):
            return f, lines
        size -= 4
    return _font(36), lines[:max_lines]


def _rgb(hexcol: str):
    return tuple(int(hexcol[i:i + 2], 16) for i in (1, 3, 5))


def _mid(sc: dict) -> dict:
    rgb = _rgb(sc["color"])
    return {"rgb": rgb, "label": sc.get("headline") or "fact", "neutral": True, "hue": 0}


def frame(sc: dict, theme_label: str, w: int, h: int, t: float, dur: float, base, shadow):
    u = w / 1080
    mid = _mid(sc)
    if sc["kind"] == "cta":
        return CL.frame("cta", mid, w, h, t, dur, None, base, shadow)
    img = base.copy()
    d = ImageDraw.Draw(img)
    acc = mid["rgb"]
    CL._sparkle(d, theme_label + sc["kind"] + str(sc.get("idx", "")), w, h, t)
    if sc["kind"] == "hook":
        _center(d, "COLOR FACTS", h * 0.04, w, 56 * u, INK)
        f, lines = _wrap(d, theme_label.upper(), 130 * u, w * 0.86, 2)
        y = h * 0.04 + 66 * u
        for ln in lines:
            d.text((w / 2, y), ln, font=f, fill=(255, 255, 255), anchor="mt", stroke_width=max(3, int(f.size * 0.09)), stroke_fill=INK)
            y += f.size * 1.1
        cx, cy = w / 2, max(h * 0.33, y + w * 0.17)
        for k in range(4, 0, -1):  # cincin warna berdenyut
            pulse = 1 + 0.07 * math.sin(2 * math.pi * (t * 0.9 - k * 0.12))
            R = w * (0.05 + 0.045 * k) * pulse * _out_back((t - 0.1 * (4 - k)) / 0.7)
            if R > 3:
                d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=CONFETTI[k % 6] if k % 2 else _mix(acc, (255, 255, 255), 0.4),
                          outline=INK, width=max(3, int(6 * u)))
        r0 = w * 0.07 * _out_back(t / 0.6)
        if r0 > 3:
            d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0], fill=acc, outline=INK, width=max(3, int(7 * u)))
            d.text((cx, cy), "?", font=_font(r0 * 1.3), fill=(255, 255, 255), anchor="mm", stroke_width=max(2, int(4 * u)), stroke_fill=INK)
    else:  # fact
        # gumpalan warna yang mengorbit di belakang kartu
        for j in range(3):
            a = 2 * math.pi * (t * 0.12 + j / 3)
            bx = w / 2 + math.cos(a) * w * 0.42
            by = h * 0.27 + math.sin(a * 1.3) * h * 0.1
            R = w * (0.11 + 0.02 * j)
            d.ellipse([bx - R, by - R, bx + R, by + R], fill=_mix(acc, (255, 255, 255), 0.35 + 0.15 * j), outline=INK, width=max(3, int(5 * u)))
        label = f"FACT {sc['idx'] + 1}"
        s = _out_back(t / 0.6)
        f = _font(54 * u * max(s, 0.01))
        tw = d.textlength(label, font=f)
        py = h * 0.04
        if s > 0.1:
            _rr(d, [w / 2 - tw / 2 - 34 * u + 6 * u, py + 6 * u, w / 2 + tw / 2 + 34 * u + 6 * u, py + 86 * u + 6 * u], 43 * u, fill=shadow)
            _rr(d, [w / 2 - tw / 2 - 34 * u, py, w / 2 + tw / 2 + 34 * u, py + 86 * u], 43 * u, fill=_mix(acc, INK, 0.25), outline=INK, width=max(3, int(6 * u)))
            d.text((w / 2, py + 43 * u), label, font=f, fill=(255, 255, 255), anchor="mm")
        box = [w * 0.07, h * 0.125, w * 0.93, h * 0.425]
        cm._card(d, box, shadow, u)
        f, lines = _wrap(d, sc["headline"].upper(), 108 * u, (box[2] - box[0]) * 0.86, 3)
        lh = f.size * 1.18
        y0 = (box[1] + box[3]) / 2 - lh * len(lines) / 2 - 18 * u
        for i, ln in enumerate(lines):
            q = _out_cubic(_clamp((t - 0.35 - i * 0.18) / 0.5))
            if q > 0:
                d.text((w / 2, y0 + i * lh + (1 - q) * 40 * u), ln, font=f, fill=_mix(acc, INK, 0.55), anchor="mt")
        for k in range(7):  # titik warna yang bergelombang di dasar kartu
            bob = math.sin(2 * math.pi * (t * 0.9 - k / 7)) * 9 * u
            cx = w / 2 + (k - 3) * w * 0.075
            d.ellipse([cx - 14 * u, box[3] - 40 * u + bob - 14 * u, cx + 14 * u, box[3] - 40 * u + bob + 14 * u], fill=CONFETTI[k % 6], outline=INK, width=max(2, int(3 * u)))
        n = sc["n"]  # penanda posisi fakta
        for k in range(n):
            r = (15 if k == sc["idx"] else 10) * u
            cx = w / 2 + (k - (n - 1) / 2) * 42 * u
            d.ellipse([cx - r, h * 0.447 - r, cx + r, h * 0.447 + r], fill=acc if k == sc["idx"] else (255, 255, 255), outline=INK, width=max(2, int(4 * u)))
    return img


def render(sc: dict, theme_label: str, outdir: str, w: int, h: int, dur: float, fps: int = CL.FPS) -> str:
    os.makedirs(outdir, exist_ok=True)
    base, shadow = cm._kid_base(_mid(sc), w, h)
    n = max(2, int(math.ceil(dur * fps)) + 1)
    for i in range(n):
        frame(sc, theme_label, w, h, i / fps, dur, base, shadow).save(os.path.join(outdir, f"f_{i:04d}.png"), compress_level=1)
    return os.path.join(outdir, "f_%04d.png")
