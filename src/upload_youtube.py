"""Upload ke YouTube lewat refresh token OAuth (dibuat sekali, lihat README)."""
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _creds(token_env: str = "YT_REFRESH_TOKEN"):
    """token_env = nama secret refresh token. Channel berbeda = refresh token berbeda."""
    refresh = os.environ.get(token_env, "").strip()
    if not refresh:
        raise RuntimeError(f"Secret {token_env} kosong/belum dibuat (token channel tujuan upload).")
    return Credentials(
        token=None,
        refresh_token=refresh,
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )


def _service(token_env: str = "YT_REFRESH_TOKEN"):
    return build("youtube", "v3", credentials=_creds(token_env))


def check_auth(token_env: str = "YT_REFRESH_TOKEN") -> None:
    """Cek token YouTube SEBELUM membuat video. Raise RefreshError bila token kedaluwarsa/dicabut."""
    from google.auth.transport.requests import Request
    _creds(token_env).refresh(Request())


def upload(path: str, meta: dict, privacy: str = "private", token_env: str = "YT_REFRESH_TOKEN") -> str:
    body = {
        "snippet": {
            "title": (meta["title"] + " #Shorts")[:100],
            "description": meta["description"] + "\n\n#Shorts",
            "tags": meta.get("tags", []),
            "categoryId": str(meta.get("category", "24")),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            # Wajib jujur: konten ini dibuat AI.
            "containsSyntheticMedia": True,
        },
    }
    media = MediaFileUpload(path, mimetype="video/mp4", resumable=True)
    req = _service(token_env).videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]