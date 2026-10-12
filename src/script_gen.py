"""Buat naskah + prompt gambar orisinal dengan Gemini API (free tier)."""
import json
import os
import re
import time
import requests

LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
SKIP = ("image", "tts", "live", "audio", "lite", "exp", "embedding", "robotics",
        "omni", "preview", "thinking", "customtools")
WAITS = [20, 60, 120]
RETRY_STATUS = (429, 500, 502, 503, 504)

PROMPT = """Kamu penulis naskah YouTube Shorts dalam bahasa {language} untuk audiens {country}.
Niche channel: {niche}
Sudut pandang khas channel: {angle}

Topik: "{topic}" (kata kunci: {tags}).
{facts_block}{character_block}
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

Balas HANYA JSON dengan bentuk:
{{
  "hook_title": "3-7 kata pemicu rasa penasaran, tanpa tahun, tanpa tanda kutip, tanpa titik dua",
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


SERIES = "Today in History"


def make_title(hook: str, topic: dict) -> str:
    """Pola seri: '<hook> | Today in History (Oct 12, 1492)', maks 85 karakter."""
    hook = hook.strip().strip('"').rstrip(".!?:")
    label = topic.get("date_label")
    if not label:
        return hook[:85]
    tail = f" | {SERIES} ({label})"
    room = 85 - len(tail)
    if len(hook) > room:
        hook = hook[:room].rsplit(" ", 1)[0]
    return hook + tail


def generate(topic: dict, cfg: dict) -> dict:
    key = os.environ["GEMINI_API_KEY"]
    character = cfg.get("character", "").strip()
    if character:
        character_block = (
            f"MASKOT TETAP channel: {character}\n"
            "Setiap image_prompt harus menampilkan MASKOT ITU sebagai tokoh utama yang "
            "melakukan sesuatu sesuai isi scene (aksi, ekspresi, latar). Cukup tulis "
            "'the mascot', JANGAN mendeskripsikan ulang tampilannya. Tokoh sejarah/nyata "
            "hanya boleh tampil sebagai siluet atau figur bergaya tanpa wajah detail.\n"
        )
        image_rule = "tulis 'the mascot' + aksi + latar; tanpa wajah orang nyata"
    else:
        character_block = ""
        image_rule = "tanpa tokoh terkenal"
    prompt = PROMPT.format(
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
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    for model in list_models(key):
        print("Model Gemini:", model)
        for wait in [0, 20, 60]:
            if wait:
                print(f"Gemini sibuk, tunggu {wait}s...")
                time.sleep(wait)
            try:
                r = requests.post(GEN_URL.format(m=model), params={"key": key}, json=body, timeout=180)
            except requests.exceptions.RequestException as e:
                print("Gemini error jaringan:", e)
                continue
            if r.status_code in RETRY_STATUS:
                print("Gemini status", r.status_code)
                continue
            if r.status_code == 404:
                break
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text)
            assert data.get("scenes"), "Gemini tidak mengembalikan scenes"
            data["title"] = make_title(data.get("hook_title") or data.get("title") or topic["title"], topic)
            if character:
                for sc in data["scenes"]:
                    sc["image_prompt"] = f"{character}. {sc['image_prompt']}"
            return data
        print("Model", model, "gagal, coba model lain...")
    raise RuntimeError("Gemini gagal di semua model")