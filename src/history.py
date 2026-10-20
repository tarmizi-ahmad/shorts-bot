"""Topik 'On this day' dari Wikipedia (gratis, tanpa API key), dengan penyaring topik sensitif."""
import datetime as dt
import re
import requests

URLS = [
    "https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/{m:02d}/{d:02d}",
    "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{m:02d}/{d:02d}",
]
HEADERS = {"User-Agent": "shorts-bot/1.0 (educational project)"}

SAFE_MODE = True  # False = tanpa penyaring (seperti versi lama)

# Kekerasan/kejadian kelam: DIBUANG sama sekali (rawan iklan terbatas & kurang cocok untuk format ringan).
HARD = re.compile(
    r"\b(massacre\w*|genocide\w*|terror\w*|bomb\w*|assassinat\w*|execut\w*|shoot\w*|murder\w*|killed|kills?|"
    r"hostages?|suicide|holocaust|atrocit\w*|isil|isis|islamic state|al-qaeda|slaughter\w*|lynch\w*|torture\w*|"
    r"rape\w*|ethnic cleansing|death camps?|concentration camps?)\b", re.I)
# Perang/konflik: BOLEH, tapi diurutkan paling akhir (dipilih hanya bila topik lain habis).
SOFT = re.compile(
    r"\b(war|wars|battle|battles|invasion|invade\w*|siege|military|offensive|uprising|rebellion|revolt|coup|"
    r"attack\w*|troops|army|navy|bombard\w*|conflict)\b", re.I)
# Kejadian positif/menarik: diberi nilai tambah.
BOOST = re.compile(
    r"\b(peace|prize|treaty|discover\w*|invent\w*|first|founded|opens?|opened|launch\w*|wins?|won|record|"
    r"breakthrough|lands?|landed|independence|signed|established|premiere\w*|released?)\b", re.I)


def _rank(text: str, titles: list[str], n_pages: int):
    """Kembalikan (dibuang?, soft?, skor)."""
    blob = " ".join([text] + titles)
    if HARD.search(blob):
        return True, False, 0
    soft = bool(SOFT.search(blob))
    score = n_pages + 2 * min(len(BOOST.findall(blob)), 3)
    return False, soft, score


def get_topics(tz, limit: int = 40) -> list[dict]:
    today = dt.datetime.now(tz)
    events, last = [], None
    for u in URLS:
        try:
            r = requests.get(u.format(m=today.month, d=today.day), headers=HEADERS, timeout=30)
            r.raise_for_status()
            events = r.json().get("events", [])
            if events:
                break
        except requests.exceptions.RequestException as e:
            last = e
            print("Wikipedia gagal:", e)
    if not events and last:
        raise last

    ranked, dropped = [], 0
    for e in events:
        text = (e.get("text") or "").strip()
        if not text or not e.get("year"):
            continue
        pages = e.get("pages", [])
        titles = [p.get("normalizedtitle", "") for p in pages[:3] if p.get("normalizedtitle")]
        if SAFE_MODE:
            drop, soft, score = _rank(text, titles, len(pages))
            if drop:
                dropped += 1
                continue
        else:
            soft, score = False, len(pages)
        ranked.append((soft, -score, e))
    if SAFE_MODE:
        print(f"Penyaring topik: {dropped} dibuang (kekerasan), sisa {len(ranked)}; topik perang dipakai paling akhir.")
    ranked.sort(key=lambda x: (x[0], x[1]))  # non-perang dulu, lalu skor tertinggi

    out = []
    for _, _, e in ranked[:limit]:
        text = (e.get("text") or "").strip()
        year = e.get("year")
        pages = e.get("pages", [])
        extract = " ".join((p.get("extract") or "") for p in pages[:2]).strip()
        keywords = [p.get("normalizedtitle", "") for p in pages[:3] if p.get("normalizedtitle")]
        out.append(
            {
                "id": f"otd-{year}-{text[:40]}",
                "title": f"{today.strftime('%B')} {today.day}, {year}: {text}",
                "year": year,
                "date_label": f"{today.strftime('%b')} {today.day}, {year}",
                "tags": keywords + ["today in history", "history"],
                "facts": f"{text} {extract}"[:900],
            }
        )
    return out