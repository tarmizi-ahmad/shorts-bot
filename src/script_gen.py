"""Buat naskah + prompt gambar orisinal. Mode: history_fact & history_trivia (Cliffhanger)."""
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
{era_fields}  "hook_title": "3-7 kata pemicu rasa penasaran, tanpa tahun, tanpa tanda kutip",
  "description": "deskripsi 2 kalimat + 3 hashtag",
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

def _gemini(prompt: str):
    key = os.environ.get("GEMINI_API_KEY")
    if not key: return None
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    try: models = list_models(key)
    except Exception as e:
        print("Gemini list model gagal:", e); return None
    for model in models:
        print("Model Gemini:", model)
        for wait in [0, 20]:
            if wait: time.sleep(wait)
            try:
                r = requests.post(GEN_URL.format(m=model), params={"key": key}, json=body, timeout=120)
            except Exception as e: continue
            if r.status_code in RETRY_STATUS: continue
            if r.status_code != 200: break
            try:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                print(f"Naskah dari: Gemini ({model})")
                return text
            except (KeyError, IndexError): break
    return None

def _groq(prompt: str):
    key = os.environ.get("GROQ_API_KEY")
    if not key: return None
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    print("Cadangan: Groq", model)
    for wait in [0, 15]:
        if wait: time.sleep(wait)
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model, "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}, "temperature": 0.7,
                }, timeout=120,
            )
        except Exception as e: continue
        if r.status_code in RETRY_STATUS: continue
        if r.status_code != 200: return None
        print(f"Naskah dari: Groq ({model})")
        return r.json()["choices"][0]["message"]["content"]
    return None

def _cloudflare_text(prompt: str):
    acc, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not acc or not tok: return None
    model = os.environ.get("CF_TEXT_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    print("Cadangan: Cloudflare", model)
    try:
        r = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{model}",
            headers={"Authorization": f"Bearer {tok}"},
            json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 2500},
            timeout=180,
        )
    except Exception as e: return None
    if r.status_code != 200: return None
    out = r.json().get("result", {}).get("response")
    print(f"Naskah dari: Cloudflare ({model})")
    return json.dumps(out) if isinstance(out, (dict, list)) else out

def _parse(text: str) -> dict:
    text = (text or "").strip()
    try: return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m: raise
        return json.loads(m.group(0))

def generate(topic: dict, cfg: dict) -> dict:
    mode = cfg.get("id", "history_fact")

    if mode == "history_trivia":
        character_block = "Maskot Cal ada di tengah-bawah. Gambar latar HARUS: cinematic, mysterious, or highly detailed historical illustration style. NO text in image. Leave empty space at lower center. Make it intriguing.\n"
        image_rule = "cinematic, mysterious, detailed historical background, empty space at lower center, no text"
        era_block, era_fields, era_story = "", "", ""
        custom_structure = """STRUKTUR NASKAH (HISTORICAL TRIVIA - CLIFFHANGER):
1. Scene 1 = THE CHALLENGE. Ajukan pertanyaan mengejutkan tentang tokoh/peristiwa sejarah. (Contoh: "This man survived 5 assassination attempts and became a legendary leader. Who is he?")
2. Scene 2 = THE CLUES. Berikan 2 petunjuk detail yang kuat, tapi JANGAN sebut nama tokoh atau kejadian sebenarnya. Biarkan penonton menebak.
3. Scene 3 = THE CLIFFHANGER. JANGAN beri jawaban! Katakan persis seperti ini atau variasinya: "Think you know the answer? Comment your guess below, and come back tomorrow for the full story and the big reveal!"
- Nada: Sangat penasaran, menggantung, memancing audiens untuk kembali besok."""
    else:
        character_block = "Maskot channel (kalender kecil bernama Cal) ditempel di tengah-bawah layar oleh editor video. Setiap image_prompt HANYA melukiskan LATAR/pemandangan. JANGAN ada tokoh, wajah, atau kerumunan di depan; sisakan ruang kosong di tengah-bawah gambar.\n"
        image_rule = "hanya latar era itu, tanpa tokoh/wajah, ruang kosong di tengah-bawah"
        year = topic.get("year")
        if year:
            era_block = f"TAHUN KEJADIAN: {year}. Semua visual HARUS terasa seperti era dan lokasi kejadian itu.\n"
            era_fields = '  "era_setting": "suasana/latar era itu, bahasa Inggris, maks 20 kata",\n'
            era_story = f"- Bawa penonton MERASAKAN suasana tahun {year}.\n"
        else:
            era_block, era_fields, era_story = "", "", ""
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
        character_block=character_block, image_rule=image_rule, n=cfg["scenes"],
    )

    data = None
    for provider in (_gemini, _groq, _cloudflare_text):
        text = provider(prompt)
        if not text: continue
        try:
            data = _parse(text)
            assert data.get("scenes"), "tanpa scenes"
            break
        except Exception as e:
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
        if setting: parts.append(f"Era setting: {setting}")
        parts.append(style)
        sc["image_prompt"] = ". ".join(parts)
    return data