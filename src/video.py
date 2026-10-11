"""Rangkai gambar + narasi jadi video vertikal 9:16 dengan FFmpeg."""
import subprocess


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def make_clip(image: str, audio: str, out: str, w: int, h: int) -> None:
    # Zoom pelan (Ken Burns) selama durasi audio.
    vf = (
        f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,"
        f"crop={w*2}:{h*2},"
        f"zoompan=z='min(zoom+0.0008,1.15)':d=1:s={w}x{h}:fps=30,"
        "format=yuv420p"
    )
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
