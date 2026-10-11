"""Buat naskah + prompt gambar orisinal dengan Gemini API (free tier)."""
import json
import os
import re
import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"

PROMPT = """Kamu penulis konten video pendek (YouTube Shorts) dalam {language}.
Topik yang sedang ramai di negara {country}: "{topic}" (kata kunci: {tags}).

Tulis konten ORISINAL. Jangan menyalin judul/kalimat dari sumber, jangan sebut
nama channel, jangan pakai lirik, kutipan panjang, atau karakter berhak cipta.
Gaya bahasa harus terasa natural untuk audiens {country}.
Jangan membuat klaim fakta yang tidak pasti tentang orang nyata; kalau topik
sensitif, bawakan secara netral.

Balas HANYA JSON dengan bentuk:
{{
  "title": "judul menarik maks 70 karakter",
  "description": "deskripsi 2 kalimat + 3 hashtag",
  "tags": ["tag1", "tag2", "tag3"],
  "scenes": [
    {{"narration": "1-2 kalimat narasi singkat", "image_prompt": "deskripsi gambar ilustrasi gaya komik/kartun, tanpa teks, tanpa tokoh terkenal, bahasa Inggris"}}
  ]
}}
Jumlah scenes: tepat {n}. Total narasi sekitar 40-50 detik bila dibaca."""

SKIP = ("image", "tts", "live", "audio", "lite", "exp", "embedding", "robotics")


def pick_model(key: str) -> str:
    forced = os.environ.get("GEMINI_MODEL")
    if forced:
        return forced
    r = requests.get(f"{BASE}/models", params={"key": key, "pageSize": 200}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"ListModels gagal {r.status_code}: {r.text[:300]}")
    names = [
        m["name"].split("/")[-1]
        for m in r.json().get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    cands = [n for n in names if "flash" in n and not any(s in n for s in SKIP)]
    if not cands:
        raise RuntimeError(f"Tidak ada model flash yang cocok. Tersedia: {names[:20]}")

    def ver(n: str):
        return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", n)]

    return max(cands, key=ver)


def generate(topic: dict, cfg: dict) -> dict:
    key = os.environ["GEMINI_API_KEY"]
    model = pick_model(key)
    print("Model Gemini:", model)
    prompt = PROMPT.format(
        language=cfg["language"],
        country=cfg["country"],
        topic=topic["title"],
        tags=", ".join(topic.get("tags", [])),
        n=cfg["scenes"],
    )
    r = requests.post(
        f"{BASE}/models/{model}:generateContent",
        params={"key": key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=90,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Gemini {model} gagal {r.status_code}: {r.text[:400]}")
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(text)
    assert data.get("scenes"), "Gemini tidak mengembalikan scenes"
    return data