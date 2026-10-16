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
HF_WAITS = [10, 20]
POLL_WAITS = [15, 30]

# ⭐ INGAT API TERAKHIR YANG BERHASIL AGAR SCENE BERIKUTNYA LEBIH CEPAT
LAST_SUCCESSFUL_PROVIDER = None


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
        # ⭐ LOG EKSPLESIF: Agar tidak silent error jika lupa set secret
        raise RuntimeError("HF_TOKEN TIDAK DITEMUKAN di GitHub Secrets! Cek Settings > Secrets.")
        
    api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"inputs": STYLE + prompt, "parameters": {"num_inference_steps": 4}}
    
    r = requests.post(api_url, headers=headers, json=payload, timeout=90)
    
    if r.status_code == 503:
        est = r.json().get("estimated_time", 15)
        raise RuntimeError(f"HF Model sedang loading, estimasi {est} detik")
    if r.status_code == 401:
        raise RuntimeError("HF Token tidak valid atau expired")
    if r.status_code == 429:
        raise RuntimeError("Hugging Face rate limit/kuota harian tercapai")
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
    print("🎨 Menggunakan fallback gambar lokal (Pillow)...", flush=True)
    img = Image.new("RGB", (width, height), color=(30, 30, 40))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except OSError:
        font = ImageFont.load_default()

    for y in range(height):
        r_val = int(30 + (y / height) * 40)
        draw.line([(0, y), (width, y)], fill=(r_val, r_val, r_val + 20))

    short_prompt = (STYLE + prompt)[:150] + "..."
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
    err_msg = err_msg.lower()
    return any(x in err_msg for x in [
        "daily free allocation", "quota", "http 402", "http 401", "http 403",
        "token tidak ditemukan", "token tidak valid", "free limit reached"
    ])


def _try(fn, waits, name: str) -> bool:
    global LAST_SUCCESSFUL_PROVIDER
    last = None
    for wait in [0] + waits:
        if wait:
            print(f"⏳ {name} menunggu {wait} detik sebelum retry...", flush=True)
            time.sleep(wait)
        try:
            fn()
            print(f"✅ {name} berhasil.", flush=True)
            LAST_SUCCESSFUL_PROVIDER = name  # ⭐ SIMPAN PENYEDIA YANG BERHASIL
            return True
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            print(f"⚠️ {name} error: {last}", flush=True)
            
            if _is_hard_fail(last):
                print(f"⛔ {name} gagal permanen (kuota/auth). Skip retry.", flush=True)
                return False
                
    print(f"❌ {name} menyerah setelah semua retry.", flush=True)
    return False


def make_image(prompt: str, path: str, width: int, height: int) -> None:
    global LAST_SUCCESSFUL_PROVIDER
    
    # 1. Susun daftar penyedia yang tersedia
    providers = []
    if os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"):
        providers.append(("Cloudflare", lambda: _cloudflare(prompt, path), CF_WAITS))
    if os.environ.get("HF_TOKEN"):
        providers.append(("HuggingFace", lambda: _huggingface(prompt, path), HF_WAITS))
    providers.append(("Pollinations", lambda: _pollinations(prompt, path, width, height), POLL_WAITS))
    
    # 2. ⭐ PRIORITASKAN API TERAKHIR YANG BERHASIL (Pindah ke indeks 0)
    if LAST_SUCCESSFUL_PROVIDER:
        for i, (name, fn, waits) in enumerate(providers):
            if name == LAST_SUCCESSFUL_PROVIDER:
                providers.insert(0, providers.pop(i))
                print(f"⚡ Scene berikutnya memprioritaskan {LAST_SUCCESSFUL_PROVIDER} (berhasil sebelumnya).", flush=True)
                break

    # 3. Coba satu per satu
    for name, fn, waits in providers:
        if _try(fn, waits, name):
            return

    # 4. Fallback terakhir
    print("⚠️ Semua AI gambar gagal. Menggunakan fallback lokal...", flush=True)
    _fallback_pillow(prompt, path, width, height)