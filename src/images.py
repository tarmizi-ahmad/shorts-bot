"""Gambar latar per scene: Cloudflare -> Pollinations -> pakai ulang gambar sukses -> latar lokal (tanpa teks).

Hugging Face SUDAH DIHAPUS: endpoint lama api-inference.huggingface.co sudah mati (domain tidak ada),
dan FLUX.1-schnell dicabut dari layanan HF; akun gratis juga tidak punya kredit bulanan.
"""
import base64
import hashlib
import os
import random
import shutil
import time
import urllib.parse
import requests
from PIL import Image, ImageDraw

STYLE = "flat comic illustration, vibrant colors, clean lines, no text, no watermark, "
CF_MODEL = os.environ.get("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell")

CF_WAITS = [10, 30]
POLL_WAITS = [45, 45]   # Pollinations anonim: ~1 gambar per 40 detik
POLL_GAP = 45
MAX_GIVEUPS = 2         # provider yang menyerah 2x berturut-turut ikut di-blacklist

# STATE GLOBAL: ingat provider yang berhasil, yang sudah limit, dan gambar sukses terakhir
LAST_SUCCESSFUL_PROVIDER = None
FAILED_PROVIDERS: set = set()
LAST_GOOD_IMAGE = None
LAST_POLL_TS = 0.0
GIVEUPS: dict = {}


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


def _pollinations(prompt: str, path: str, width: int, height: int) -> None:
    global LAST_POLL_TS
    gap = POLL_GAP - (time.time() - LAST_POLL_TS)
    if gap > 0:  # patuhi batas ~1 gambar/40 detik supaya tidak kena 402
        print(f"⏳ Pollinations: jeda {gap:.0f} detik (batas anonim)...", flush=True)
        time.sleep(gap)
    seed = random.randint(1, 999999)
    safe_prompt = urllib.parse.quote(STYLE + prompt)
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={width}&height={height}&nologo=true&seed={seed}&noCache=true"

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=90)
    LAST_POLL_TS = time.time()

    if r.status_code == 402:  # batas laju sementara, BUKAN gagal permanen
        print("ℹ️ Pollinations 402:", r.text[:300], flush=True)
        raise RuntimeError("Pollinations kena batas laju, coba lagi nanti")
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
        with open(path, "wb") as f:
            f.write(r.content)
        return
    raise RuntimeError(f"Pollinations HTTP {r.status_code}: {r.text[:300]}")


def _local_background(prompt: str, path: str, width: int, height: int) -> None:
    """Latar buatan sendiri (gradasi + siluet kota/bukit), TANPA teks. Warna acak tapi tetap per prompt."""
    print("🎨 Membuat latar lokal (tanpa teks)...", flush=True)
    rnd = random.Random(int(hashlib.md5(prompt.encode()).hexdigest(), 16))
    hue = [(48, 70, 130), (120, 60, 90), (40, 100, 110), (130, 90, 50), (70, 60, 120)]
    top = rnd.choice(hue)
    bottom = tuple(min(255, c + 110) for c in top)
    img = Image.new("RGB", (width, height))
    d = ImageDraw.Draw(img)
    for y in range(height):
        k = y / height
        d.line([(0, y), (width, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
    # matahari/bulan besar
    r = width // 5
    cx, cy = rnd.randint(width // 4, width * 3 // 4), int(height * 0.28)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(min(255, c + 150) for c in top))
    # dua lapis siluet bangunan di sepertiga bawah
    for layer, shade in enumerate((0.55, 0.35)):
        base = int(height * (0.70 + layer * 0.08))
        col = tuple(int(c * shade) for c in top)
        x = 0
        while x < width:
            bw = rnd.randint(width // 14, width // 6)
            bh = rnd.randint(height // 14, height // 5)
            d.rectangle([x, base - bh, x + bw, height], fill=col)
            x += bw
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
            LAST_SUCCESSFUL_PROVIDER = name
            GIVEUPS[name] = 0
            return True
        except Exception as e:  # noqa: BLE001
            last = str(e)[:300]
            print(f"⚠️ {name} error: {last}", flush=True)

            if _is_hard_fail(last):
                print(f"⛔ {name} gagal permanen (kuota/auth). Skip retry & masuk blacklist.", flush=True)
                FAILED_PROVIDERS.add(name)
                if LAST_SUCCESSFUL_PROVIDER == name:
                    LAST_SUCCESSFUL_PROVIDER = None
                return False

    print(f"❌ {name} menyerah setelah semua retry.", flush=True)
    GIVEUPS[name] = GIVEUPS.get(name, 0) + 1
    if GIVEUPS[name] >= MAX_GIVEUPS:
        print(f"⛔ {name} menyerah {GIVEUPS[name]}x berturut-turut, masuk blacklist.", flush=True)
        FAILED_PROVIDERS.add(name)
    return False


def make_image(prompt: str, path: str, width: int, height: int) -> None:
    global LAST_GOOD_IMAGE

    providers = []
    if os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"):
        providers.append(("Cloudflare", lambda: _cloudflare(prompt, path), CF_WAITS))
    else:
        print("ℹ️ Cloudflare dilewati: CF_ACCOUNT_ID/CF_API_TOKEN tidak diset.", flush=True)
    providers.append(("Pollinations", lambda: _pollinations(prompt, path, width, height), POLL_WAITS))

    # Buang provider yang sudah limit hari ini
    skipped = [n for (n, _, _) in providers if n in FAILED_PROVIDERS]
    providers = [(n, f, w) for (n, f, w) in providers if n not in FAILED_PROVIDERS]
    if skipped:
        print(f"⚠️ Dilewati (sudah limit): {skipped}", flush=True)

    # Prioritaskan provider yang terakhir berhasil
    if LAST_SUCCESSFUL_PROVIDER:
        for i, (name, _, _) in enumerate(providers):
            if name == LAST_SUCCESSFUL_PROVIDER:
                providers.insert(0, providers.pop(i))
                break

    for name, fn, waits in providers:
        if _try(fn, waits, name):
            LAST_GOOD_IMAGE = path
            return

    # Semua AI gagal: pakai ulang gambar sukses sebelumnya (latar era yang sama), Ken Burns tetap bergerak
    if LAST_GOOD_IMAGE and os.path.exists(LAST_GOOD_IMAGE):
        print("♻️ Semua AI gambar gagal. Memakai ulang gambar sukses sebelumnya.", flush=True)
        shutil.copyfile(LAST_GOOD_IMAGE, path)
        return

    print("⚠️ Semua AI gambar gagal. Memakai latar lokal...", flush=True)
    _local_background(prompt, path, width, height)