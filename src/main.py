"""Pipeline: trending -> naskah -> gambar -> narasi -> video -> upload.
Mendukung multi-profile dengan state Supabase (Trivia hari ini = Fact besok)."""
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
    merged_cfg = {**cfg, **profile}
    pid = merged_cfg.get("id", "default")
    
    print(f"\n{'='*60}\n🚀 MEMULAI MODE: {pid.upper()}\n{'='*60}")

    source_type = merged_cfg.get("source", "history")
    topic = None

    # === LOGIKA KHUSUS: HISTORY FACT (Mengambil Trivia Kemarin) ===
    if pid == "history_fact":
        pending = db.get_pending_trivia() if not force else None
        if pending:
            topic = pending
            print(f"🧠 [{pid}] Menggunakan JAWABAN trivia kemarin: {topic.get('title', 'Unknown')[:60]}...")
            db.clear_pending_trivia()
        else:
            print(f"⚠️ [{pid}] Tidak ada trivia kemarin (atau mode force). Mengambil topik history acak.")
            used = db.used_topics(merged_cfg["country"])
            candidates = history.get_topics(tz)
            topic = next((t for t in candidates if t["id"] not in used), None)
            if not topic:
                print(f"[{pid}] Tidak ada topik history baru. Skip.")
                return False
            print(f"[{pid}] Topik acak:", topic["title"])
            
    # === LOGIKA KHUSUS: HISTORY TRIVIA (Membuat Pertanyaan Baru) ===
    elif pid == "history_trivia":
        used = db.used_topics(merged_cfg["country"])
        if source_type == "history":
            candidates = history.get_topics(tz)
        else:
            candidates = trends.get_trends(merged_cfg["country"])
            
        topic = next((t for t in candidates if t["id"] not in used), None)
        if not topic:
            print(f"[{pid}] Tidak ada topik trivia baru. Skip.")
            return False
        print(f"[{pid}] Topik trivia baru:", topic["title"])

    if not topic:
        return False

    # Generate Script
    data = script_gen.generate(topic, merged_cfg)
    out = os.path.join(ROOT, "output", pid)
    os.makedirs(out, exist_ok=True)

    year = topic.get("year")
    era = mascot.era_for_year(year) if year else "modern"
    date_label = topic.get("date_label") or dt.datetime.now(tz).strftime("%b %d")
    cal = mascot.prepare(era, date_label, os.path.join(out, "cal"))
    print(f"[{pid}] Era Cal:", era)

    clips = []
    for i, sc in enumerate(data["scenes"]):
        img, aud, clip = (os.path.join(out, f"s{i}.{e}") for e in ("png", "mp3", "mp4"))
        images.make_image(sc["image_prompt"], img, merged_cfg["width"], merged_cfg["height"])
        tts.make_voice(sc["narration"], merged_cfg["voice"], aud)
        video.make_clip(img, aud, clip, merged_cfg["width"], merged_cfg["height"], sc["narration"], cal, year)
        clips.append(clip)
        print(f"[{pid}] Scene {i + 1}/{len(data['scenes'])} selesai")

    final = os.path.join(out, "final.mp4")
    video.concat(clips, os.path.join(out, "list.txt"), final)

    vid = upload_youtube.upload(final, data, merged_cfg.get("privacy", "private"))
    db.log_post(merged_cfg["country"], topic["id"], data["title"], vid)
    print(f"[{pid}] ✅ Terupload: https://youtube.com/shorts/{vid}")

    # SIMPAN TOPIK TRIVIA KE SUPABASE UNTUK BESOK
    if pid == "history_trivia":
        db.save_pending_trivia(topic)

    if upload_facebook.enabled():
        try:
            fb = upload_facebook.upload(final, data)
            print(f"[{pid}] Facebook Reel terkirim, video id:", fb)
        except Exception as e:
            print(f"[{pid}] Facebook gagal:", e)

    return True

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

    profiles = cfg.get("profiles")
    if not profiles:
        profiles = [{
            "id": "default",
            "source": cfg.get("source", "history"),
            "language": cfg.get("language", "English"),
            "niche": cfg.get("niche", ""),
            "angle": cfg.get("angle", ""),
            "scenes": cfg.get("scenes", 5),
            "width": cfg.get("width", 1080),
            "height": cfg.get("height", 1920),
            "voice": cfg.get("voice", "en_US-ryan-high"),
        }]

    success_count = 0
    for profile in profiles:
        if db.posted_today(cfg["country"], tz) >= cfg["max_posts_per_day"] and not force:
            print("Kuota harian tercapai. Stop.")
            break

        try:
            ok = _process_one_profile(profile, cfg, tz, force)
            if ok:
                success_count += 1
        except Exception as e:
            pid = profile.get("id", "default")
            print(f"\n❌ GAGAL di mode {pid}: {e}")
            traceback.print_exc()
            continue

    print(f"\n🏁 SELESAI. Total video sukses: {success_count}/{len(profiles)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())