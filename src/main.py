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
    """Tulis laporan sederhana ke file untuk dikirim via email."""
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _process_one_profile(profile: dict, cfg: dict, tz, force: bool) -> str:
    """Return link video jika sukses, atau error message jika gagal."""
    merged_cfg = {**cfg, **profile}
    pid = merged_cfg.get("id", "default")
    print(f"\n{'='*60}\n🚀 MODE: {pid.upper()}\n{'='*60}")

    source_type = merged_cfg.get("source", "history")
    topic = None
    used_pending_trivia = False  # ⭐ FLAG: Hanya clear DB jika upload sukses

    if pid == "history_fact":
        pending = db.get_pending_trivia()
        if pending:
            topic = pending
            used_pending_trivia = True  # ⭐ Tandai bahwa kita memakai data ini
            print(f"🧠 [{pid}] Menggunakan JAWABAN trivia kemarin")
        else:
            used = db.used_topics(merged_cfg["country"])
            candidates = history.get_topics(tz)
            topic = next((t for t in candidates if t["id"] not in used), None)
            if not topic:
                return f"[{pid}] Tidak ada topik baru"
            print(f"[{pid}] Topik acak")

    elif pid == "history_trivia":
        used = db.used_topics(merged_cfg["country"])
        candidates = history.get_topics(tz) if source_type == "history" else trends.get_trends(merged_cfg["country"])
        topic = next((t for t in candidates if t["id"] not in used), None)
        if not topic:
            return f"[{pid}] Tidak ada topik baru"
        print(f"[{pid}] Topik trivia baru")

    if not topic:
        return f"[{pid}] Topik kosong"

    data = script_gen.generate(topic, merged_cfg)
    out = os.path.join(OUT_DIR, pid)
    os.makedirs(out, exist_ok=True)

    year = topic.get("year")
    era = mascot.era_for_year(year) if year else "modern"
    date_label = topic.get("date_label") or dt.datetime.now(tz).strftime("%b %d")
    cal = mascot.prepare(era, date_label, os.path.join(out, "cal"))

    clips = []
    for i, sc in enumerate(data["scenes"]):
        img, aud, clip = (os.path.join(out, f"s{i}.{e}") for e in ("png", "mp3", "mp4"))
        images.make_image(sc["image_prompt"], img, merged_cfg["width"], merged_cfg["height"])
        tts.make_voice(sc["narration"], merged_cfg["voice"], aud)
        video.make_clip(img, aud, clip, merged_cfg["width"], merged_cfg["height"], sc["narration"], cal, year)
        clips.append(clip)

    final = os.path.join(out, "final.mp4")
    video.concat(clips, os.path.join(out, "list.txt"), final)

    # ⭐ UPLOAD: Jika baris ini gagal (Exception), kode di bawahnya TIDAK akan jalan.
    # Artinya used_pending_trivia tidak akan diproses, dan data tetap aman di DB.
    vid = upload_youtube.upload(final, data, merged_cfg.get("privacy", "private"))
    db.log_post(merged_cfg["country"], topic["id"], data["title"], vid)

    # ⭐ BARU SEKARANG AMAN: clear pending trivia & simpan trivia baru
    if used_pending_trivia:
        db.clear_pending_trivia()
        print(f"🧹 [{pid}] Pending trivia di-clear (karena upload sukses).")

    if pid == "history_trivia":
        db.save_pending_trivia(topic)

    if upload_facebook.enabled():
        try:
            upload_facebook.upload(final, data)
        except Exception:  # noqa: BLE001
            pass  # Abaikan error FB, YouTube sudah sukses

    return f"https://youtube.com/shorts/{vid}"


def main() -> int:
    cfg = load_cfg()
    tz = ZoneInfo(cfg["timezone"])
    now = dt.datetime.now(tz)
    force = os.environ.get("FORCE") == "1"

    if not force and now.hour not in cfg["peak_hours"]:
        write_report([f"SKIP: Jam {now.hour} bukan jam ramai"])
        return 0

    if db.posted_today(cfg["country"], tz) >= cfg["max_posts_per_day"] and not force:
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
            results.append(f"[{pid}] Kuota tercapai")
            continue
        try:
            result = _process_one_profile(profile, cfg, tz, force)
            results.append(result)
        except Exception as e:
            # Ambil root cause (baris terakhir dari traceback)
            tb = traceback.format_exc()
            root_cause = tb.strip().split("\n")[-1]
            results.append(f"[{pid}] ERROR: {root_cause}")

    write_report(results)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        tb = traceback.format_exc()
        root_cause = tb.strip().split("\n")[-1]
        write_report([f"FATAL ERROR: {root_cause}"])
        sys.exit(1)