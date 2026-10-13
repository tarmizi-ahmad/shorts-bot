"""Narasi offline dengan Piper (gratis, tanpa API). Cadangan: gTTS.

Suara dipilih lewat "voice" di config.json, contoh: "en_US-ryan-high".
Nama edge-tts lama (mis. "en-US-AriaNeural") otomatis diganti ke suara default.
"""
import os
import re
import subprocess
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE_DIR = os.path.join(ROOT, "voices")
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
DEFAULT_VOICE = "en_US-ryan-high"
FALLBACK_VOICES = ["en_US-lessac-high", "en_US-lessac-medium"]

# Pengaturan gaya bicara (default Piper: length 1.0, noise 0.667, noise_w 0.8)
LENGTH_SCALE = "1.05"      # >1 = sedikit lebih pelan & tenang, cocok untuk bercerita
NOISE_SCALE = "0.75"       # variasi intonasi
NOISE_W_SCALE = "0.9"      # variasi ritme/durasi
SENTENCE_SILENCE = "0.3"   # jeda antar kalimat (detik)

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
        "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _two(n: int) -> str:
    if n < 20:
        return ONES[n]
    return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])


def _year_words(y: int) -> str:
    if y % 1000 == 0:
        return f"{ONES[y // 1000]} thousand"
    if 2000 < y < 2010:
        return f"two thousand {ONES[y % 10]}"
    hi, lo = divmod(y, 100)
    if lo == 0:
        return f"{_two(hi)} hundred"
    if lo < 10:
        return f"{_two(hi)} oh {ONES[lo]}"
    return f"{_two(hi)} {_two(lo)}"


def clean_text(text: str) -> str:
    """Rapikan teks agar dibaca lebih alami (tahun jadi kata, simbol, tanda baca)."""
    t = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    t = re.sub(r"(?<![\d$])(?<!\d,)\b(1\d{3}|20\d{2})\b(?!\d|,\d|%)", lambda m: _year_words(int(m.group(1))), t)
    t = t.replace("&", " and ").replace("%", " percent")
    t = re.sub(r"[*_#`~^]", "", t)
    t = re.sub(r"\s*[\u2014\u2013]\s*|\s+-\s+", ", ", t).replace("...", ".")
    t = re.sub(r"\s+", " ", t).strip()
    if t and t[-1] not in ".!?":
        t += "."
    return t


def _voice_files(name: str):
    m = re.fullmatch(r"([a-z]{2})_([A-Z]{2})-(.+)-(x_low|low|medium|high)", name)
    if not m:
        raise ValueError(f"Nama suara Piper tidak valid: {name}")
    lang, region, spk, quality = m.groups()
    return f"{lang}/{lang}_{region}/{spk}/{quality}/{name}"


def _download(url: str, dest: str) -> None:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest + ".part", "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    os.replace(dest + ".part", dest)


def _ensure_model(name: str) -> str:
    os.makedirs(VOICE_DIR, exist_ok=True)
    onnx = os.path.join(VOICE_DIR, f"{name}.onnx")
    cfg = onnx + ".json"
    if not (os.path.exists(onnx) and os.path.exists(cfg)):
        base = f"{HF}/{_voice_files(name)}"
        print(f"Unduh suara Piper {name} ...", flush=True)
        _download(base + ".onnx.json", cfg)
        _download(base + ".onnx", onnx)
    return onnx


def _load_model(preferred: str) -> str:
    names = [preferred] + [v for v in FALLBACK_VOICES if v != preferred]
    last = None
    for n in names:
        try:
            return _ensure_model(n)
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"Suara {n} gagal diunduh: {e}")
    raise RuntimeError(f"Tidak ada suara Piper yang bisa dipakai: {last}")


def _run_piper(model: str, text: str, wav: str) -> None:
    base = [sys.executable, "-m", "piper", "-m", model, "-f", wav]
    tuned = base + ["--length-scale", LENGTH_SCALE, "--noise-scale", NOISE_SCALE,
                    "--noise-w-scale", NOISE_W_SCALE, "--sentence-silence", SENTENCE_SILENCE]
    r = subprocess.run(tuned, input=text, text=True, capture_output=True)
    if r.returncode != 0:
        # Versi Piper yang tidak mengenal salah satu opsi -> ulangi tanpa penyetelan.
        print("Piper dengan penyetelan gagal, coba pengaturan standar:", r.stderr[-200:])
        subprocess.run(base, input=text, text=True, check=True, capture_output=True)


def _polish(wav: str, mp3: str) -> None:
    """Rapikan suara: buang dengung rendah, kompres ringan, samakan volume."""
    af = "highpass=f=70,acompressor=threshold=-18dB:ratio=2.5:attack=5:release=120,loudnorm=I=-16:TP=-1.5:LRA=9"
    subprocess.run(
        ["ffmpeg", "-y", "-i", wav, "-af", af, "-ar", "44100", "-ac", "1", "-b:a", "192k", mp3],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )


def _piper(text: str, voice: str, path: str) -> None:
    name = voice if re.fullmatch(r"[a-z]{2}_[A-Z]{2}-.+-(x_low|low|medium|high)", voice or "") else DEFAULT_VOICE
    model = _load_model(name)
    wav = os.path.splitext(path)[0] + ".wav"
    _run_piper(model, clean_text(text), wav)
    _polish(wav, path)


def _gtts(text: str, path: str) -> None:
    from gtts import gTTS

    gTTS(clean_text(text), lang="en").save(path)


def make_voice(text: str, voice: str, path: str) -> None:
    try:
        _piper(text, voice, path)
    except Exception as e:  # noqa: BLE001
        print("Piper gagal:", e, "-> pakai gTTS")
        _gtts(text, path)