"""Ambil video trending dari YouTube Data API (chart mostPopular) per negara."""
import os
import requests

API = "https://www.googleapis.com/youtube/v3/videos"
SKIP_CATEGORIES = {"10", "1"}  # 10 = Music, 1 = Film & Animation


def get_trends(country: str, limit: int = 50) -> list[dict]:
    r = requests.get(
        API,
        params={
            "part": "snippet",
            "chart": "mostPopular",
            "regionCode": country,
            "maxResults": limit,
            "key": os.environ["YOUTUBE_API_KEY"],
        },
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for item in r.json().get("items", []):
        sn = item["snippet"]
        if sn.get("categoryId") in SKIP_CATEGORIES:
            continue
        lang = (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "en").lower()
        if country == "US" and not lang.startswith("en"):
            continue
        out.append(
            {
                "id": item["id"],
                "title": sn["title"],
                "channel": sn["channelTitle"],
                "tags": sn.get("tags", [])[:8],
            }
        )
    return out