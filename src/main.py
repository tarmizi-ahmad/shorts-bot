"""Pipeline: trending -> naskah -> gambar -> narasi -> video -> upload.
Mendukung multi-profile (1 run = 2 video: history_fact + history_trivia)."""
import datetime as dt
import json
import os
import sys
import traceback
from zoneinfo import ZoneInfo

from . import db, history, images, mascot, script_gen, trends, tts, upload_facebook, upload_youtube, video

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_cfg() -> dict:
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def _process_one_profile(profile: dict, cfg: dict, tz, force: bool) -> bool:
    """Proses 1 profil (1 video). Return True jika sukses upload."""
    # GABUNGKAN config global dengan config profil (profil menimpa global jika ada key sama)
    merged_cfg = {**cfg, **profile}
    pid = merged_cfg.get("id", "default")
    
    print(f"\n{'='*60}\n🚀 MEMULAI MODE: {pid.upper()}\n{'='*60}")

    # 1. Ambil Topik
    used = db.used_topics(merged_cfg["country"])
    source_type = merged_cfg.get("source", "history")
    if source_type == "history":
        candidates = history.get_topics(tz)
    else:
        candidates = trends.get_trends(merged_cfg["country"])

    topic = next((t for t in candidates if t["id"] not in used), None)
    if not topic:
        print(f"[{pid}] Tidak ada topik baru. Skip.")
        return False
    print(f"[{pid}] Topik:", topic["title"])

    # 2. Generate Script (Sekarang merged_cfg punya "country", "language", dll)
    data = script_gen.generate(topic, merged_cfg)
    out = os.path.join(ROOT, "output", pid)
    os.makedirs(out, exist_ok=True)

    # 3. Siapkan Maskot
    year = topic.get("year")
    era = mascot.era_for_year(year) if year else "modern"
    date_label = topic.get("date_label") or dt.datetime.now(tz).strftime("%b %d")
    cal = mascot.prepare(era, date_label, os.path.join(out, "cal"))
    print(f"[{pid}] Era Cal:", era)

    # 4. Render Scenes
    clips = []
    for i, sc in enumerate(data["scenes"]):
        img, aud, clip = (os.path.join(out, f"s{i}.{e}") for e in ("png", "mp3", "mp4"))
        images.make_image(sc["image_prompt"], img, merged_cfg["width"], merged_cfg["height"])
        tts.make_voice(sc["narration"], merged_cfg["voice"], aud)
        video.make_clip(img, aud, clip, merged_cfg["width"], merged_cfg["height"], sc["narration"], cal, year)
        clips.append(clip)
        print(f"[{pid}] Scene {i + 1}/{len(data['scenes'])} selesai")

    # 5. Concat & Upload
    final = os.path.join(out, "final.mp4")
    video.concat(clips, os.path.join(out, "list.txt"), final)

    vid = upload_youtube.upload(final, data, merged_cfg.get("privacy", "private"))
    db.log_post(merged_cfg["country"], topic["id"], data["title"], vid)
    print(f"[{pid}] ✅ Terupload: https://youtube.com/shorts/{vid}")

    # 6. Upload Facebook (opsional, aman di-skip jika token kosong)
    if upload_facebook.enabled():
        try:
            fb = upload_facebook.upload(final, data)
            print(f"[{pid}] Facebook Reel terkirim, video id:", fb)
        except Exception as e:  # noqa: BLE001
            print(f"[{pid}] Facebook gagal (YouTube tetap sukses):", e)

    return True


def main() -> int:
    cfg = load_cfg()
    tz = ZoneInfo(cfg["timezone"])
    now = dt.datetime.now(tz)
    force = os.environ.get("FORCE") == "1"

    if not force and now.hour not in cfg["peak_hours"]:
        print(f"Jam {now.hour} bukan jam ramai {cfg['peak_hours']} ({cfg['timezone']}). Lewati.")
        return 0

    # Cek kuota global
    if db.posted_today(cfg["country"], tz) >= cfg["max_posts_per_day"] and not force:
        print("Kuota harian tercapai. Lewati.")
        return 0

    # Ambil daftar profil (fallback ke 1 profil default jika config lama)
    profiles = cfg.get("profiles")
    if not profiles:
        profiles = [{
            "id": "default",
            "source": cfg.get("source", "history"),
            "language": cfg["language"],
            "niche": cfg.get("niche", ""),
            "angle": cfg.get("angle", ""),
            "scenes": cfg["scenes"],
            "width": cfg["width"],
            "height": cfg["height"],
            "voice": cfg["voice"],
        }]

    success_count = 0
    for profile in profiles:
        # Cek kuota lagi sebelum tiap profil (agar tidak jebol max_posts_per_day)
        if db.posted_today(cfg["country"], tz) >= cfg["max_posts_per_day"] and not force:
            print("Kuota harian tercapai. Stop memproses profil berikutnya.")
            break

        try:
            ok = _process_one_profile(profile, cfg, tz, force)
            if ok:
                success_count += 1
        except Exception as e:
            pid = profile.get("id", "default")
            print(f"\n❌ GAGAL di mode {pid}: {e}")
            traceback.print_exc()
            # Continue ke profil berikutnya, JANGAN return!
            continue

    print(f"\n🏁 SELESAI. Total video sukses diupload: {success_count}/{len(profiles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())