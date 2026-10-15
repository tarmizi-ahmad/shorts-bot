"""Catatan posting di Supabase (REST). Mencegah topik dobel & membatasi kuota harian."""
import datetime as dt
import json
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

# =========================================================
# STATE MANAGEMENT UNTUK TRIVIA (CLIFFHANGER) - BULLETPROOF
# =========================================================

def get_pending_trivia():
    """Mengambil topik trivia yang disimpan kemarin untuk dijawab hari ini."""
    try:
        url = f"{os.environ['SUPABASE_URL']}/rest/v1/bot_state?select=data&key=eq.pending_trivia"
        print(f"🔍 [DB] Mengambil data dari: {url}")
        
        r = requests.get(url, headers=_h(), timeout=15)
        print(f"🔍 [DB] Status Code: {r.status_code} | Response: {r.text[:300]}")
        
        if r.status_code == 200:
            res = r.json()
            if res and len(res) > 0:
                raw_data = res[0]["data"]
                # PERBAIKAN PENTING: Handle jika data tersimpan sebagai string, bukan jsonb
                if isinstance(raw_data, str):
                    topic = json.loads(raw_data)
                else:
                    topic = raw_data
                
                print(f"✅ [DB] Trivia kemarin DITEMUKAN: {topic.get('title', 'Unknown')[:50]}...")
                return topic
            else:
                print("⚠️ [DB] Tabel bot_state kosong (belum ada trivia yang disimpan).")
        else:
            print(f"⚠️ [DB] Gagal ambil data. Status: {r.status_code} | Detail: {r.text}")
    except Exception as e:
        print(f"⚠️ [DB] Exception saat ambil trivia: {e}")
    
    return None

def save_pending_trivia(topic: dict):
    """Menyimpan topik trivia hari ini agar dijawab besok."""
    try:
        url = f"{os.environ['SUPABASE_URL']}/rest/v1/bot_state"
        # Pastikan payload adalah dictionary yang valid untuk jsonb
        payload = {"key": "pending_trivia", "data": topic}
        
        r = requests.post(
            url, 
            headers={**_h(), "Prefer": "resolution=merge-duplicates"}, 
            json=payload, 
            timeout=15
        )
        
        if r.status_code in (200, 201, 204):
            print(f"✅ [DB] Topik trivia BERHASIL disimpan: {topic.get('title', 'Unknown')[:50]}...")
        else:
            print(f"⚠️ [DB] Gagal simpan. Status: {r.status_code} | Detail: {r.text}")
    except Exception as e:
        print(f"⚠️ [DB] Exception saat simpan trivia: {e}")

def clear_pending_trivia():
    """Menghapus state trivia setelah dipakai agar tidak berulang."""
    try:
        url = f"{os.environ['SUPABASE_URL']}/rest/v1/bot_state?key=eq.pending_trivia"
        r = requests.delete(url, headers=_h(), timeout=15)
        print(f"🧹 [DB] Clear pending trivia. Status: {r.status_code}")
    except Exception as e:
        print(f"⚠️ [DB] Exception saat hapus trivia: {e}")