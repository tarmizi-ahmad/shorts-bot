"""Buat naskah + prompt gambar orisinal. Mode: history_fact (jawaban/fakta) & history_trivia (tebak-tebakan)."""
import json
import os
import re
import time
import requests

LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
SKIP = ("image", "tts", "live", "audio", "lite", "exp", "embedding", "robotics",
        "omni", "preview", "thinking", "customtools")
RETRY_STATUS = (429, 500, 502, 503, 504)

PROMPT = """Kamu penulis naskah YouTube Shorts dalam bahasa {language} untuk audiens {country}.
Niche channel: {niche}
Sudut pandang khas channel: {angle}

Topik: "{topic}" (kata kunci: {tags}).
{facts_block}{character_block}{era_block}
ATURAN ISI (penting untuk kualitas & orisinalitas):
- Jangan menyalin judul/kalimat sumber, jangan sebut nama channel, jangan pakai lirik,
  kutipan panjang, atau karakter berhak cipta.
- Jangan membuat klaim fakta yang tidak pasti tentang orang nyata.
- Jangan mengarang tanggal, angka, nama, atau kutipan.
- Bukan sekadar menceritakan ulang. Wajib ada NILAI TAMBAH.
- Jika topik tidak cocok dengan niche, cari sudut yang cocok.

{custom_structure}
- Kalimat pendek, ritme cepat, tanpa basa-basi.
{era_story}
Balas HANYA JSON dengan bentuk:
{{
{era_fields}  "hook_title": "{title_rule}",
  "description": "deskripsi 2 kalimat + 3 hashtag{desc_rule}",
  "tags": ["tag1", "tag2", "tag3"],
  "scenes": [
    {{"narration": "1-2 kalimat narasi singkat dalam {language}", "image_prompt": "maks 25 kata, bahasa Inggris, {image_rule}"}}
  ]
}}
Jumlah scenes: tepat {n}. Total narasi sekitar 40-50 detik bila dibaca."""


def list_models(key: str) -> list[str]:
    forced = os.environ.get("GEMINI_MODEL")
    if forced:
        return [forced]
    r = requests.get(LIST_URL, params={"key": key, "pageSize": 200}, timeout=30)
    r.raise_for_status()
    names = []
    for m in r.json().get("models", []):
        name = m["name"].split("/")[-1]
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if "flash" not in name or any(s in name for s in SKIP):
            continue
        names.append(name)
    if not names:
        raise RuntimeError("Tidak ada model flash yang cocok")

    def ver(n: str) -> float:
        m = re.search(r"(\d+(?:\.\d+)?)", n)
        return float(m.group(1)) if m else 0.0

    return sorted(names, key=ver, reverse=True)[:3]


SERIES = "What Happened Today"


def make_title(hook: str, topic: dict) -> str:
    hook = hook.strip().strip('"').rstrip(".!?:")
    label = topic.get("date_label")
    if not label:
        return hook[:85]
    tail = f" | {SERIES} ({label})"
    room = 85 - len(tail)
    if len(hook) > room:
        hook = hook[:room].rsplit(" ", 1)[0]
    return hook + tail


# Penyedia teks yang gagal PERMANEN di run ini (kuota harian habis / model tidak ada / kunci salah).
# Disimpan di level modul, jadi profil berikutnya di run yang sama tidak memanggilnya lagi.
DEAD: set = set()

# Urutan kesukaan model Groq. llama-3.3-70b-versatile sudah dipensiunkan Groq (16 Agustus 2026).
GROQ_PREFER = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b",
               "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
GROQ_SKIP = ("whisper", "guard", "tts", "orpheus", "compound", "playai", "distil", "embed")


def _gemini(prompt: str):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    try:
        models = list_models(key)
    except Exception as e:  # noqa: BLE001
        print("Gemini list model gagal:", e)
        return None
    bad: set = set()
    # 3 ronde sabar: 503 = server Google sedang penuh, biasanya reda dalam hitungan menit.
    for rnd, wait in enumerate([0, 30, 60]):
        live = [m for m in models if m not in bad]
        if not live:
            break
        if wait:
            print(f"Gemini sibuk, ronde {rnd + 1}: tunggu {wait}s...")
            time.sleep(wait)
        for model in live:
            print("Model Gemini:", model)
            try:
                r = requests.post(GEN_URL.format(m=model), params={"key": key}, json=body, timeout=120)
            except Exception as e:  # noqa: BLE001
                print("Gemini error jaringan:", str(e)[:150])
                continue
            if r.status_code in RETRY_STATUS:
                print("Gemini status", r.status_code)
                continue
            if r.status_code != 200:
                print("Gemini status", r.status_code, r.text[:200])
                bad.add(model)
                continue
            try:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                print(f"Naskah dari: Gemini ({model})")
                return text
            except (KeyError, IndexError):
                print("Gemini balasan kosong")
                bad.add(model)
    return None


