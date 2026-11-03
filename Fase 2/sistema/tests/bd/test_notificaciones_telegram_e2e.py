"""«La alerta llega y el acuse vuelve»: despachador real + base real + Telegram simulado.

Nada sale a la red: el servidor de Telegram es un `httpx.MockTransport` con estado.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from gepp_api.notificaciones.despachador import Despachador
from gepp_api.notificaciones.telegram import CanalTelegram
from gepp_bd import transaccion
from gepp_bd.modelos import Notificacion
from gepp_bd.repositorios import hallazgos
from gepp_bd.semilla import cargar, leer
from gepp_core import Hallazgo, Severidad, TipoEPP
from sqlalchemy import Engine, select

from ..conftest import T0

pytestmark = pytest.mark.integration

PERFIL = Path(__file__).resolve().parents[2] / "perfiles" / "construccion.yaml"
GRUPO = "-100777"
GRAVE = Hallazgo(
    track_id=1,
    regla_id=1,
    regla_version=1,
    epp_faltante=frozenset({TipoEPP.CASCO}),
    severidad=Severidad.CRITICA,
    ts_inicio=T0,
    ts_fin=T0 + timedelta(seconds=30),
    cuadros_confirmados=150,
    confianza_media=0.9,
)


class TelegramFalso:
    """Guarda lo que se le manda y entrega toques de botón cuando se le piden."""

    def __init__(self, estado_envio: int = 200) -> None:
        self.llamadas: list[tuple[str, dict[str, Any]]] = []
        self.toques: list[dict[str, Any]] = []
        self.estado_envio = estado_envio

    def tocar(self, callback_data: str) -> None:
        self.toques.append(
            {
                "update_id": len(self.llamadas) + 100,
                "callback_query": {
                    "id": f"q{len(self.toques)}",
                    "from": {"id": 1, "first_name": "Profesor"},
                    "data": callback_data,
                    "message": {"message_id": 41, "chat": {"id": int(GRUPO)}},
                },
            }
        )

    def __call__(self, req: httpx.Request) -> httpx.Response:
        metodo = req.url.path.rsplit("/", 1)[-1]
        datos = json.loads(req.content or b"{}")
        self.llamadas.append((metodo, datos))
        if metodo == "sendMessage":
            if self.estado_envio != 200:
                return httpx.Response(self.estado_envio, json={"ok": False, "description": "x"})
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 41}})
        if metodo == "getUpdates":
            salida, self.toques = self.toques, []
            return httpx.Response(200, json={"ok": True, "result": salida})
        return httpx.Response(200, json={"ok": True, "result": True})

    def metodos(self) -> list[str]:
        return [m for m, _ in self.llamadas]


def _despachador(motor: Engine, tg: TelegramFalso) -> Despachador:
    canal = CanalTelegram("1:SECRETO", httpx.Client(transport=httpx.MockTransport(tg)))
    return Despachador(motor, canal)


def _filas(motor: Engine) -> list[Notificacion]:
    with transaccion(motor) as s:
        return list(s.execute(select(Notificacion).order_by(Notificacion.id)).scalars())


@pytest.fixture
def con_grave(bd: Engine) -> Engine:
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
    aviso = hallazgos.NuevaNotificacion(canal="telegram", destinatario=GRUPO)
    with transaccion(bd) as s:
        hallazgos.guardar(s, GRAVE, hallazgos.Contexto(fuente_id=1, area_id=1), [aviso])
    return bd


def test_la_alerta_llega_al_grupo_y_el_acuse_vuelve_a_la_base(con_grave: Engine) -> None:
    tg = TelegramFalso()
    d = _despachador(con_grave, tg)

    r = d.ciclo()
    assert r.avisos_enviados == 1
    envios = [datos for m, datos in tg.llamadas if m == "sendMessage"]
    assert len(envios) == 1 and envios[0]["chat_id"] == GRUPO
    assert "sendPhoto" not in tg.metodos()  # solo texto: ADR-006, ver alerta-en-vivo.md
    (n,) = _filas(con_grave)
    assert (n.estado, n.acusada_en) == ("enviada", None)  # entregado NO es acusado

    # El toque lleva el `callback_data` del botón del mensaje enviado, no uno armado aquí.
    boton = envios[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert boton == f"acuse:{n.token_acuse}"
    tg.tocar(boton)
    r = d.ciclo()
    assert r.acusados == 1
    (n,) = _filas(con_grave)
    assert n.estado == "acusada" and n.acusada_en is not None
    assert n.acusada_por is None  # un grupo acusa; no se guarda quién tocó
    assert "editMessageReplyMarkup" in tg.metodos()  # el botón desaparece en el grupo

    tg.tocar(boton)  # otro profesor toca después: no cambia nada
    assert d.ciclo().acusados == 0


def test_telegram_caido_no_pierde_la_alerta(con_grave: Engine) -> None:
    tg = TelegramFalso(estado_envio=503)
    r = _despachador(con_grave, tg).ciclo()
    assert (r.avisos_enviados, r.fallos) == (0, 1)
    (n,) = _filas(con_grave)
    assert (n.estado, n.intentos) == ("pendiente", 1) and n.reintentar_despues is not None
