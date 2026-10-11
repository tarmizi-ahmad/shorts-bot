"""Catatan posting di Supabase (REST). Mencegah topik dobel & membatasi kuota harian."""
import datetime as dt
import os
import requests


def _h():
    key = os.environ["SUPABASE_KEY"]
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _url():
    return os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/posts"


def posted_today(country: str, tz: dt.tzinfo) -> int:
    start = dt.datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    r = requests.get(
        _url(),
        headers={**_h(), "Prefer": "count=exact"},
        params={"select": "id", "country": f"eq.{country}", "created_at": f"gte.{start.isoformat()}"},
        timeout=30,
    )
    r.raise_for_status()
    return len(r.json())


def used_topics(country: str) -> set[str]:
    r = requests.get(
        _url(),
        headers=_h(),
        params={"select": "topic_id", "country": f"eq.{country}", "order": "created_at.desc", "limit": 200},
        timeout=30,
    )
    r.raise_for_status()
    return {row["topic_id"] for row in r.json()}


def log_post(country: str, topic_id: str, title: str, video_id: str) -> None:
    r = requests.post(
        _url(),
        headers=_h(),
        json={"country": country, "topic_id": topic_id, "title": title, "video_id": video_id},
        timeout=30,
    )
    r.raise_for_status()