def groq_models(key: str) -> list[str]:
    forced = os.environ.get("GROQ_MODEL")
    if forced:
        return [forced]
    ids: list[str] = []
    try:
        r = requests.get("https://api.groq.com/openai/v1/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=30)
        r.raise_for_status()
        ids = [m["id"] for m in r.json().get("data", []) if m.get("active", True)]
    except Exception as e:  # noqa: BLE001
        print("Groq list model gagal:", str(e)[:150])
    ids = [i for i in ids if not any(x in i for x in GROQ_SKIP)]
    ordered = [m for m in GROQ_PREFER if m in ids]
    rest = [i for i in ids if i not in ordered and any(k in i for k in ("llama", "qwen", "gpt-oss"))]
    return (ordered + rest)[:3] or GROQ_PREFER[:1]


def _groq(prompt: str):
    key = os.environ.get("GROQ_API_KEY")
    if not key or "groq" in DEAD:
        return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}"}
    models = groq_models(key)
    missing = 0
    for model in models:
        print("Cadangan: Groq", model)
        full = {"model": model, "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"}, "temperature": 0.7, "max_tokens": 4096}
        if "gpt-oss" in model:
            full["reasoning_effort"] = "low"
        plain = {"model": model, "messages": [{"role": "user", "content": prompt}],
                 "temperature": 0.7, "max_tokens": 4096}
        for wait in [0, 15]:
            if wait:
                time.sleep(wait)
            try:
                r = requests.post(url, headers=headers, json=full, timeout=120)
                if r.status_code == 400:  # model tidak mendukung JSON mode/parameter tertentu -> ulangi polos
                    r = requests.post(url, headers=headers, json=plain, timeout=120)
            except Exception as e:  # noqa: BLE001
                print("Groq error jaringan:", str(e)[:150])
                continue
            if r.status_code in RETRY_STATUS:
                print("Groq status", r.status_code)
                continue
            if r.status_code in (401, 403):
                print("Groq status", r.status_code, r.text[:200], "-> kunci/akses ditolak, dilewati")
                DEAD.add("groq")
                return None
            if r.status_code == 404:
                print("Groq status 404, model tidak ada:", model)
                missing += 1
                break
            if r.status_code != 200:
                print("Groq status", r.status_code, r.text[:200])
                break
            try:
                content = r.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                print("Groq balasan kosong")
                break
            print(f"Naskah dari: Groq ({model})")
            return content
    if missing == len(models):
        print("Groq: semua model tidak tersedia, dilewati sampai run berikutnya.")
        DEAD.add("groq")
    return None


def _cloudflare_text(prompt: str):
    acc, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not acc or not tok or "cloudflare" in DEAD:
        return None
    model = os.environ.get("CF_TEXT_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    print("Cadangan: Cloudflare", model)
    try:
        r = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{model}",
            headers={"Authorization": f"Bearer {tok}"},
            json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 2500},
            timeout=180,
        )
    except Exception as e:  # noqa: BLE001
        print("Cloudflare error jaringan:", str(e)[:150])
        return None
    if r.status_code != 200:
        print("Cloudflare status", r.status_code, r.text[:200])
        if r.status_code in (401, 403) or (r.status_code == 429 and "daily free allocation" in r.text):
            DEAD.add("cloudflare")
            try:  # kuota neurons dipakai bersama gambar: gambar juga jangan mencoba Cloudflare lagi
                from . import images
                images.FAILED_PROVIDERS.add("Cloudflare")
            except Exception:  # noqa: BLE001
                pass
        return None
    out = r.json().get("result", {}).get("response")
    print(f"Naskah dari: Cloudflare ({model})")
    return json.dumps(out) if isinstance(out, (dict, list)) else out


