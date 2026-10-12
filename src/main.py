"""Pipeline: trending -> naskah -> gambar -> narasi -> video -> upload."""
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

from . import db, images, script_gen, trends, tts, upload_youtube, video

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_cfg() -> dict:
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    cfg = load_cfg()
    tz = ZoneInfo(cfg["timezone"])
    now = dt.datetime.now(tz)
    force = os.environ.get("FORCE") == "1"

    if not force and now.hour not in cfg["peak_hours"]:
        print(f"Jam {now.hour} bukan jam ramai {cfg['peak_hours']} ({cfg['timezone']}). Lewati.")
        return 0

    if db.posted_today(cfg["country"], tz) >= cfg["max_posts_per_day"] and not force:
        print("Kuota harian tercapai. Lewati.")
        return 0

    used = db.used_topics(cfg["country"])
    topic = next((t for t in trends.get_trends(cfg["country"]) if t["id"] not in used), None)
    if not topic:
        print("Tidak ada topik baru.")
        return 0
    print("Topik:", topic["title"])

    data = script_gen.generate(topic, cfg)
    out = os.path.join(ROOT, "output")
    os.makedirs(out, exist_ok=True)

    clips = []
    for i, sc in enumerate(data["scenes"]):
        img, aud, clip = (os.path.join(out, f"s{i}.{e}") for e in ("png", "mp3", "mp4"))
        images.make_image(sc["image_prompt"], img, cfg["width"], cfg["height"])
        tts.make_voice(sc["narration"], cfg["voice"], aud)
        video.make_clip(img, aud, clip, cfg["width"], cfg["height"], sc["narration"])
        clips.append(clip)
        print(f"Scene {i + 1}/{len(data['scenes'])} selesai")

    final = os.path.join(out, "final.mp4")
    video.concat(clips, os.path.join(out, "list.txt"), final)

    vid = upload_youtube.upload(final, data, cfg.get("privacy", "private"))
    db.log_post(cfg["country"], topic["id"], data["title"], vid)
    print("Terupload:", f"https://youtube.com/shorts/{vid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())