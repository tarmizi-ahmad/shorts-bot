"""Topik 'On this day' dari Wikipedia (gratis, tanpa API key)."""
import datetime as dt
import requests

URLS = [
    "https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/events/{m:02d}/{d:02d}",
    "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{m:02d}/{d:02d}",
]
HEADERS = {"User-Agent": "shorts-bot/1.0 (educational project)"}


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
    # Makin banyak halaman Wikipedia terkait, makin dikenal kejadiannya.
    events.sort(key=lambda e: len(e.get("pages", [])), reverse=True)
    out = []
    for e in events[:limit]:
        text = (e.get("text") or "").strip()
        year = e.get("year")
        if not text or not year:
            continue
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