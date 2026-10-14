"""Maskot 'Cal' (kalender hidup). Digambar dengan kode, jadi SELALU sama persis.

Era hanya mengubah aksesori (topi, mahkota, dll). Mulut & kedip dibuat sebagai
'tambalan' wajah yang ditumpuk FFmpeg, mulut mengikuti kenyaringan suara narasi.
"""
import array
import math
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

S = 3  # supersampling biar halus
W, H = 600, 800
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

INK = (40, 32, 44)
RED = (226, 70, 70)
PAGE = (255, 250, 240)
GOLD = (240, 190, 60)

ERAS = ["ancient", "medieval", "1800s", "1920s", "1980s", "modern"]
FACE_BOX = (170, 375, 430, 555)  # area wajah (koordinat sprite 600x800) untuk tambalan
SCALE = 0.85  # sprite akhir 510x680


def era_for_year(year) -> str:
    try:
        y = int(year)
    except (TypeError, ValueError):
        return "modern"
    if y < 476:
        return "ancient"
    if y < 1500:
        return "medieval"
    if y < 1900:
        return "1800s"
    if y < 1950:
        return "1920s"
    if y < 1990:
        return "1980s"
    return "modern"


def short_label(date_label: str) -> str:
    """'Oct 13, 1492' -> 'OCT 13'."""
    return (date_label or "").split(",")[0].strip().upper() or "TODAY"


def sc(v):
    return [int(x * S) for x in v] if isinstance(v, (list, tuple)) else int(v * S)


def font(sz):
    return ImageFont.truetype(FONT_B, int(sz * S))


class Cal:
    def __init__(self, date_label="OCT 13", mouth_open=False, blink=False, era="modern", bounce=0):
        self.d = date_label
        self.open = mouth_open
        self.blink = blink
        self.era = era
        self.dy = bounce
        self.im = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        self.g = ImageDraw.Draw(self.im)

    # --- primitif ---
    def rr(self, box, r, fill, outline=INK, w=6):
        b = [box[0], box[1] + self.dy, box[2], box[3] + self.dy]
        self.g.rounded_rectangle(sc(b), radius=sc(r), fill=fill, outline=outline, width=sc(w))

    def el(self, box, fill, outline=INK, w=6):
        b = [box[0], box[1] + self.dy, box[2], box[3] + self.dy]
        self.g.ellipse(sc(b), fill=fill, outline=outline, width=sc(w))

    def pg(self, pts, fill, outline=INK, w=6):
        p = [(x, y + self.dy) for x, y in pts]
        self.g.polygon(sc([c for q in p for c in q]), fill=fill)
        self.g.line(sc([c for q in p + [p[0]] for c in q]), fill=outline, width=sc(w), joint="curve")

    def ln(self, pts, fill=INK, w=6):
        p = [(x, y + self.dy) for x, y in pts]
        self.g.line(sc([c for q in p for c in q]), fill=fill, width=sc(w), joint="curve")

    # --- bagian tubuh ---
    def legs(self):
        for x in (230, 370):
            self.ln([(x, 610), (x, 700)], INK, 22)
            self.el([x - 38, 690, x + 38, 740], (70, 60, 90))

    def arms(self):
        self.ln([(158, 470), (92, 540)], INK, 26)
        self.ln([(442, 470), (508, 540)], INK, 26)
        self.el([68, 520, 116, 568], PAGE)
        self.el([484, 520, 532, 568], PAGE)

    def body(self):
        self.rr([150, 215, 450, 625], 44, PAGE)
        self.g.rounded_rectangle(sc([150, 215 + self.dy, 450, 305 + self.dy]), radius=sc(44), fill=RED, outline=INK, width=sc(6))
        self.g.rectangle(sc([153, 260 + self.dy, 447, 305 + self.dy]), fill=RED)
        self.ln([(150, 305), (450, 305)], INK, 6)
        for x in (220, 380):
            self.rr([x - 11, 188, x + 11, 240], 10, (200, 200, 210))
        f = font(46)
        tw = self.g.textlength(self.d, font=f) / S
        self.g.text(sc([300 - tw / 2, 232 + self.dy]), self.d, font=f, fill=(255, 255, 255))

    def face(self):
        for cx in (240, 360):
            if self.blink:
                self.ln([(cx - 26, 420), (cx + 26, 420)], INK, 8)
            else:
                self.el([cx - 30, 385, cx + 30, 455], (255, 255, 255))
                self.el([cx - 14, 405, cx + 16, 445], INK, INK, 1)
                self.el([cx - 6, 410, cx + 6, 422], (255, 255, 255), (255, 255, 255), 1)
        for cx in (200, 400):
            self.g.ellipse(sc([cx - 24, 470 + self.dy, cx + 24, 498 + self.dy]), fill=(255, 170, 170))
        if self.open:
            self.el([265, 485, 335, 545], (90, 30, 45))
            self.el([280, 518, 320, 543], (240, 110, 120), (240, 110, 120), 1)
        else:
            self.g.arc(sc([265, 480 + self.dy, 335, 530 + self.dy]), 20, 160, fill=INK, width=sc(8))

    # --- aksesori era ---
    def era_back(self):
        if self.era == "medieval":
            self.pg([(130, 330), (470, 330), (520, 660), (80, 660)], (150, 40, 60))

    def era_front(self):
        e = self.era
        if e == "ancient":
            self.pg([(150, 565), (300, 548), (450, 565), (450, 625), (150, 625)], (250, 244, 225), INK, 5)
            self.ln([(150, 565), (450, 565)], (150, 40, 60), 10)
            self.el([140, 535, 184, 579], GOLD)
            for i in range(9):
                a = math.radians(195 + i * 18.75)
                cx, cy = 300 + 142 * math.cos(a), 262 + 52 * math.sin(a)
                self.el([cx - 24, cy - 11, cx + 24, cy + 11], (90, 160, 80), INK, 4)
        elif e == "medieval":
            self.pg([(190, 205), (190, 150), (230, 180), (260, 135), (300, 180), (340, 135), (370, 180), (410, 150), (410, 205)], GOLD)
            self.el([282, 160, 318, 196], (220, 60, 80), INK, 4)
            self.rr([150, 600, 450, 625], 6, (150, 40, 60), INK, 5)
        elif e == "1800s":
            self.rr([185, 205, 415, 230], 8, (35, 30, 40))
            self.rr([220, 90, 380, 215], 10, (35, 30, 40))
            self.rr([220, 170, 380, 190], 2, (150, 40, 60), INK, 3)
            self.pg([(270, 560), (330, 560), (300, 575)], (150, 40, 60))
            self.pg([(330, 560), (390, 530), (390, 590)], (150, 40, 60))
            self.pg([(210, 530), (270, 560), (210, 590)], (150, 40, 60))
            self.el([285, 548, 315, 578], (120, 30, 45), INK, 4)
        elif e == "1920s":
            self.rr([200, 160, 400, 215], 20, (120, 120, 130))
            self.rr([200, 190, 400, 208], 2, (40, 40, 50), INK, 3)
            self.el([160, 195, 440, 225], (120, 120, 130))
            for x in (220, 380):
                self.ln([(x, 305), (x, 625)], (60, 60, 80), 12)
            self.pg([(285, 560), (315, 560), (322, 620), (300, 635), (278, 620)], (200, 60, 70))
        elif e == "1980s":
            self.rr([146, 188, 454, 214], 10, (255, 90, 180))
            self.rr([146, 200, 454, 208], 3, (60, 220, 230), INK, 2)
            self.rr([188, 392, 292, 450], 16, (30, 30, 50))
            self.rr([308, 392, 412, 450], 16, (30, 30, 50))
            self.ln([(292, 410), (308, 410)], INK, 6)
            self.pg([(150, 470), (300, 520), (450, 470), (450, 520), (300, 580), (150, 520)], (60, 220, 230))
        else:  # modern
            self.el([180, 150, 420, 240], (60, 120, 220))
            self.rr([180, 205, 470, 232], 12, (60, 120, 220))
            self.el([290, 145, 310, 165], (240, 240, 250), INK, 3)

    def render(self):
        self.era_back()
        self.legs()
        self.body()
        self.arms()
        self.face()
        self.era_front()
        return self.im.resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- sprite

