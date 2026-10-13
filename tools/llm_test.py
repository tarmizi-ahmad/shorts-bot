"""Tes manual: apakah model lokal kecil (llama.cpp) cukup bagus untuk naskah Shorts?

Memakai PROMPT & pasca-proses asli dari src/script_gen.py, jadi hasilnya adil
dibandingkan Gemini. Tidak mengubah pipeline utama.
"""
import json
import os
import sys
import time

from huggingface_hub import hf_hub_download
from llama_cpp import Llama

from src import script_gen

REPO = os.environ.get("MODEL_REPO", "Qwen/Qwen2.5-3B-Instruct-GGUF")
FILE = os.environ.get("MODEL_FILE", "qwen2.5-3b-instruct-q4_k_m.gguf")

TOPICS = [
    {"title": "October 13, 54: Roman emperor Claudius dies from poisoning under mysterious circumstances. He is succeeded by his adopted son Nero.",
     "year": 54, "date_label": "Oct 13, 54", "tags": ["Claudius", "Nero", "Roman Empire"],
     "facts": "Roman emperor Claudius dies from poisoning under mysterious circumstances. He is succeeded by his adopted son Nero, rather than by Britannicus, his son with Messalina."},
    {"title": "October 13, 1884: Greenwich is established as the universal time meridian of longitude.",
     "year": 1884, "date_label": "Oct 13, 1884", "tags": ["Greenwich", "Prime meridian", "Time zone"],
     "facts": "Greenwich is established as the universal time meridian of longitude by the International Meridian Conference in Washington, D.C."},
    {"title": "October 13, 1972: Uruguayan Air Force Flight 571 crashes in the Andes.",
     "year": 1972, "date_label": "Oct 13, 1972", "tags": ["Andes", "Flight 571", "Survival"],
     "facts": "Uruguayan Air Force Flight 571 crashes in the Andes mountains; survivors are rescued more than two months later."},
]


def main() -> int:
    cfg = json.load(open("config.json", encoding="utf-8"))
    print(f"Unduh model {REPO}/{FILE} ...", flush=True)
    path = hf_hub_download(REPO, FILE)
    llm = Llama(model_path=path, n_ctx=6144, n_threads=os.cpu_count() or 2, verbose=False)

    def local(prompt: str):
        t = time.time()
        out = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=2000,
        )
        print(f"  waktu generate: {time.time() - t:.0f} detik", flush=True)
        return out["choices"][0]["message"]["content"]

    script_gen._gemini = local
    script_gen._groq = lambda p: None
    script_gen._cloudflare_text = lambda p: None

    rows = []
    for tp in TOPICS:
        print("\n=== ", tp["title"][:70], flush=True)
        t0 = time.time()
        try:
            d = script_gen.generate(tp, cfg)
        except Exception as e:
            print("  GAGAL:", e)
            rows.append((tp["year"], False, 0, 0, False, 0))
            continue
        scenes = d["scenes"]
        words = sum(len(s["narration"].split()) for s in scenes)
        hook_words = len(scenes[0]["narration"].split())
        era_ok = bool((d.get("era_outfit") or "").strip() and (d.get("era_setting") or "").strip())
        print("  Judul     :", d["title"])
        print("  Outfit    :", d.get("era_outfit"))
        print("  Setting   :", d.get("era_setting"))
        for i, s in enumerate(scenes, 1):
            print(f"  [{i}] {s['narration']}")
        print("  Contoh prompt gambar:", scenes[0]["image_prompt"][:200])
        rows.append((tp["year"], len(scenes) == cfg["scenes"], words, hook_words, era_ok, time.time() - t0))

    print("\n==== RINGKASAN (target: 6 scene, 100-130 kata, hook <=12 kata, era lengkap) ====")
    print("tahun | scene ok | total kata | kata hook | era ok | detik")
    for r in rows:
        print(f"{r[0]:>5} | {str(r[1]):>8} | {r[2]:>10} | {r[3]:>9} | {str(r[4]):>6} | {r[5]:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())