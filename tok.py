import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

REDIRECT = "http://localhost"   # harus terdaftar di Authorized redirect URIs client kamu
SCOPE = "https://www.googleapis.com/auth/youtube.upload"

cid = input("Client ID: ").strip()
secret = getpass.getpass("Client secret (tidak tampil di layar): ").strip()
print(f"(Secret diterima: {len(secret)} karakter, berakhiran ...{secret[-3:]})")
if len(secret) != 35 or not secret.startswith("GOCSPX-"):
    print("PERINGATAN: secret yang benar biasanya 35 karakter dan diawali GOCSPX-. Mungkin salah salin.")
q = urllib.parse.urlencode({
    "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code",
    "scope": SCOPE, "access_type": "offline", "prompt": "consent",
})
print("\n1) Buka alamat ini di Chrome, pilih CHANNEL tujuan, lalu Allow:\n")
print("https://accounts.google.com/o/oauth2/v2/auth?" + q)
print("\n2) Muncul 'site can't be reached' = normal. Salin SELURUH alamat di bilah alamat, tempel di sini.")
raw = input("\nAlamat lengkap (atau kodenya saja): ").strip()
if "code=" in raw:
    params = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
    code = (params.get("code") or [""])[0]
    if not code:
        sys.exit(f"Tidak ada code di alamat itu. Error dari Google: {params.get('error')}")
else:
    code = urllib.parse.unquote(raw)   # kode saja (mis. 4/0A... atau 4%2F0A...)
if not code.startswith("4/"):
    sys.exit("Itu bukan kode otorisasi (harus diawali 4/0A...). Salin ulang dari bilah alamat.")
body = urllib.parse.urlencode({
    "code": code, "client_id": cid, "client_secret": secret,
    "redirect_uri": REDIRECT, "grant_type": "authorization_code",
}).encode()
try:
    r = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=30))
    print("\nBERHASIL. Refresh token (salin, simpan ke GitHub Secrets):\n")
    print(r.get("refresh_token") or "(tidak ada refresh_token; ulangi dari awal)")
except urllib.error.HTTPError as e:
    err = json.loads(e.read() or b"{}")
    print("\nGAGAL:", e.code, err.get("error"), "-", err.get("error_description"))
except urllib.error.URLError as e:
    print("\nTidak bisa menghubungi Google (cek internet):", e.reason)