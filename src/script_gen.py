"""Buat naskah + prompt gambar orisinal. Gemini dulu, cadangan: Groq, Cloudflare."""
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
- Jangan membuat klaim fakta yang tidak pasti tentang orang nyata. Kalau tidak yakin,
  pakai kata seperti "reportedly" / "people are saying". Topik sensitif dibawakan netral.
- Jangan mengarang tanggal, angka, nama, atau kutipan. Pakai hanya yang ada di
  DASAR FAKTA (bila ada) atau pengetahuan umum yang pasti benar.
- Bukan sekadar menceritakan ulang. Wajib ada NILAI TAMBAH: konteks singkat yang
  jarang disebut, kenapa ini penting bagi penonton, dan satu pendapat/prediksi
  yang jelas (bertanda opini).
- Jika topik tidak cocok dengan niche (mis. musik, selebriti gosip), cari sudut
  yang cocok dengan niche, atau tetap bawakan lewat sudut pandang channel.

STRUKTUR NASKAH (ikuti urutan scenes):
1. Scene 1 = HOOK, maksimal 12 kata, memancing rasa penasaran dalam 2 detik
   (pertanyaan mengejutkan / klaim berani yang benar / kontras). Jangan mulai dengan
   "Hi", "Hello", atau perkenalan.
2. Scene tengah = fakta inti + konteks + "kenapa ini penting".
3. Scene terakhir = opini/prediksi singkat + ajakan komentar berupa pertanyaan
   (mis. "Do you agree?"), maks 1 kalimat. Jangan minta subscribe berlebihan.
- Kalimat pendek, ritme cepat, tanpa basa-basi.
{era_story}
Balas HANYA JSON dengan bentuk:
{{
{era_fields}  "hook_title": "3-7 kata pemicu rasa penasaran, tanpa tahun, tanpa tanda kutip, tanpa titik dua",
  "description": "deskripsi 2 kalimat + 3 hashtag",
  "tags": ["tag1", "tag2", "tag3"],
  "scenes": [
    {{"narration": "1-2 kalimat narasi singkat dalam {language}", "image_prompt": "maks 25 kata, bahasa Inggris, gaya komik/kartun, tanpa teks di gambar, {image_rule}"}}
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
    """Pola seri: '<hook> | What Happened Today (Oct 12, 1492)', maks 85 karakter."""
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
    if not key:
        return None
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    try:
        models = list_models(key)
    except requests.exceptions.RequestException as e:
        print("Gemini list model gagal:", e)
        return None
    for model in models:
        print("Model Gemini:", model)
        for wait in [0, 20]:
            if wait:
                print(f"Gemini sibuk, tunggu {wait}s...")
                time.sleep(wait)
            try:
                r = requests.post(GEN_URL.format(m=model), params={"key": key}, json=body, timeout=120)
            except requests.exceptions.RequestException as e:
                print("Gemini error jaringan:", e)
                continue
            if r.status_code in RETRY_STATUS:
                print("Gemini status", r.status_code)
                continue
            if r.status_code != 200:
                print("Gemini status", r.status_code, r.text[:200])
                break
            try:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                print(f"Naskah dari: Gemini ({model})")
                return text
            except (KeyError, IndexError):
                print("Gemini balasan kosong")
                break
    return None


def _groq(prompt: str):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    print("Cadangan: Groq", model)
    for wait in [0, 15]:
        if wait:
            time.sleep(wait)
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.7,
                },
                timeout=120,
            )
        except requests.exceptions.RequestException as e:
            print("Groq error jaringan:", e)
            continue
        if r.status_code in RETRY_STATUS:
            print("Groq status", r.status_code)
            continue
        if r.status_code != 200:
            print("Groq status", r.status_code, r.text[:200])
            return None
        print(f"Naskah dari: Groq ({model})")
        return r.json()["choices"][0]["message"]["content"]
    return None


def _cloudflare_text(prompt: str):
    acc, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not acc or not tok:
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
    except requests.exceptions.RequestException as e:
        print("Cloudflare error jaringan:", e)
        return None
    if r.status_code != 200:
        print("Cloudflare status", r.status_code, r.text[:200])
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
    character = cfg.get("character", "").strip()
    if character:
        character_block = (
            f"MASKOT TETAP channel: {character}\n"
            "Setiap image_prompt harus menampilkan MASKOT ITU sebagai tokoh utama yang "
            "melakukan sesuatu sesuai isi scene (aksi, ekspresi, latar). Cukup tulis "
            "'the mascot', JANGAN mendeskripsikan ulang tampilannya (pakaian era diatur lewat era_outfit). Tokoh sejarah/nyata "
            "hanya boleh tampil sebagai siluet atau figur bergaya tanpa wajah detail.\n"
        )
        image_rule = "tulis 'the mascot' + aksi + latar; tanpa wajah orang nyata"
    else:
        character_block = ""
        image_rule = "tanpa tokoh terkenal"
    year = topic.get("year")
    era_block, era_fields, era_story = "", "", ""
    if year:
        era_block = (
            f"TAHUN KEJADIAN: {year}. Semua visual HARUS terasa seperti era dan lokasi kejadian itu: "
            "maskot memakai pakaian khas era dan tempat tersebut, latar (bangunan, kendaraan, "
            "teknologi, warna, suasana) mencerminkan era itu, bukan zaman modern.\n"
        )
        era_fields = (
            '  "era_outfit": "pakaian maskot yang akurat untuk tahun & lokasi kejadian, bahasa Inggris, maks 15 kata",\n'
            '  "era_setting": "suasana/latar era itu (arsitektur, kendaraan, teknologi, palet warna), bahasa Inggris, maks 20 kata",\n'
        )
        era_story = (
            f"- Bawa penonton MERASAKAN suasana tahun {year}: di scene 2-3 sebut 1-2 detail "
            "sensorik/keseharian era itu (suara, benda, teknologi, tren) yang PASTI benar. "
            "Boleh memakai kalimat 'Imagine it's ...' untuk mengajak membayangkan.\n"
        )
    prompt = PROMPT.format(
        era_block=era_block,
        era_fields=era_fields,
        era_story=era_story,
        language=cfg["language"],
        country=cfg["country"],
        niche=cfg.get("niche", "berita & tren harian dijelaskan singkat"),
        angle=cfg.get("angle", "jelaskan kenapa ini penting dan apa yang mungkin terjadi berikutnya"),
        topic=topic["title"],
        tags=", ".join(topic.get("tags", [])),
        facts_block=(f'DASAR FAKTA (sumber utama): {topic["facts"]}\n' if topic.get("facts") else ""),
        character_block=character_block,
        image_rule=image_rule,
        n=cfg["scenes"],
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
        except Exception as e:  # JSON rusak / tidak lengkap -> coba penyedia berikutnya
            print(f"Balasan {provider.__name__} tidak valid:", e)
            data = None
    if not data:
        raise RuntimeError("Semua penyedia AI teks gagal (Gemini, Groq, Cloudflare)")

    data["title"] = make_title(data.get("hook_title") or data.get("title") or topic["title"], topic)
    if character:
        outfit = (data.get("era_outfit") or "").strip()
        setting = (data.get("era_setting") or "").strip()
        prefix = character
        if outfit:
            prefix += f", wearing {outfit}"
        if setting:
            prefix += f". Era setting: {setting}"
        for sc in data["scenes"]:
            sc["image_prompt"] = f"{prefix}. {sc['image_prompt']}"
    return data