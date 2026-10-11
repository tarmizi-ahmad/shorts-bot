"""Buat naskah + prompt gambar orisinal dengan Gemini API (free tier)."""
import json
import os
import requests

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

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


def generate(topic: dict, cfg: dict) -> dict:
    prompt = PROMPT.format(
        language=cfg["language"],
        country=cfg["country"],
        topic=topic["title"],
        tags=", ".join(topic.get("tags", [])),
        n=cfg["scenes"],
    )
    r = requests.post(
        URL.format(m=MODEL),
        params={"key": os.environ["GEMINI_API_KEY"]},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=90,
    )
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(text)
    assert data.get("scenes"), "Gemini tidak mengembalikan scenes"
    return data
