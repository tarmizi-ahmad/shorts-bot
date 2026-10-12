"""Rangkai gambar + narasi + subtitle jadi video vertikal 9:16 dengan FFmpeg."""
import os
import subprocess

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


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
    """drawtext per potongan pendek, waktu sebanding panjang huruf."""
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
            f"x=(w-text_w)/2:y={int(h * 0.68)}:"
            f"enable='between(t,{t:.2f},{t + d:.2f})'"
        )
        t += d
    return "," + ",".join(filters)


def make_clip(image: str, audio: str, out: str, w: int, h: int, text: str = "") -> None:
    dur = _duration(audio)
    # Zoom pelan (Ken Burns) selama durasi audio.
    vf = (
        f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,"
        f"crop={w*2}:{h*2},"
        f"zoompan=z='min(zoom+0.0008,1.15)':d=1:s={w}x{h}:fps=30,"
        "format=yuv420p"
    )
    if text:
        vf += _subtitle_filters(text, dur, w, h, os.path.splitext(out)[0])
    _run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", image, "-i", audio,
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-r", "30", out,
        ]
    )


def concat(clips: list[str], listfile: str, out: str) -> None:
    with open(listfile, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", out])