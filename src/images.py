"""Gambar per scene: Cloudflare Workers AI (utama) lalu Pollinations (cadangan)."""
import base64
import os
import random
import time
import urllib.parse
import requests

STYLE = "flat comic illustration, vibrant colors, clean lines, no text, no watermark, "
CF_MODEL = os.environ.get("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
CF_WAITS = [10, 30]
POLL_WAITS = [15, 30, 60, 120]


def _cloudflare(prompt: str, path: str) -> None:
    acc = os.environ["CF_ACCOUNT_ID"]
    tok = os.environ["CF_API_TOKEN"]
    r = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{CF_MODEL}",
        headers={"Authorization": f"Bearer {tok}"},
        json={"prompt": STYLE + prompt, "steps": 6},
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Cloudflare HTTP {r.status_code}: {r.text[:200]}")
    if r.headers.get("content-type", "").startswith("image"):
        data = r.content
    else:
        data = base64.b64decode(r.json()["result"]["image"])
    with open(path, "wb") as f:
        f.write(data)


def _pollinations(prompt: str, path: str, width: int, height: int) -> None:
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(STYLE + prompt)
    params = {"width": width, "height": height, "nologo": "true", "seed": random.randint(1, 10**6)}
    r = requests.get(url, params=params, timeout=120)
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
        with open(path, "wb") as f:
            f.write(r.content)
        return
    raise RuntimeError(f"Pollinations HTTP {r.status_code}")


def _try(fn, waits, name: str) -> bool:
    last = None
    for wait in [0] + waits:
        if wait:
            print(f"{name} gagal ({last}). Coba lagi {wait} detik...", flush=True)
            time.sleep(wait)
        try:
            fn()
            return True
        except Exception as e:  # noqa: BLE001
            last = str(e)[:120]
    print(f"{name} menyerah: {last}", flush=True)
    return False


def make_image(prompt: str, path: str, width: int, height: int) -> None:
    if os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"):
        if _try(lambda: _cloudflare(prompt, path), CF_WAITS, "Cloudflare"):
            return
        print("Pindah ke Pollinations...", flush=True)
    if _try(lambda: _pollinations(prompt, path, width, height), POLL_WAITS, "Pollinations"):
        time.sleep(4)
        return
    raise RuntimeError("Semua penyedia gambar gagal")