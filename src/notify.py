"""Notifikasi hasil run lewat email (SMTP) dan/atau Telegram. Tidak pernah menggagalkan pipeline."""
import os
import smtplib
import ssl
from email.message import EmailMessage

import requests


def _run_url() -> str:
    repo, run = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    if repo and run:
        return f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{run}"
    return ""


def _send_email(subject: str, body: str) -> bool:
    user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    if not user or not pw:
        return False
    to = os.environ.get("NOTIFY_EMAIL") or user
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or 465)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(body)
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as s:
        s.login(user, pw)
        s.send_message(msg)
    return True


def _send_telegram(subject: str, body: str) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": f"{subject}\n\n{body}"[:4000]},
        timeout=30,
    )
    r.raise_for_status()
    return True


def notify(subject: str, lines: list) -> None:
    """Kirim ke semua kanal yang sudah dikonfigurasi. Error apa pun hanya dicetak."""
    body = "\n".join(lines)
    url = _run_url()
    if url:
        body += f"\n\nDetail run: {url}"
    sent = False
    for name, fn in (("Email", _send_email), ("Telegram", _send_telegram)):
        try:
            if fn(subject, body):
                print(f"📨 Notifikasi {name} terkirim.")
                sent = True
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Notifikasi {name} gagal: {type(e).__name__}: {str(e)[:120]}")
    if not sent:
        print("ℹ️ Notifikasi tidak dikirim (belum ada SMTP_USER/SMTP_PASSWORD atau TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID).")