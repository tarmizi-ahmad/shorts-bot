"""Upload ke YouTube lewat refresh token OAuth (dibuat sekali, lihat README)."""
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _creds():
    return Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )


def _service():
    return build("youtube", "v3", credentials=_creds())


def check_auth() -> None:
    """Cek token YouTube SEBELUM membuat video. Raise RefreshError bila token kedaluwarsa/dicabut."""
    from google.auth.transport.requests import Request
    _creds().refresh(Request())


def upload(path: str, meta: dict, privacy: str = "private") -> str:
    body = {
        "snippet": {
            "title": (meta["title"] + " #Shorts")[:100],
            "description": meta["description"] + "\n\n#Shorts",
            "tags": meta.get("tags", []),
            "categoryId": "24",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            # Wajib jujur: konten ini dibuat AI.
            "containsSyntheticMedia": True,
        },
    }
    media = MediaFileUpload(path, mimetype="video/mp4", resumable=True)
    req = _service().videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]