_cache: dict = {}


def prepare(era: str, date_label: str, outdir: str) -> dict:
    """Render 1 sprite penuh + 3 tambalan wajah (mulut, kedip, kedip+mulut)."""
    label = short_label(date_label)
    key = (era, label, outdir)
    if key in _cache:
        return _cache[key]
    os.makedirs(outdir, exist_ok=True)
    tw, th = int(W * SCALE), int(H * SCALE)
    fx = [round(v * SCALE) for v in FACE_BOX]  # x0,y0,x1,y1 dalam sprite kecil

    def variant(mouth, blink):
        im = Cal(label, mouth_open=mouth, blink=blink, era=era).render()
        return im.resize((tw, th), Image.LANCZOS)

    base = variant(False, False)
    paths = {}
    for name, img, crop in (
        ("base", base, None),
        ("mouth", variant(True, False), fx),
        ("blink", variant(False, True), fx),
        ("blinkmouth", variant(True, True), fx),
    ):
        p = os.path.join(outdir, f"cal_{era}_{label.replace(' ', '')}_{name}.png")
        (img.crop(crop) if crop else img).save(p)
        paths[name] = p
    paths.update(w=tw, h=th, face_x=fx[0], face_y=fx[1])
    _cache[key] = paths
    return paths


# ---------------------------------------------------------------- waktu

def _samples(audio: str, rate: int = 16000) -> array.array:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", audio, "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        check=True, capture_output=True,
    ).stdout
    a = array.array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    return a


def speech_intervals(audio: str, hop: float = 0.05) -> list[tuple[float, float]]:
    """Kapan mulut Cal terbuka: bagian suara yang cukup keras."""
    rate = 16000
    a = _samples(audio, rate)
    n = int(rate * hop)
    rms = []
    for i in range(0, len(a) - n, n):
        seg = a[i:i + n]
        rms.append(math.sqrt(sum(x * x for x in seg) / n))
    if not rms:
        return []
    ranked = sorted(rms)
    thr = max(0.28 * ranked[int(len(ranked) * 0.9)], 150)
    out: list[list[float]] = []
    for i, v in enumerate(rms):
        if v < thr:
            continue
        t0, t1 = i * hop, (i + 1) * hop
        if out and t0 - out[-1][1] <= hop * 1.5:  # sambung celah sangat pendek
            out[-1][1] = t1
        else:
            out.append([t0, t1])
    return [(round(x, 2), round(y, 2)) for x, y in out if y - x >= hop]


def blink_intervals(dur: float, first: float = 1.0, every: float = 3.1, length: float = 0.14):
    out, t = [], first
    while t + length < dur:
        out.append((round(t, 2), round(t + length, 2)))
        t += every
    return out


def expr(intervals) -> str:
    """Ekspresi FFmpeg: bernilai 1 saat t berada di salah satu interval, selain itu 0."""
    if not intervals:
        return "0"
    return "(" + "+".join(f"between(t,{a},{b})" for a, b in intervals) + ")"