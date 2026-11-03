"""Canal Telegram (Bot API por HTTPS). Implementa `CanalNotificacion`.

El token del bot es un secreto: vive en `GEPP_TELEGRAM_TOKEN`, nunca en el repositorio, y
ningún mensaje de error lo incluye (la URL de la API lo lleva dentro).

El acuse es el botón "Acuso recibo" del propio mensaje: Telegram lo entrega como
`callback_query` y se recoge con `getUpdates`, sin exponer ningún puerto hacia internet.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from gepp_api.notificaciones.canal import Aviso, Estado, ResultadoEnvio

API = "https://api.telegram.org"
PREFIJO_ACUSE = "acuse:"
MAXIMO_DESCRIPCION = 120

_URL = re.compile(r"https?://\S+")
_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_TOKEN = re.compile(r"\d{5,}:[\w-]{8,}")


def sanear(texto: str, token: str = "") -> str:
    """Lo que Telegram devuelve en `description` no es de fiar: puede traer una URL con el bot,
    el token o un correo. Antes de anotarlo (terminal, base) se quitan y se corta a largo fijo."""
    if token:
        texto = texto.replace(token, "<token>")
    texto = _URL.sub("<url>", texto)
    texto = _CORREO.sub("<correo>", texto)
    texto = _TOKEN.sub("<token>", texto)
    texto = " ".join(texto.split())
    return texto[:MAXIMO_DESCRIPCION]


class CanalTelegram:
    nombre = "telegram"

    def __init__(self, token: str, cliente: httpx.Client | None = None, base: str = API) -> None:
        if not token:
            raise ValueError("falta el token del bot (GEPP_TELEGRAM_TOKEN)")
        self._token = token
        self._url = f"{base}/bot{token}"
        self._http = cliente or httpx.Client(timeout=15)
        self._offset: int | None = None
        #: Por qué falló la última consulta de acuses (None si fue bien). Sin esto un webhook
        #: activo (409) o un token revocado (401) dejan los acuses mudos y nadie se entera.
        self.ultimo_error: str | None = None

    def _descripcion(self, cuerpo: dict[str, Any]) -> str:
        return sanear(str(cuerpo.get("description", "sin descripción")), self._token)

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
        except httpx.HTTPError as e:  # red, tiempo, respuesta que no se puede decodificar
            return ResultadoEnvio(
                Estado.FALLO_TRANSITORIO, reintentar_en_s=30, motivo=type(e).__name__
            )
        cuerpo = _json(r)
        if r.status_code == 200 and cuerpo.get("ok"):
            resultado = cuerpo.get("result")
            id_mensaje = resultado.get("message_id") if isinstance(resultado, dict) else None
            # Aceptado sin id legible: el aviso salió, se identifica por su token (no se reenvía).
            return ResultadoEnvio(
                Estado.ACEPTADO,
                id_externo=str(id_mensaje)
                if id_mensaje is not None
                else f"sin-id:{aviso.token_acuse}",
            )
        motivo = f"{r.status_code}: {self._descripcion(cuerpo)}"
        if r.status_code == 429:
            parametros = cuerpo.get("parameters")
            espera = _espera(
                parametros.get("retry_after") if isinstance(parametros, dict) else None
            )
            return ResultadoEnvio(Estado.FALLO_TRANSITORIO, reintentar_en_s=espera, motivo=motivo)
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
        except httpx.HTTPError as e:
            self.ultimo_error = type(e).__name__
            return []  # se reintenta en el próximo ciclo; Telegram guarda lo no confirmado
        cuerpo = _json(r)
        if r.status_code != 200 or not cuerpo.get("ok"):
            # 409: hay un webhook puesto y getUpdates no puede convivir con él. 401: token malo.
            self.ultimo_error = f"{r.status_code}: {self._descripcion(cuerpo)}"
            return []
        actualizaciones = cuerpo.get("result", [])
        if not isinstance(actualizaciones, list):
            self.ultimo_error = "respuesta inesperada de getUpdates"
            return []
        self.ultimo_error = None
        tokens = []
        for u in actualizaciones:
            if not isinstance(u, dict) or not isinstance(u.get("update_id"), int):
                continue  # sin update_id no se puede ni confirmar: se ignora
            self._offset = u["update_id"] + 1  # confirma el update: no vuelve a llegar
            cq = u.get("callback_query")
            if not isinstance(cq, dict):
                continue
            data = cq.get("data")
            if not isinstance(data, str) or not data.startswith(PREFIJO_ACUSE):
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
        except (httpx.HTTPError, KeyError, TypeError):
            pass


def _espera(valor: Any, defecto: float = 30.0) -> float:
    """`retry_after` de Telegram, o el defecto si viene mal (texto, negativo, cero, infinito)."""
    try:
        espera = float(valor)
    except (TypeError, ValueError):
        return defecto
    return espera if 0 < espera < float("inf") else defecto


def _json(r: httpx.Response) -> dict[str, Any]:
    try:
        datos = r.json()
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}
