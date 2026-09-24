"""El adaptador de Telegram contra un servidor simulado: sin red y sin token real."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from gepp_api.notificaciones.canal import Aviso, CanalNotificacion, Estado
from gepp_api.notificaciones.telegram import CanalTelegram

TOKEN = "123456:SECRETO-DE-PRUEBA"
AVISO = Aviso("Acceso · turno B", "1 persona sin casco", "tok-1")


def canal(
    responder: Any, llamadas: list[tuple[str, dict[str, Any]]] | None = None
) -> CanalTelegram:
    def manejador(req: httpx.Request) -> httpx.Response:
        metodo = req.url.path.rsplit("/", 1)[-1]
        datos = json.loads(req.content or b"{}")
        if llamadas is not None:
            llamadas.append((metodo, datos))
        return responder(metodo, datos)

    return CanalTelegram(TOKEN, httpx.Client(transport=httpx.MockTransport(manejador)))


def test_cumple_el_puerto() -> None:
    assert isinstance(canal(lambda _m, _d: httpx.Response(200)), CanalNotificacion)


def test_envia_con_el_boton_de_acuse() -> None:
    llamadas: list[tuple[str, dict[str, Any]]] = []
    c = canal(
        lambda _m, _d: httpx.Response(200, json={"ok": True, "result": {"message_id": 77}}),
        llamadas,
    )
    r = c.enviar(AVISO, "chat-1")
    assert (r.estado, r.id_externo) == (Estado.ACEPTADO, "77")
    ((metodo, datos),) = llamadas
    assert metodo == "sendMessage" and datos["chat_id"] == "chat-1"
    boton = datos["reply_markup"]["inline_keyboard"][0][0]
    assert boton["callback_data"] == "acuse:tok-1"


@pytest.mark.parametrize(
    ("status", "cuerpo", "estado", "espera"),
    [
        (
            429,
            {"ok": False, "description": "Too Many", "parameters": {"retry_after": 17}},
            Estado.FALLO_TRANSITORIO,
            17,
        ),
        (502, {"ok": False, "description": "Bad Gateway"}, Estado.FALLO_TRANSITORIO, 60),
        (403, {"ok": False, "description": "bot was blocked"}, Estado.RECHAZADO_PERMANENTE, None),
        (400, {"ok": False, "description": "chat not found"}, Estado.RECHAZADO_PERMANENTE, None),
    ],
)
def test_clasifica_los_errores(
    status: int, cuerpo: dict[str, Any], estado: Estado, espera: float | None
) -> None:
    r = canal(lambda _m, _d: httpx.Response(status, json=cuerpo)).enviar(AVISO, "chat-1")
    assert (r.estado, r.reintentar_en_s) == (estado, espera)
    assert TOKEN not in (r.motivo or "")  # el secreto nunca aparece en un motivo


def test_sin_red_es_fallo_transitorio() -> None:
    def cae(_m: str, _d: dict[str, Any]) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    r = canal(cae).enviar(AVISO, "chat-1")
    assert r.estado is Estado.FALLO_TRANSITORIO and TOKEN not in (r.motivo or "")


def test_recoge_los_acuses_y_quita_el_boton() -> None:
    llamadas: list[tuple[str, dict[str, Any]]] = []
    actualizaciones = {
        "ok": True,
        "result": [
            {
                "update_id": 10,
                "callback_query": {
                    "id": "q1",
                    "data": "acuse:tok-1",
                    "message": {"message_id": 77, "chat": {"id": 5}},
                },
            },
            {"update_id": 11, "callback_query": {"id": "q2", "data": "otra-cosa"}},
        ],
    }

    def responder(m: str, d: dict[str, Any]) -> httpx.Response:
        if m == "getUpdates":
            return httpx.Response(
                200, json=actualizaciones if "offset" not in d else {"ok": True, "result": []}
            )
        return httpx.Response(200, json={"ok": True, "result": True})

    c = canal(responder, llamadas)
    assert c.acuses_recibidos() == ["tok-1"]
    assert [m for m, _ in llamadas] == [
        "getUpdates",
        "answerCallbackQuery",
        "editMessageReplyMarkup",
    ]
    assert c.acuses_recibidos() == []  # confirmados con offset: no vuelven
    assert llamadas[-1] == (
        "getUpdates",
        {"timeout": 0, "allowed_updates": ["callback_query"], "offset": 12},
    )
