"""Ambil ID Halaman + token Halaman jangka panjang (tanpa kedaluwarsa).

Jalankan di Termux:  python tools/fb_token.py
Semua nilai rahasia dimasukkan lewat prompt tersembunyi (tidak masuk riwayat shell).
Salin hasilnya ke GitHub Secrets, JANGAN ditempel ke chat.
"""
import getpass
import os

import requests

VER = os.environ.get("FB_GRAPH_VERSION", "v25.0")
G = f"https://graph.facebook.com/{VER}"


def main() -> None:
    app_id = input("App ID: ").strip()
    secret = getpass.getpass("App Secret (tersembunyi): ").strip()
    short = getpass.getpass("User token dari Graph API Explorer (tersembunyi): ").strip()

    r = requests.get(f"{G}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id,
        "client_secret": secret, "fb_exchange_token": short}, timeout=30)
    j = r.json()
    if "access_token" not in j:
        raise SystemExit(f"Gagal tukar token: {j}")
    long_user = j["access_token"]

    r = requests.get(f"{G}/me/accounts", params={"access_token": long_user, "limit": 100}, timeout=30)
    pages = r.json().get("data", [])
    if not pages:
        raise SystemExit(f"Tidak ada Halaman ditemukan: {r.json()}")
    print("\nHalaman yang bisa dipakai:")
    for p in pages:
        print(f"- {p['name']}  |  FB_PAGE_ID = {p['id']}")
    pick = input("\nMasukkan FB_PAGE_ID yang dipilih: ").strip()
    for p in pages:
        if p["id"] == pick:
            print("\nFB_PAGE_TOKEN (simpan ke GitHub Secrets):\n" + p["access_token"])
            return
    raise SystemExit("ID tidak cocok.")


if __name__ == "__main__":
    main()