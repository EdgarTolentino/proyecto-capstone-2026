"""Canal Telegram (Bot API por HTTPS). Implementa `CanalNotificacion`.

El token del bot es un secreto: vive en `GEPP_TELEGRAM_TOKEN`, nunca en el repositorio, y
ningún mensaje de error lo incluye (la URL de la API lo lleva dentro).

El acuse es el botón "Acuso recibo" del propio mensaje: Telegram lo entrega como
`callback_query` y se recoge con `getUpdates`, sin exponer ningún puerto hacia internet.
"""

from __future__ import annotations

from typing import Any

import httpx

from gepp_api.notificaciones.canal import Aviso, Estado, ResultadoEnvio

API = "https://api.telegram.org"
PREFIJO_ACUSE = "acuse:"


class CanalTelegram:
    nombre = "telegram"

    def __init__(self, token: str, cliente: httpx.Client | None = None, base: str = API) -> None:
        if not token:
            raise ValueError("falta el token del bot (GEPP_TELEGRAM_TOKEN)")
        self._url = f"{base}/bot{token}"
        self._http = cliente or httpx.Client(timeout=15)
        self._offset: int | None = None

    def _llamar(self, metodo: str, **datos: Any) -> httpx.Response:
        return self._http.post(f"{self._url}/{metodo}", json=datos)

    def enviar(self, aviso: Aviso, destino: str) -> ResultadoEnvio:
        try:
            r = self._llamar(
                "sendMessage",
                chat_id=destino,
                text=f"{aviso.titulo}\n\n{aviso.cuerpo}",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {
                                "text": "✅ Acuso recibo",
                                "callback_data": PREFIJO_ACUSE + aviso.token_acuse,
                            }
                        ]
                    ]
                },
            )
        except httpx.TransportError as e:
            return ResultadoEnvio(
                Estado.FALLO_TRANSITORIO, reintentar_en_s=30, motivo=type(e).__name__
            )
        cuerpo = _json(r)
        if r.status_code == 200 and cuerpo.get("ok"):
            return ResultadoEnvio(Estado.ACEPTADO, id_externo=str(cuerpo["result"]["message_id"]))
        motivo = f"{r.status_code}: {cuerpo.get('description', 'sin descripción')}"
        if r.status_code == 429:
            espera = cuerpo.get("parameters", {}).get("retry_after", 30)
            return ResultadoEnvio(
                Estado.FALLO_TRANSITORIO, reintentar_en_s=float(espera), motivo=motivo
            )
        if r.status_code >= 500:
            return ResultadoEnvio(Estado.FALLO_TRANSITORIO, reintentar_en_s=60, motivo=motivo)
        # 400 chat inexistente, 403 bot bloqueado, 401 token inválido: reintentar no arregla nada.
        return ResultadoEnvio(Estado.RECHAZADO_PERMANENTE, motivo=motivo)

    def acuses_recibidos(self) -> list[str]:
        datos: dict[str, Any] = {"timeout": 0, "allowed_updates": ["callback_query"]}
        if self._offset is not None:
            datos["offset"] = self._offset
        try:
            r = self._llamar("getUpdates", **datos)
        except httpx.TransportError:
            return []  # se reintenta en el próximo ciclo; Telegram guarda lo no confirmado
        tokens = []
        for u in _json(r).get("result", []):
            self._offset = u["update_id"] + 1  # confirma el update: no vuelve a llegar
            cq = u.get("callback_query") or {}
            data = cq.get("data", "")
            if not data.startswith(PREFIJO_ACUSE):
                continue
            tokens.append(data.removeprefix(PREFIJO_ACUSE))
            self._cerrar_boton(cq)
        return tokens

    def _cerrar_boton(self, cq: dict[str, Any]) -> None:
        """Responde el toque y quita el botón: se ve que el acuse llegó. Si falla, no importa:
        el acuse ya se tomó."""
        try:
            self._llamar("answerCallbackQuery", callback_query_id=cq["id"], text="Acuse registrado")
            mensaje = cq.get("message") or {}
            if mensaje:
                self._llamar(
                    "editMessageReplyMarkup",
                    chat_id=mensaje["chat"]["id"],
                    message_id=mensaje["message_id"],
                    reply_markup={"inline_keyboard": []},
                )
        except (httpx.TransportError, KeyError):
            pass


def _json(r: httpx.Response) -> dict[str, Any]:
    try:
        datos = r.json()
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}
