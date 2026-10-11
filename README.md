# shorts-bot

Pipeline otomatis: trending YouTube (per negara) → naskah Gemini → gambar Pollinations → narasi edge-tts → video FFmpeg → upload YouTube Shorts. Jalan di GitHub Actions, jadi HP cukup untuk ngoding.

## Struktur
```
config.json                  negara, bahasa, jam ramai, suara, privasi
src/trends.py                YouTube mostPopular per regionCode
src/script_gen.py            naskah + prompt gambar (Gemini)
src/images.py                gambar per scene (Pollinations)
src/tts.py                   narasi (edge-tts)
src/video.py                 klip + concat (ffmpeg)
src/upload_youtube.py        upload Shorts
src/db.py                    catatan posting (Supabase)
src/main.py                  orkestrasi
supabase.sql                 tabel posts
.github/workflows/shorts.yml cron tiap jam
```

## Setup (sekali)
1. **Supabase**: buat project, jalankan `supabase.sql`. Ambil `Project URL` dan `service_role key`.
2. **Google Cloud Console**: aktifkan *YouTube Data API v3*.
   - Buat **API key** → `YOUTUBE_API_KEY`.
   - Buat **OAuth Client ID** (tipe Desktop) → `YT_CLIENT_ID`, `YT_CLIENT_SECRET`.
   - Dapatkan **refresh token** dengan scope `youtube.upload` (pakai OAuth Playground: developers.google.com/oauthplayground, centang "Use your own OAuth credentials") → `YT_REFRESH_TOKEN`.
   - Catatan: video dari project API yang belum diaudit Google dipaksa **private**. Ajukan audit kalau mau publik.
3. **Gemini**: ambil API key gratis di aistudio.google.com → `GEMINI_API_KEY`.
4. **GitHub**: repo → Settings → Secrets and variables → Actions, tambahkan 7 secret:
   `YOUTUBE_API_KEY, GEMINI_API_KEY, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN, SUPABASE_URL, SUPABASE_KEY`.
5. Ganti nama `_gitignore` jadi `.gitignore` sebelum commit.

## Tes
Actions → shorts-bot → **Run workflow** → centang `force`. Cek log dan video di YouTube Studio (default privat).

## Atur
- Negara/jam: edit `config.json` (`peak_hours` memakai jam lokal `timezone`).
- Suara lain: `edge-tts --list-voices`.
- Cron GitHub bisa telat beberapa menit; script hanya cek jam, bukan menit.

## Aturan main
- Konten dibuat AI → sudah ditandai `containsSyntheticMedia`. Jangan dimatikan.
- Tanpa musik/klip pihak ketiga; semua aset dibuat sendiri.
- Konten massal yang repetitif bisa ditolak monetisasi. Tinjau hasil secara berkala.
- Batas gratis Gemini, Pollinations, dan kuota YouTube API bisa berubah; cek dokumentasinya.

## Langkah berikutnya
Multi-negara (loop di `main.py`), Facebook Pages & Instagram, subtitle, musik bebas royalti.
