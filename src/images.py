"""Gambar per scene: Cloudflare -> Hugging Face -> Pollinations -> Fallback Lokal (Pillow)."""
import base64
import os
import random
import time
import urllib.parse
import requests
from PIL import Image, ImageDraw, ImageFont

STYLE = "flat comic illustration, vibrant colors, clean lines, no text, no watermark, "
CF_MODEL = os.environ.get("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
HF_MODEL = "black-forest-labs/FLUX.1-schnell"

CF_WAITS = [10, 30]
HF_WAITS = [10, 20]  # HF butuh waktu jika model sedang "cold start"
POLL_WAITS = [15, 30]


def _cloudflare(prompt: str, path: str) -> None:
    acc = os.environ.get("CF_ACCOUNT_ID")
    tok = os.environ.get("CF_API_TOKEN")
    if not acc or not tok:
        raise RuntimeError("CF credentials missing")
        
    r = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{CF_MODEL}",
        headers={"Authorization": f"Bearer {tok}"},
        json={"prompt": STYLE + prompt, "steps": 4},
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Cloudflare HTTP {r.status_code}: {r.text[:150]}")
    
    if r.headers.get("content-type", "").startswith("image"):
        data = r.content
    else:
        data = base64.b64decode(r.json()["result"]["image"])
    
    with open(path, "wb") as f:
        f.write(data)


def _huggingface(prompt: str, path: str) -> None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN tidak ditemukan di GitHub Secrets!")
        
    api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"inputs": STYLE + prompt, "parameters": {"num_inference_steps": 4}}
    
    r = requests.post(api_url, headers=headers, json=payload, timeout=90)
    
    if r.status_code == 503:
        est = r.json().get("estimated_time", 15)
        raise RuntimeError(f"HF Model sedang loading, estimasi {est} detik")
    if r.status_code == 401:
        raise RuntimeError("HF Token tidak valid/expired")
    if r.status_code == 429:
        raise RuntimeError("Hugging Face rate limit/kuota tercapai")
    if r.status_code != 200:
        raise RuntimeError(f"HF HTTP {r.status_code}: {r.text[:150]}")
        
    with open(path, "wb") as f:
        f.write(r.content)


def _pollinations(prompt: str, path: str, width: int, height: int) -> None:
    seed = random.randint(1, 999999)
    safe_prompt = urllib.parse.quote(STYLE + prompt)
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={width}&height={height}&nologo=true&seed={seed}&noCache=true"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=90)
    
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
        with open(path, "wb") as f:
            f.write(r.content)
        return
    raise RuntimeError(f"Pollinations HTTP {r.status_code}: {r.text[:100]}")


def _fallback_pillow(prompt: str, path: str, width: int, height: int) -> None:
    """Fallback terakhir: Buat gambar gradient sederhana dengan teks prompt jika semua AI gagal."""
    print("🎨 Menggunakan fallback gambar lokal (Pillow)...", flush=True)
    img = Image.new("RGB", (width, height), color=(30, 30, 40))
    draw = ImageDraw.Draw(img)
    
    # Coba pakai font default, jika tidak ada pakai default PIL
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except OSError:
        font = ImageFont.load_default()

    # Buat gradient sederhana
    for y in range(height):
        r = int(30 + (y / height) * 40)
        draw.line([(0, y), (width, y)], fill=(r, r, r + 20))

    # Tulis teks prompt (dipotong agar muat)
    short_prompt = (STYLE + prompt)[:150] + "..."
    # Text wrapping sederhana
    words = short_prompt.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) < 40:
            current += word + " "
        else:
            lines.append(current)
            current = word + " "
    lines.append(current)

    y_text = height // 2 - (len(lines) * 25)
    for line in lines:
        draw.text((width // 2, y_text), line.strip(), font=font, fill=(255, 255, 255), anchor="mm")
        y_text += 50

    img.save(path)


def _is_hard_fail(err_msg: str) -> bool:
    """True jika error ini TIDAK AKAN SEMBUH dengan retry (misal: auth, kuota habis)."""
    err_msg = err_msg.lower()
    return any(x in err_msg for x in [
        "daily free allocation", "quota", "http 402", "http 401", "http 403",
        "token tidak ditemukan", "token tidak valid"
    ])


def _try(fn, waits, name: str) -> bool:
    last = None
    for wait in [0] + waits:
        if wait:
            print(f"⏳ {name} menunggu {wait} detik sebelum retry...", flush=True)
            time.sleep(wait)
        try:
            fn()
            print(f"✅ {name} berhasil.", flush=True)
            return True
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            print(f"⚠️ {name} error: {last}", flush=True)
            
            # Jika error ini jenis "hard fail" (kuota/auth), jangan buang waktu retry
            if _is_hard_fail(last):
                print(f"⛔ {name} gagal permanen (kuota/auth). Skip retry.", flush=True)
                return False
                
    print(f"❌ {name} menyerah setelah semua retry.", flush=True)
    return False


def make_image(prompt: str, path: str, width: int, height: int) -> None:
    # 1. Cloudflare
    if os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"):
        if _try(lambda: _cloudflare(prompt, path), CF_WAITS, "Cloudflare"):
            return
        print("➡️ Pindah ke Hugging Face...", flush=True)

    # 2. Hugging Face
    if os.environ.get("HF_TOKEN"):
        if _try(lambda: _huggingface(prompt, path), HF_WAITS, "HuggingFace"):
            return
        print("➡️ Pindah ke Pollinations...", flush=True)

    # 3. Pollinations
    if _try(lambda: _pollinations(prompt, path, width, height), POLL_WAITS, "Pollinations"):
        return

    # 4. FALLBACK LOKAL (PASTI SUKSES)
    print("⚠️ Semua AI gambar gagal. Menggunakan fallback lokal...", flush=True)
    _fallback_pillow(prompt, path, width, height)