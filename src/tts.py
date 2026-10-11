"""Narasi dengan edge-tts (suara Microsoft Edge, gratis)."""
import asyncio
import edge_tts


async def _speak(text: str, voice: str, path: str) -> None:
    await edge_tts.Communicate(text, voice).save(path)


def make_voice(text: str, voice: str, path: str) -> None:
    asyncio.run(_speak(text, voice, path))
