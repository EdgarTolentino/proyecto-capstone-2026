"""Muestra el `chat_id` de quien le escribió al bot. Es el destinatario de los avisos.

    GEPP_TELEGRAM_TOKEN=... uv run python scripts/telegram_chat_id.py

Antes, desde el teléfono, abre el bot y envíale cualquier mensaje. El `chat_id` va en
`GEPP_AVISO_DESTINATARIO` del `.env`, nunca en el repositorio.
"""

from __future__ import annotations

import os
import sys

import httpx


def main() -> int:
    token = os.environ.get("GEPP_TELEGRAM_TOKEN")
    if not token:
        print("Falta GEPP_TELEGRAM_TOKEN", file=sys.stderr)
        return 2
    r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15)
    if r.status_code != 200:
        print(f"Telegram respondió {r.status_code}: revisa el token", file=sys.stderr)
        return 1
    chats = {}
    for u in r.json().get("result", []):
        chat = (u.get("message") or {}).get("chat")
        if chat:
            chats[chat["id"]] = chat.get("type", "")
    if not chats:
        print("Nadie le ha escrito al bot todavía: envíale un mensaje desde el teléfono y repite.")
        return 1
    for chat_id, tipo in chats.items():
        print(f"GEPP_AVISO_DESTINATARIO={chat_id}   ({tipo})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
