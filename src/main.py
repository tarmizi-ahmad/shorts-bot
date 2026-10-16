"""Pipeline: trending -> naskah -> gambar -> narasi -> video -> upload."""
import datetime as dt
import json
import os
import sys
import traceback
from zoneinfo import ZoneInfo

from . import db, history, images, mascot, script_gen, trends, tts, upload_facebook, upload_youtube, video

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
REPORT_FILE = os.path.join(OUT_DIR, "report.txt")


def load_cfg() -> dict:
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def write_report(lines: list) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _process_one_profile(profile: dict, cfg: dict, tz, force: bool) -> str:
    merged_cfg = {**cfg, **profile}
    pid = merged_cfg.get("id", "default")
    
    print(f"\n{'='*60}\n🚀 MEMULAI MODE: {pid.upper()}\n{'='*60}")

    source_type = merged_cfg.get("source", "history")
    topic = None
    used_pending_trivia = False

    if pid == "history_fact":
        pending = db.get_pending_trivia()
        if pending:
            topic = pending
            used_pending_trivia = True
            print(f"🧠 [{pid}] Menggunakan JAWABAN trivia kemarin: {topic.get('title', 'Unknown')[:60]}...")
        else:
            print(f"⚠️ [{pid}] Tidak ada trivia kemarin. Mengambil topik history acak.")
            used = db.used_topics(merged_cfg["country"])
            candidates = history.get_topics(tz)
            topic = next((t for t in candidates if t["id"] not in used), None)
            if not topic:
                return f"[{pid}] Tidak ada topik baru"
            print(f"[{pid}] Topik acak: {topic['title']}")

    elif pid == "history_trivia":
        used = db.used_topics(merged_cfg["country"])
        candidates = history.get_topics(tz) if source_type == "history" else trends.get_trends(merged_cfg["country"])
        topic = next((t for t in candidates if t["id"] not in used), None)
        if not topic:
            return f"[{pid}] Tidak ada topik baru"
        print(f"[{pid}] Topik trivia baru: {topic['title']}")

    if not topic:
        return f"[{pid}] Topik kosong"

    data = script_gen.generate(topic, merged_cfg)
    out = os.path.join(OUT_DIR, pid)
    os.makedirs(out, exist_ok=True)

    year = topic.get("year")
    era = mascot.era_for_year(year) if year else "modern"
    date_label = topic.get("date_label") or dt.datetime.now(tz).strftime("%b %d")
    cal = mascot.prepare(era, date_label, os.path.join(out, "cal"))
    print(f"[{pid}] Era Cal: {era}")

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

    if used_pending_trivia:
        db.clear_pending_trivia()
        print(f"🧹 [{pid}] Pending trivia di-clear (karena upload sukses).")

    if pid == "history_trivia":
        db.save_pending_trivia(topic)

    if upload_facebook.enabled():
        try:
            fb = upload_facebook.upload(final, data)
            print(f"[{pid}] Facebook Reel terkirim, video id: {fb}")
        except Exception as e:  # noqa: BLE001
            print(f"[{pid}] Facebook gagal: {e}")

    return f"https://youtube.com/shorts/{vid}"


def main() -> int:
    cfg = load_cfg()
    tz = ZoneInfo(cfg["timezone"])
    now = dt.datetime.now(tz)
    force = os.environ.get("FORCE") == "1"

    if not force and now.hour not in cfg["peak_hours"]:
        msg = f"Jam {now.hour} bukan jam ramai {cfg['peak_hours']} ({cfg['timezone']})."
        print(msg)
        write_report([f"SKIP: {msg}"])
        return 0

    if db.posted_today(cfg["country"], tz) >= cfg["max_posts_per_day"] and not force:
        msg = "Kuota harian tercapai. Lewati."
        print(msg)
        write_report(["SKIP: Kuota harian tercapai"])
        return 0

    profiles = cfg.get("profiles")
    if not profiles:
        profiles = [{"id": "default", "source": cfg.get("source", "history"),
                     "language": cfg.get("language", "English"), "niche": cfg.get("niche", ""),
                     "angle": cfg.get("angle", ""), "scenes": cfg.get("scenes", 5),
                     "width": cfg.get("width", 1080), "height": cfg.get("height", 1920),
                     "voice": cfg.get("voice", "en_US-ryan-high")}]

    results = []
    for profile in profiles:
        pid = profile.get("id", "default")
        if db.posted_today(cfg["country"], tz) >= cfg["max_posts_per_day"] and not force:
            print("Kuota harian tercapai. Stop.")
            results.append(f"[{pid}] Kuota tercapai")
            continue
            
        try:
            result = _process_one_profile(profile, cfg, tz, force)
            results.append(result)
            
            # ⭐ LOGIKA BARU: Jika history_fact gagal karena batas upload, HENTIKAN SEMUA.
            if pid == "history_fact" and "ERROR" in result and "uploadLimitExceeded" in result:
                print("\n⛔ BATAS UPLOAD YOUTUBE TERCAPAI. Menghentikan pipeline untuk menghemat resource.")
                results.append("[history_trivia] DIBATALKAN: Batas upload YouTube tercapai di mode sebelumnya.")
                break
                
        except Exception as e:
            tb = traceback.format_exc()
            root_cause = tb.strip().split("\n")[-1]
            print(f"\n❌ GAGAL di mode {pid}: {root_cause}")
            results.append(f"[{pid}] ERROR: {root_cause}")
            
            # ⭐ LOGIKA BARU: Tangkap exception upload limit juga
            if "uploadLimitExceeded" in root_cause:
                print("\n⛔ BATAS UPLOAD YOUTUBE TERCAPAI. Menghentikan pipeline untuk menghemat resource.")
                results.append("[history_trivia] DIBATALKAN: Batas upload YouTube tercapai.")
                break

    write_report(results)
    
    ok_count = sum(1 for r in results if "https://youtube.com/shorts/" in r)
    print(f"\n🏁 SELESAI. Total video sukses: {ok_count}/{len(profiles)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        tb = traceback.format_exc()
        root_cause = tb.strip().split("\n")[-1]
        print(f"\n❌ FATAL ERROR: {root_cause}")
        write_report([f"FATAL ERROR: {root_cause}"])
        sys.exit(1)