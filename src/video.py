"""Rangkai latar + narasi + subtitle + maskot Cal jadi video vertikal 9:16 dengan FFmpeg."""
import os
import subprocess

from . import mascot

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SUB_Y = 0.50   # posisi subtitle (di atas kepala Cal)
BOB = 9        # amplitudo naik-turun Cal (px)
BOB_PERIOD = 2.2


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise RuntimeError("FFmpeg gagal: " + r.stderr[-1500:])


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def _chunks(text: str, max_chars: int = 16, max_words: int = 3) -> list[str]:
    """Potong kata jadi baris pendek: maks 16 huruf & 3 kata per tampilan."""
    out, cur = [], []
    for wd in text.split():
        trial = " ".join(cur + [wd])
        if cur and (len(trial) > max_chars or len(cur) >= max_words):
            out.append(" ".join(cur))
            cur = [wd]
        else:
            cur.append(wd)
    if cur:
        out.append(" ".join(cur))
    return out


def _subtitle_filters(text: str, dur: float, w: int, h: int, base: str) -> str:
    """drawtext per potongan 3 kata, waktu sebanding panjang huruf."""
    parts = _chunks(text)
    if not parts:
        return ""
    total = sum(len(p) for p in parts)
    t, filters = 0.0, []
    for i, p in enumerate(parts):
        d = dur * len(p) / total
        # Huruf kapital DejaVu Bold ~0.8 x fontsize lebarnya; muat di 84% lebar video.
        fs = int(min(76, (w * 0.84) / (0.8 * max(len(p), 1))))
        tf = f"{base}_sub{i}.txt"
        with open(tf, "w", encoding="utf-8") as f:
            f.write(p.upper())
        filters.append(
            f"drawtext=fontfile={FONT}:textfile={tf}:expansion=none:"
            f"fontsize={fs}:fontcolor=white:borderw=6:bordercolor=black:"
            f"x=(w-text_w)/2:y={int(h * SUB_Y)}:"
            f"enable='between(t,{t:.2f},{t + d:.2f})'"
        )
        t += d
    return ",".join(filters)


def _year_filter(year, h: int) -> str:
    try:
        y = int(year)
    except (TypeError, ValueError):
        return ""
    if y <= 0:
        return ""
    return (
        f"drawtext=fontfile={FONT}:text='{y}':expansion=none:fontsize=150:"
        f"fontcolor=0xFFD23C:borderw=9:bordercolor=black:"
        f"x=(w-text_w)/2:y={int(h * 0.07)}"
    )


def make_clip(image: str, audio: str, out: str, w: int, h: int, text: str = "",
              cal: dict | None = None, year=None, zoom: bool = True, frames: bool = False) -> None:
    """cal = hasil mascot.prepare(); bila None, klip tanpa maskot. zoom=False: latar diam (untuk grafik/angka).
    frames=True: image adalah pola urutan bingkai (mis. dir/f_%03d.png) yang diperpanjang sampai audio selesai."""
    dur = _duration(audio)
    base = os.path.splitext(out)[0]
    # Latar: zoom pelan (Ken Burns) selama durasi audio.
    if frames:
        bg = (
            f"[0:v]fps=30,tpad=stop_mode=clone:stop_duration={dur + 1:.2f},"
            f"scale={w}:{h},format=yuv420p"
        )
    elif zoom:
        bg = (
            f"[0:v]scale={w*2}:{h*2}:force_original_aspect_ratio=increase,"
            f"crop={w*2}:{h*2},"
            f"zoompan=z='min(zoom+0.0008,1.15)':d=1:s={w}x{h}:fps=30,"
            "format=yuv420p"
        )
    else:  # grafik tidak boleh terpotong oleh zoom
        bg = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},fps=30,format=yuv420p"
        )
    inputs = ["-framerate", "30", "-i", image] if frames else ["-loop", "1", "-framerate", "30", "-i", image]
    graph, last = [], "bg"

    if cal:
        x0 = (w - cal["w"]) // 2
        y0 = h - cal["h"] - 200  # sisakan ruang untuk tombol/judul Shorts di bawah
        bob = f"{y0}+{BOB}*sin(2*PI*t/{BOB_PERIOD})"
        speak = mascot.expr(mascot.speech_intervals(audio))
        blink = mascot.expr(mascot.blink_intervals(dur))
        for k in ("base", "mouth", "blink", "blinkmouth"):
            inputs += ["-loop", "1", "-framerate", "30", "-i", cal[k]]
        fx, fy = x0 + cal["face_x"], f"{bob}+{cal['face_y']}"
        graph.append(bg + "[bg]")
        graph.append(f"[bg][1:v]overlay=x={x0}:y='{bob}':format=auto[a]")
        graph.append(f"[a][2:v]overlay=x={fx}:y='{fy}':enable='{speak}*(1-{blink})':format=auto[b]")
        graph.append(f"[b][3:v]overlay=x={fx}:y='{fy}':enable='(1-{speak})*{blink}':format=auto[c]")
        graph.append(f"[c][4:v]overlay=x={fx}:y='{fy}':enable='{speak}*{blink}':format=auto[d]")
        last = "d"
    else:
        graph.append(bg + "[bg]")

    tail = [f for f in (_year_filter(year, h), _subtitle_filters(text, dur, w, h, base)) if f]
    tail.append("format=yuv420p")
    graph.append(f"[{last}]" + ",".join(tail) + "[v]")

    audio_idx = inputs.count("-i")  # jumlah input video; audio ada tepat sesudahnya
    _run(
        ["ffmpeg", "-y", *inputs, "-i", audio,
         "-filter_complex", ";".join(graph),
         "-map", "[v]", "-map", f"{audio_idx}:a",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-t", f"{dur:.3f}", "-r", "30", out]
    )


def concat(clips: list[str], listfile: str, out: str) -> None:
    with open(listfile, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", out])
