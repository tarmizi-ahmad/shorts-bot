"""Generate gambar per scene lewat Pollinations.ai (gratis, tanpa API key)."""
import time
import urllib.parse
import requests

STYLE = "flat comic illustration, vibrant colors, clean lines, no text, no watermark, "


def make_image(prompt: str, path: str, width: int, height: int, retries: int = 4) -> None:
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(STYLE + prompt)
    params = {"width": width, "height": height, "nologo": "true", "model": "flux"}
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                with open(path, "wb") as f:
                    f.write(r.content)
                return
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Gagal generate gambar: {last}")
