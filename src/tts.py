"""Narasi: edge-tts (utama) -> Piper offline -> gTTS (cadangan)."""
import asyncio
import os
import subprocess
import sys
import time

import edge_tts
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE_DIR = os.path.join(ROOT, "voices")
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/"
PIPER_FILES = ("en_US-lessac-medium.onnx", "en_US-lessac-medium.onnx.json")


def _edge(text: str, voice: str, path: str) -> None:
    async def go():
        await edge_tts.Communicate(text, voice).save(path)

    asyncio.run(go())


def _piper(text: str, path: str) -> None:
    os.makedirs(VOICE_DIR, exist_ok=True)
    for fn in PIPER_FILES:
        dst = os.path.join(VOICE_DIR, fn)
        if not os.path.exists(dst):
            r = requests.get(PIPER_BASE + fn, timeout=300)
            r.raise_for_status()
            with open(dst, "wb") as f:
                f.write(r.content)
    model = os.path.join(VOICE_DIR, PIPER_FILES[0])
    wav = path + ".wav"
    subprocess.run(
        [sys.executable, "-m", "piper", "-m", model, "-f", wav],
        input=text.encode("utf-8"), check=True, capture_output=True,
    )
    subprocess.run(["ffmpeg", "-y", "-i", wav, path], check=True, capture_output=True)
    os.remove(wav)


def _gtts(text: str, voice: str, path: str) -> None:
    from gtts import gTTS

    gTTS(text, lang=voice.split("-")[0]).save(path)


def make_voice(text: str, voice: str, path: str) -> None:
    last = None
    for wait in (0, 5, 15):  # edge-tts: 3 percobaan
        if wait:
            time.sleep(wait)
        try:
            _edge(text, voice, path)
            return
        except Exception as e:  # noqa: BLE001
            last = type(e).__name__
    print(f"edge-tts gagal ({last}). Pakai Piper...", flush=True)
    try:
        _piper(text, path)
        return
    except Exception as e:  # noqa: BLE001
        print(f"Piper gagal ({str(e)[:150]}). Pakai gTTS...", flush=True)
    _gtts(text, voice, path)