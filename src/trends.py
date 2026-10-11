"""Ambil video trending dari YouTube Data API (chart mostPopular) per negara."""
import os
import requests

API = "https://www.googleapis.com/youtube/v3/videos"


def get_trends(country: str, limit: int = 15) -> list[dict]:
    key = os.environ["YOUTUBE_API_KEY"]
    r = requests.get(
        API,
        params={
            "part": "snippet",
            "chart": "mostPopular",
            "regionCode": country,
            "maxResults": limit,
            "key": key,
        },
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for item in r.json().get("items", []):
        sn = item["snippet"]
        out.append(
            {
                "id": item["id"],
                "title": sn["title"],
                "channel": sn["channelTitle"],
                "tags": sn.get("tags", [])[:8],
            }
        )
    return out
