"""Generate gambar per scene lewat Pollinations.ai (gratis) dengan retry sabar."""
import random
import time
import urllib.parse
import requests

STYLE = "flat comic illustration, vibrant colors, clean lines, no text, no watermark, "
WAITS = [20, 45, 90, 150, 240]  # detik; total tunggu maks ~9 menit


def make_image(prompt: str, path: str, width: int, height: int) -> None:
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(STYLE + prompt)
    last = None
    for wait in [0] + WAITS:
        if wait:
            print(f"Gambar gagal ({last}). Coba lagi {wait} detik...", flush=True)
            time.sleep(wait)
        params = {"width": width, "height": height, "nologo": "true", "seed": random.randint(1, 10**6)}
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                with open(path, "wb") as f:
                    f.write(r.content)
                time.sleep(4)  # beri jeda antar permintaan
                return
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)
    raise RuntimeError(f"Gagal generate gambar setelah banyak percobaan: {last}")