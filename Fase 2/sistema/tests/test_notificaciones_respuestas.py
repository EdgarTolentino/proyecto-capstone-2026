"""Telegram contesta cosas raras: ninguna debe tumbar el proceso del despachador."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from gepp_api.notificaciones.canal import Aviso, Estado
from gepp_api.notificaciones.telegram import CanalTelegram

AVISO = Aviso("Acceso · turno B", "1 incumplimiento sin casco", "tok-1")


def canal(responder: Any) -> CanalTelegram:
    def manejador(req: httpx.Request) -> httpx.Response:
        metodo = req.url.path.rsplit("/", 1)[-1]
        return responder(metodo, json.loads(req.content or b"{}"))

    return CanalTelegram("1:SECRETO", httpx.Client(transport=httpx.MockTransport(manejador)))


def decodificacion(_m: str, _d: dict[str, Any]) -> httpx.Response:
    raise httpx.DecodingError("gzip roto")


def test_una_respuesta_que_no_se_decodifica_es_fallo_transitorio_y_no_excepcion() -> None:
    r = canal(decodificacion).enviar(AVISO, "chat-1")
    assert r.estado is Estado.FALLO_TRANSITORIO and r.motivo == "DecodingError"
    c = canal(decodificacion)
    assert c.acuses_recibidos() == [] and c.ultimo_error == "DecodingError"


def test_aceptado_sin_id_legible_se_identifica_por_el_token_del_aviso() -> None:
    for cuerpo in ({"ok": True}, {"ok": True, "result": "x"}, {"ok": True, "result": {}}):
        r = canal(lambda _m, _d, c=cuerpo: httpx.Response(200, json=c)).enviar(AVISO, "chat-1")
        assert (r.estado, r.id_externo) == (Estado.ACEPTADO, "sin-id:tok-1")


@pytest.mark.parametrize(
    ("retry_after", "esperado"),
    [(17, 17.0), ("17", 17.0), (0.5, 0.5), (0, 30.0), (-5, 30.0), ("abc", 30.0), (None, 30.0)],
    ids=["entero", "texto_numerico", "borde_positivo", "cero", "negativo", "texto", "nulo"],
)
def test_retry_after_invalido_cae_al_defecto(retry_after: Any, esperado: float) -> None:
    cuerpo = {"ok": False, "description": "Too Many", "parameters": {"retry_after": retry_after}}
    r = canal(lambda _m, _d: httpx.Response(429, json=cuerpo)).enviar(AVISO, "chat-1")
    assert (r.estado, r.reintentar_en_s) == (Estado.FALLO_TRANSITORIO, esperado)


def test_parameters_que_no_es_un_objeto_tambien_cae_al_defecto() -> None:
    cuerpo = {"ok": False, "parameters": "raro"}
    r = canal(lambda _m, _d: httpx.Response(429, json=cuerpo)).enviar(AVISO, "chat-1")
    assert r.reintentar_en_s == 30.0


def test_getupdates_con_result_que_no_es_lista_se_anota() -> None:
    c = canal(lambda _m, _d: httpx.Response(200, json={"ok": True, "result": {"x": 1}}))
    assert c.acuses_recibidos() == [] and c.ultimo_error == "respuesta inesperada de getUpdates"


def test_actualizaciones_malformadas_se_saltan_y_la_buena_se_toma() -> None:
    malas = [
        None,
        "texto",
        {"callback_query": {"data": "acuse:no"}},  # sin update_id
        {"update_id": "5", "callback_query": {"data": "acuse:no"}},  # update_id no entero
        {"update_id": 6, "callback_query": "x"},  # callback_query no es un objeto
        {"update_id": 7, "callback_query": {"id": "q", "data": 7}},  # data no es texto
        {"update_id": 8, "callback_query": {"id": "q", "data": "acuse:bueno"}},
    ]

    def responder(m: str, _d: dict[str, Any]) -> httpx.Response:
        if m == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": malas})
        return httpx.Response(200, json={"ok": True, "result": True})

    c = canal(responder)
    assert c.acuses_recibidos() == ["bueno"]
    assert c.ultimo_error is None
