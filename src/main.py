"""Pipeline: topik -> naskah -> gambar -> narasi -> video -> upload (bisa beberapa profil per run)."""
import datetime as dt
import json
import os
import sys
import traceback
from zoneinfo import ZoneInfo

from . import db, history, images, mascot, notify, script_gen, trends, tts, upload_facebook, upload_youtube, video

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
REPORT_FILE = os.path.join(OUT_DIR, "report.txt")

# Topik yang sudah dipilih di run ini (supaya 2 profil tidak memilih topik sama, termasuk saat dry-run)
RUN_USED: set = set()


def load_cfg() -> dict:
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def write_report(lines: list) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_summary(title: str, results: list) -> None:
    """Ringkasan di halaman run GitHub Actions (mudah dibaca dari HP)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [f"## {title}", ""]
    for r in results:
        bad = "ERROR" in r or "DIBATALKAN" in r or "BERMASALAH" in r
        lines.append(f"- {'❌' if bad else '✅'} {r}")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


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
            merged_cfg["is_answer"] = True
            print(f"🧠 [{pid}] Menggunakan JAWABAN trivia kemarin: {topic.get('title', 'Unknown')[:60]}...")
        else:
            print(f"⚠️ [{pid}] Tidak ada trivia kemarin. Mengambil topik history acak.")
            used = set(db.used_topics(merged_cfg["country"])) | RUN_USED
            candidates = history.get_topics(tz)
            topic = next((t for t in candidates if t["id"] not in used), None)
            if not topic:
                return f"[{pid}] Tidak ada topik baru"
            print(f"[{pid}] Topik acak: {topic['title']}")

    elif pid == "history_trivia":
        used = set(db.used_topics(merged_cfg["country"])) | RUN_USED
        candidates = history.get_topics(tz) if source_type == "history" else trends.get_trends(merged_cfg["country"])
        topic = next((t for t in candidates if t["id"] not in used), None)
        if not topic:
            return f"[{pid}] Tidak ada topik baru"
        print(f"[{pid}] Topik trivia baru: {topic['title']}")

    if not topic:
        return f"[{pid}] Topik kosong"
    RUN_USED.add(topic["id"])

    is_trivia = pid == "history_trivia"
    year = topic.get("year")
    date_label = topic.get("date_label") or dt.datetime.now(tz).strftime("%b %d")

    # Trivia TIDAK boleh membocorkan jawaban: judul hanya memuat tanggal (tanpa tahun) dan tahun tidak ditampilkan.
    script_topic = topic
    if is_trivia:
        script_topic = {**topic, "date_label": date_label.split(",")[0].strip()}
    data = script_gen.generate(script_topic, merged_cfg)

    out = os.path.join(OUT_DIR, pid)
    os.makedirs(out, exist_ok=True)

    era = mascot.era_for_year(year) if year else "modern"
    cal = mascot.prepare(era, date_label, os.path.join(out, "cal"))
    print(f"[{pid}] Era Cal: {era}")

    # Blacklist provider (Cloudflare/Pollinations) SENGAJA dibawa ke profil berikutnya (modul images sama).
    # Tapi gambar sukses terakhir harus dilupakan: latar profil lain beda topik/era.
    images.LAST_GOOD_IMAGE = None

    clips = []
    for i, sc in enumerate(data["scenes"]):
        img, aud, clip = (os.path.join(out, f"s{i}.{e}") for e in ("png", "mp3", "mp4"))
        images.make_image(sc["image_prompt"], img, merged_cfg["width"], merged_cfg["height"])
        tts.make_voice(sc["narration"], merged_cfg["voice"], aud)
        video.make_clip(img, aud, clip, merged_cfg["width"], merged_cfg["height"], sc["narration"], cal,
                        None if is_trivia else year)
        clips.append(clip)
        print(f"[{pid}] Scene {i + 1}/{len(data['scenes'])} selesai")

    final = os.path.join(out, "final.mp4")
    video.concat(clips, os.path.join(out, "list.txt"), final)

    if os.environ.get("UPLOAD_YOUTUBE") == "0":
        # DRY-RUN: video tetap jadi (lihat Artifacts), tapi tidak ada upload & database tidak disentuh.
        print(f"[{pid}] 🧪 DRY-RUN: upload YouTube/Facebook dilewati. Video: {final}")
        return f"[{pid}] DRY-RUN video tersimpan: {final}"

    vid = upload_youtube.upload(final, data, merged_cfg.get("privacy", "private"))
    db.log_post(merged_cfg["country"], topic["id"], data["title"], vid)
    print(f"[{pid}] ✅ Terupload: https://youtube.com/shorts/{vid}")

    if used_pending_trivia:
        db.clear_pending_trivia()
        print(f"🧹 [{pid}] Pending trivia di-clear (karena upload sukses).")

    if is_trivia:
        db.save_pending_trivia(topic)

    if upload_facebook.enabled():
        try:
            fb = upload_facebook.upload(final, data)
            print(f"[{pid}] Facebook Reel terkirim, video id: {fb}")
        except Exception as e:  # noqa: BLE001
            print(f"[{pid}] Facebook gagal: {e}")

    return f"[{pid}] https://youtube.com/shorts/{vid} — {data['title']} (privacy: {merged_cfg.get('privacy', 'private')})"


def main() -> int:
    cfg = load_cfg()
    tz = ZoneInfo(cfg["timezone"])
    now = dt.datetime.now(tz)
    dry_run = os.environ.get("UPLOAD_YOUTUBE") == "0"
    force = os.environ.get("FORCE") == "1" or dry_run  # dry-run tidak memposting, jadi cek jam & kuota dilewati
    if dry_run:
        print("🧪 MODE DRY-RUN: video dibuat tapi TIDAK diunggah ke YouTube/Facebook.")

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

    if not dry_run:
        # Cek token YouTube dulu: kalau mati, jangan buang kuota Gemini/Cloudflare untuk video yang tak bisa diunggah.
        try:
            upload_youtube.check_auth()
            print("✅ Token YouTube valid.")
        except Exception as e:  # noqa: BLE001
            msg = (f"TOKEN YOUTUBE BERMASALAH: {str(e)[:200]}\n"
                   "Buat ulang YT_REFRESH_TOKEN (OAuth Playground) dan pastikan app OAuth berstatus 'In production'.")
            print("\n⛔", msg)
            write_report([msg])
            write_summary("Run gagal: token YouTube", [msg.replace("\n", " ")])
            notify.notify("❌ Shorts-ai: token YouTube bermasalah", [msg])
            return 1

    profiles = cfg.get("profiles")
    if not profiles:
        profiles = [{"id": "default", "source": cfg.get("source", "history"),
                     "language": cfg.get("language", "English"), "niche": cfg.get("niche", ""),
                     "angle": cfg.get("angle", ""), "scenes": cfg.get("scenes", 5),
                     "width": cfg.get("width", 1080), "height": cfg.get("height", 1920),
                     "voice": cfg.get("voice", "en_US-ryan-high")}]

    results = []
    for n, profile in enumerate(profiles):
        pid = profile.get("id", "default")
        if db.posted_today(cfg["country"], tz) >= cfg["max_posts_per_day"] and not force:
            print("Kuota harian tercapai. Stop.")
            results.append(f"[{pid}] Kuota tercapai")
            continue

        try:
            results.append(_process_one_profile(profile, cfg, tz, force))
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc()
            root_cause = tb.strip().split("\n")[-1]
            print(f"\n❌ GAGAL di mode {pid}: {root_cause}")
            results.append(f"[{pid}] ERROR: {root_cause}")

            # Batas upload YouTube berlaku untuk seluruh channel: profil berikutnya pasti gagal juga.
            if "uploadLimitExceeded" in root_cause or "exceeded the number of videos" in root_cause:
                print("\n⛔ BATAS UPLOAD YOUTUBE TERCAPAI. Menghentikan pipeline untuk menghemat resource.")
                for later in profiles[n + 1:]:
                    results.append(f"[{later.get('id', 'default')}] DIBATALKAN: batas upload YouTube tercapai.")
                break

    write_report(results)
    write_summary("Hasil run" + (" (dry-run)" if dry_run else ""), results)

    ok_count = sum(1 for r in results if "https://youtube.com/shorts/" in r or "DRY-RUN video" in r)
    print(f"\n🏁 SELESAI. Total video sukses: {ok_count}/{len(profiles)}")

    # Notifikasi hanya bila ada percobaan upload sungguhan (bukan skip / dry-run).
    attempted = [r for r in results if "https://youtube.com/shorts/" in r or "ERROR" in r or "DIBATALKAN" in r]
    if attempted and not dry_run:
        up = sum(1 for r in results if "https://youtube.com/shorts/" in r)
        if up == len(profiles):
            subject = f"✅ Shorts-ai: {up} video berhasil diupload"
        elif up:
            subject = f"⚠️ Shorts-ai: {up}/{len(profiles)} video berhasil diupload"
        else:
            subject = "❌ Shorts-ai: tidak ada video yang terupload"
        notify.notify(subject, results)

    # Kode keluar 1 bila ada profil yang error: run ditandai GAGAL di GitHub, sehingga email notifikasi terkirim.
    failed = [r for r in results if "ERROR" in r or "DIBATALKAN" in r]
    if failed:
        print(f"⚠️ {len(failed)} profil gagal -> run ditandai GAGAL agar kamu diberi tahu.")
        return 1
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