"""Acuses por Telegram: errores de `getUpdates` que no se callan y toques desde un grupo."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from gepp_api.notificaciones.__main__ import anunciar_cambio
from gepp_api.notificaciones.canal import Aviso
from gepp_api.notificaciones.telegram import MAXIMO_DESCRIPCION, CanalTelegram, sanear

TOKEN = "123456:SECRETO-DE-PRUEBA"


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


@pytest.mark.parametrize(
    ("status", "descripcion"),
    [
        (409, "Conflict: can't use getUpdates method while webhook is active"),
        (401, "Unauthorized"),
        (200, "ok en falso con 200"),
    ],
)
def test_si_getupdates_falla_no_calla_y_se_recupera(status: int, descripcion: str) -> None:
    respuestas = [
        httpx.Response(status, json={"ok": False, "description": descripcion}),
        httpx.Response(200, json={"ok": True, "result": []}),
    ]
    c = canal(lambda _m, _d: respuestas.pop(0))
    assert c.acuses_recibidos() == []
    assert descripcion in (c.ultimo_error or "")
    assert TOKEN not in (c.ultimo_error or "")
    assert c.acuses_recibidos() == [] and c.ultimo_error is None  # una consulta buena lo limpia


def test_sin_red_en_getupdates_queda_anotado() -> None:
    def cae(_m: str, _d: dict[str, Any]) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    c = canal(cae)
    assert c.acuses_recibidos() == [] and c.ultimo_error == "ConnectError"


def test_el_toque_de_un_grupo_acusa_sin_llevar_quien_toco() -> None:
    """Un grupo (chat_id negativo) con profesores: el acuse es del aviso, no de una persona."""
    llamadas: list[tuple[str, dict[str, Any]]] = []
    toque = {
        "update_id": 3,
        "callback_query": {
            "id": "q9",
            "from": {"id": 555, "first_name": "Profesora", "username": "prof"},
            "data": "acuse:tok-g",
            "message": {"message_id": 8, "chat": {"id": -100123, "type": "supergroup"}},
        },
    }
    lista = [{"ok": True, "result": [toque]}]

    def responder(m: str, _d: dict[str, Any]) -> httpx.Response:
        if m == "getUpdates":
            return httpx.Response(200, json=lista.pop(0) if lista else {"ok": True, "result": []})
        return httpx.Response(200, json={"ok": True, "result": True})

    c = canal(responder, llamadas)
    assert c.acuses_recibidos() == ["tok-g"]  # solo el token: nada de `from`
    cerrar = [d for m, d in llamadas if m == "editMessageReplyMarkup"]
    assert cerrar == [
        {"chat_id": -100123, "message_id": 8, "reply_markup": {"inline_keyboard": []}}
    ]
    salida = json.dumps(llamadas)
    assert "Profesora" not in salida and "555" not in salida


SUCIA = (
    f"Bad Request: ver https://api.telegram.org/bot{TOKEN}/getUpdates, escribir a "
    "soporte@ejemplo.cl o usar 987654321:AAAA-token-suelto-0000 " + "x" * 500
)


def _sin_secretos(texto: str) -> None:
    for prohibido in (TOKEN, "SECRETO", "api.telegram.org", "soporte@", "987654321", "https://"):
        assert prohibido not in texto, prohibido
    assert len(texto) <= 5 + MAXIMO_DESCRIPCION  # «409: » + la descripción cortada


def test_lo_que_dice_telegram_se_sanea_en_ultimo_error_y_en_el_motivo() -> None:
    cuerpo = {"ok": False, "description": SUCIA}
    c = canal(lambda _m, _d: httpx.Response(409, json=cuerpo))
    c.acuses_recibidos()
    _sin_secretos(c.ultimo_error or "")
    assert "<url>" in (c.ultimo_error or "") and "<correo>" in (c.ultimo_error or "")
    r = c.enviar(Aviso("t", "c", "tok"), "chat-1")  # el mismo cuerpo, ahora en el envío
    _sin_secretos(r.motivo or "")


@pytest.mark.parametrize(
    ("largo", "esperado"),
    [
        (0, 0),
        (MAXIMO_DESCRIPCION - 1, MAXIMO_DESCRIPCION - 1),
        (MAXIMO_DESCRIPCION, MAXIMO_DESCRIPCION),
        (MAXIMO_DESCRIPCION + 1, MAXIMO_DESCRIPCION),
    ],
)
def test_el_largo_se_corta_justo_en_el_limite(largo: int, esperado: int) -> None:
    assert len(sanear("a" * largo)) == esperado


def test_anunciar_cambio_imprime_el_error_una_vez_y_la_recuperacion(
    capsys: pytest.CaptureFixture[str],
) -> None:
    estado: str | None = None
    for actual, imprime in [
        (None, False),  # arranque sano: nada
        ("409: Conflict", True),
        ("409: Conflict", False),  # el mismo error no se repite
        ("401: Unauthorized", True),  # otro error sí
        (None, True),  # recuperado
        (None, False),
    ]:
        estado = anunciar_cambio("acuses", estado, actual)
        salida = capsys.readouterr().err
        assert estado == actual
        assert bool(salida) == imprime, (actual, salida)
        if imprime:
            assert salida == f"[despachador] acuses: {actual or 'recuperado'}\n"
