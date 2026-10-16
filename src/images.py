"""Gambar per scene: Cloudflare -> Hugging Face (FLUX) -> Pollinations."""
import base64
import os
import random
import time
import urllib.parse
import requests

STYLE = "flat comic illustration, vibrant colors, clean lines, no text, no watermark, "
CF_MODEL = os.environ.get("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
HF_MODEL = "black-forest-labs/FLUX.1-schnell"  # Model gratis tercepat & terbaik di HF

CF_WAITS = [10, 30]
HF_WAITS = [5, 15]       # HF jarang perlu retry lama
POLL_WAITS = [15, 30]


def _cloudflare(prompt: str, path: str) -> None:
    acc = os.environ.get("CF_ACCOUNT_ID")
    tok = os.environ.get("CF_API_TOKEN")
    if not acc or not tok:
        raise RuntimeError("CF credentials missing")
        
    r = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{CF_MODEL}",
        headers={"Authorization": f"Bearer {tok}"},
        json={"prompt": STYLE + prompt, "steps": 4}, # steps 4 cukup untuk schnell
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
        raise RuntimeError("HF_TOKEN missing")
        
    api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"inputs": STYLE + prompt, "parameters": {"num_inference_steps": 4}}
    
    r = requests.post(api_url, headers=headers, json=payload, timeout=90)
    
    # Handle rate limiting spesifik HF
    if r.status_code == 503:
        estimated_time = r.json().get("estimated_time", 10)
        raise RuntimeError(f"HF Model loading, wait {estimated_time}s")
    if r.status_code == 429:
        raise RuntimeError("Hugging Face rate limit exceeded")
    if r.status_code != 200:
        raise RuntimeError(f"Hugging Face HTTP {r.status_code}: {r.text[:150]}")
        
    with open(path, "wb") as f:
        f.write(r.content)


def _pollinations(prompt: str, path: str, width: int, height: int) -> None:
    # Tambahkan random seed dan noCache untuk menghindari hasil yang di-cache/error
    seed = random.randint(1, 999999)
    safe_prompt = urllib.parse.quote(STYLE + prompt)
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={width}&height={height}&nologo=true&seed={seed}&noCache=true"
    
    # Gunakan headers User-Agent agar tidak di-block oleh GitHub Actions IP
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    r = requests.get(url, headers=headers, timeout=90)
    
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
        with open(path, "wb") as f:
            f.write(r.content)
        return
    raise RuntimeError(f"Pollinations HTTP {r.status_code}")


def _is_quota_error(err_msg: str) -> bool:
    err_msg = err_msg.lower()
    return "daily free allocation" in err_msg or "quota" in err_msg or "http 402" in err_msg or "rate limit" in err_msg


def _try(fn, waits, name: str) -> bool:
    last = None
    for wait in [0] + waits:
        if wait:
            print(f"{name} gagal ({last}). Tunggu {wait} detik...", flush=True)
            time.sleep(wait)
        try:
            fn()
            print(f"✅ {name} berhasil.", flush=True)
            return True
        except Exception as e:  # noqa: BLE001
            last = str(e)[:150]
            if _is_quota_error(last):
                print(f"⛔ {name} kuota/limit habis. Langsung skip.", flush=True)
                return False
                
    print(f"❌ {name} menyerah: {last}", flush=True)
    return False


def make_image(prompt: str, path: str, width: int, height: int) -> None:
    # 1. Coba Cloudflare (Jika ada kredensialnya)
    if os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"):
        if _try(lambda: _cloudflare(prompt, path), CF_WAITS, "Cloudflare"):
            return
        print("➡️ Pindah ke Hugging Face...", flush=True)

    # 2. Coba Hugging Face (Gratis & Stabil)
    if os.environ.get("HF_TOKEN"):
        if _try(lambda: _huggingface(prompt, path), HF_WAITS, "HuggingFace"):
            return
        print("➡️ Pindah ke Pollinations...", flush=True)

    # 3. Fallback terakhir: Pollinations
    if _try(lambda: _pollinations(prompt, path, width, height), POLL_WAITS, "Pollinations"):
        return
        
    raise RuntimeError("Semua penyedia gambar gagal. Cek log di atas.")