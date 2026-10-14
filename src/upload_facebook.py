"""Upload Reels ke Halaman (Page) Facebook lewat Graph API. Opsional.

Aktif hanya jika FB_PAGE_ID dan FB_PAGE_TOKEN ada. Kegagalan di sini tidak
membatalkan upload YouTube (ditangani di main.py).
"""
import json
import os
import time

import requests


def _base() -> str:
    return f"https://graph.facebook.com/{os.environ.get('FB_GRAPH_VERSION', 'v25.0')}"


def enabled() -> bool:
    return bool(os.environ.get("FB_PAGE_ID") and os.environ.get("FB_PAGE_TOKEN"))


def _check(r: requests.Response, step: str) -> dict:
    try:
        j = r.json()
    except ValueError:
        j = {"raw": r.text[:300]}
    if r.status_code >= 400 or (isinstance(j, dict) and "error" in j):
        raise RuntimeError(f"Facebook {step} gagal ({r.status_code}): {json.dumps(j)[:400]}")
    return j


def _description(data: dict) -> str:
    base = (data.get("description") or "").strip()
    title = (data.get("title") or "").strip()
    text = f"{title}\n\n{base}" if base else title
    return text[:2000]


def upload(path: str, data: dict) -> str:
    page, tok = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    base = _base()

    # 1) mulai sesi upload
    j = _check(requests.post(f"{base}/{page}/video_reels",
                             data={"upload_phase": "start", "access_token": tok}, timeout=60), "start")
    video_id, upload_url = j["video_id"], j["upload_url"]

    # 2) kirim file video
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        r = requests.post(
            upload_url,
            headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)},
            data=f, timeout=900,
        )
    _check(r, "upload")

    # 3) selesaikan & terbitkan
    _check(requests.post(
        f"{base}/{page}/video_reels",
        data={"upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
              "description": _description(data), "title": (data.get("title") or "")[:100],
              "access_token": tok},
        timeout=60,
    ), "finish")

    # 4) pantau status pemrosesan (hanya info, tidak menggagalkan)
    for _ in range(12):
        time.sleep(10)
        try:
            s = requests.get(f"{base}/{video_id}", params={"fields": "status", "access_token": tok}, timeout=30).json()
        except Exception as e:  # noqa: BLE001
            print("Cek status Facebook gagal:", e)
            break
        st = (s.get("status") or {}) if isinstance(s, dict) else {}
        print("Status Facebook:", st.get("video_status"))
        if st.get("video_status") in ("ready", "error"):
            break
    return video_id