def _parse(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def generate(topic: dict, cfg: dict) -> dict:
    mode = cfg.get("id", "history_fact")
    n = cfg["scenes"]
    year = topic.get("year")
    desc_rule = ""

    if mode == "history_trivia":
        character_block = (
            "Maskot Cal ada di tengah-bawah layar. Gambar latar HARUS: cinematic, mysterious, historical illustration style, "
            "NO text, sisakan ruang kosong di tengah-bawah. Latar boleh memberi nuansa era, tapi JANGAN menampilkan "
            "lokasi/bangunan/benda ikonik yang langsung membongkar jawabannya.\n"
        )
        image_rule = "cinematic, mysterious, atmospheric historical background hinting at the era only, no famous landmark, empty space at lower center, no text"
        era_block = ""
        era_fields = '  "era_setting": "suasana umum era itu (cahaya, warna, material) tanpa nama tempat/orang/landmark, bahasa Inggris, maks 15 kata",\n'
        era_story = ""
        title_rule = "3-7 kata teka-teki yang MENGGANTUNG, tanpa tahun, tanpa nama tokoh/tempat/peristiwa yang menjadi jawaban"
        desc_rule = " (JANGAN membocorkan jawaban, tanpa nama tokoh dan tanpa tahun)"
        mid = max(n - 2, 1)
        custom_structure = f"""STRUKTUR NASKAH (HISTORICAL TRIVIA - CLIFFHANGER), tepat {n} scenes:
1. Scene 1 = THE CHALLENGE. Ajukan pertanyaan mengejutkan tentang tokoh/peristiwa sejarah.
   (Contoh: "This man survived five assassination attempts and became a legend. Who is he?")
2. Scene 2 sampai {n - 1} = THE CLUES ({mid} scene, satu petunjuk kuat per scene, makin spesifik). 
3. Scene {n} = THE CLIFFHANGER. JANGAN beri jawaban! Katakan persis atau variasinya:
   "Think you know the answer? Comment your guess below, and come back tomorrow for the big reveal!"
ATURAN ANTI-SPOILER (WAJIB): di narasi, judul, deskripsi, tags, dan image_prompt JANGAN menyebut nama tokoh,
nama peristiwa/tempat kunci, atau tahun persis. Boleh menyebut abad/dekade secara kasar saja.
- Nada: sangat penasaran, menggantung, memancing audiens kembali besok."""
    else:
        character_block = (
            "Maskot channel (kalender kecil bernama Cal) ditempel di tengah-bawah layar oleh editor video. "
            "Setiap image_prompt HANYA melukiskan LATAR/pemandangan. JANGAN ada tokoh, wajah, atau kerumunan di depan; "
            "sisakan ruang kosong di tengah-bawah gambar.\n"
        )
        image_rule = "hanya latar era itu, tanpa tokoh/wajah, ruang kosong di tengah-bawah"
        if year:
            era_block = f"TAHUN KEJADIAN: {year}. Semua visual HARUS terasa seperti era dan lokasi kejadian itu.\n"
            era_fields = '  "era_setting": "suasana/latar era itu, bahasa Inggris, maks 20 kata",\n'
            era_story = f"- Bawa penonton MERASAKAN suasana tahun {year}.\n"
        else:
            era_block, era_fields, era_story = "", "", ""
        title_rule = "3-7 kata pemicu rasa penasaran, tanpa tahun, tanpa tanda kutip"
        if cfg.get("is_answer"):
            custom_structure = """STRUKTUR NASKAH (JAWABAN TEBAK-TEBAKAN KEMARIN):
1. Scene 1 = REVEAL, maksimal 14 kata. Buka dengan "Yesterday's mystery..." lalu langsung sebut jawabannya (nama tokoh/peristiwa).
2. Scene tengah = cerita lengkap: fakta inti, konteks, kenapa petunjuk kemarin cocok, dan kenapa ini penting.
3. Scene terakhir = opini/prediksi singkat + ajakan komentar berupa pertanyaan ("Did you guess it?")."""
        else:
            custom_structure = """STRUKTUR NASKAH (ikuti urutan scenes):
1. Scene 1 = HOOK, maksimal 12 kata, memancing rasa penasaran dalam 2 detik.
2. Scene tengah = fakta inti + konteks + "kenapa ini penting".
3. Scene terakhir = opini/prediksi singkat + ajakan komentar berupa pertanyaan."""

    prompt = PROMPT.format(
        custom_structure=custom_structure, era_block=era_block, era_fields=era_fields,
        era_story=era_story, language=cfg["language"], country=cfg["country"],
        niche=cfg.get("niche", ""), angle=cfg.get("angle", ""), topic=topic["title"],
        tags=", ".join(topic.get("tags", [])),
        facts_block=(f'DASAR FAKTA: {topic["facts"]}\n' if topic.get("facts") else ""),
        character_block=character_block, image_rule=image_rule, n=n,
        title_rule=title_rule, desc_rule=desc_rule,
    )

    data = None
    for provider in (_gemini, _groq, _cloudflare_text):
        text = provider(prompt)
        if not text:
            continue
        try:
            data = _parse(text)
            assert data.get("scenes"), "tanpa scenes"
            break
        except Exception as e:  # noqa: BLE001
            print(f"Balasan {provider.__name__} tidak valid:", e)
            data = None
    if not data:
        raise RuntimeError("Semua penyedia AI teks gagal")

    data["title"] = make_title(data.get("hook_title") or data.get("title") or topic["title"], topic)
    setting = (data.get("era_setting") or "").strip()

    if mode == "history_trivia":
        style = "cinematic historical illustration, mysterious lighting, highly detailed, no people in foreground, empty space at lower center, no text"
    else:
        style = "flat vector comic style, bold outlines, wide shot, no people in foreground, empty space at lower center, no text"

    for sc in data["scenes"]:
        parts = [sc["image_prompt"]]
        if setting:
            parts.append(f"Era setting: {setting}")
        parts.append(style)
        sc["image_prompt"] = ". ".join(parts)
    return data