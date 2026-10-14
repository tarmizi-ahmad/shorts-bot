"""Catatan posting di Supabase (REST). Mencegah topik dobel & membatasi kuota harian."""
import datetime as dt
import os
import requests


def _h():
    key = os.environ["SUPABASE_KEY"]
    h = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_"):
        h["Authorization"] = f"Bearer {key}"
    return h

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

# --- STATE MANAGEMENT UNTUK TRIVIA (CLIFFHANGER) ---

def get_pending_trivia():
    """Mengambil topik trivia yang disimpan kemarin untuk dijawab hari ini."""
    try:
        url = f"{os.environ['SUPABASE_URL']}/rest/v1/bot_state?key=eq.pending_trivia&select=data"
        headers = {
            "apikey": os.environ["SUPABASE_KEY"],
            "Authorization": f"Bearer {os.environ['SUPABASE_KEY']}"
        }
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            res = r.json()
            if res and len(res) > 0:
                return res[0]["data"]
    except Exception as e:
        print("⚠️ Gagal ambil pending trivia:", e)
    return None

def save_pending_trivia(topic):
    """Menyimpan topik trivia hari ini agar dijawab besok."""
    try:
        url = f"{os.environ['SUPABASE_URL']}/rest/v1/bot_state"
        headers = {
            "apikey": os.environ["SUPABASE_KEY"],
            "Authorization": f"Bearer {os.environ['SUPABASE_KEY']}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates" # Upsert
        }
        payload = {"key": "pending_trivia", "data": topic}
        requests.post(url, headers=headers, json=payload, timeout=15)
        print("✅ Topik trivia disimpan untuk dibahas besok.")
    except Exception as e:
        print("⚠️ Gagal simpan pending trivia:", e)

def clear_pending_trivia():
    """Menghapus state trivia setelah dipakai agar tidak berulang."""
    try:
        url = f"{os.environ['SUPABASE_URL']}/rest/v1/bot_state?key=eq.pending_trivia"
        headers = {
            "apikey": os.environ["SUPABASE_KEY"],
            "Authorization": f"Bearer {os.environ['SUPABASE_KEY']}"
        }
        requests.delete(url, headers=headers, timeout=15)
    except Exception as e:
        print("⚠️ Gagal hapus pending trivia:", e)