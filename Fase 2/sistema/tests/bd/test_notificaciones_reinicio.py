"""Acuses que sobreviven a un reinicio, rechazos que no se reviven y errores de base varios."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from gepp_api.notificaciones import despachador as modulo
from gepp_api.notificaciones.despachador import Despachador
from gepp_api.notificaciones.telegram import CanalTelegram
from gepp_bd import transaccion
from gepp_bd.modelos import Notificacion
from gepp_bd.repositorios import hallazgos
from gepp_bd.semilla import cargar, leer
from gepp_core import Hallazgo, Severidad, TipoEPP
from sqlalchemy import Engine, select
from sqlalchemy.exc import InvalidRequestError, OperationalError
from sqlalchemy.exc import TimeoutError as TiempoDelPool

from ..conftest import T0

pytestmark = pytest.mark.integration

PERFIL = Path(__file__).resolve().parents[2] / "perfiles" / "construccion.yaml"
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


@pytest.fixture
def con_grave(bd: Engine) -> Engine:
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
    aviso = hallazgos.NuevaNotificacion(canal="telegram", destinatario="-100777")
    with transaccion(bd) as s:
        hallazgos.guardar(s, replace(GRAVE), hallazgos.Contexto(fuente_id=1, area_id=1), [aviso])
    return bd


def filas(bd: Engine) -> list[Notificacion]:
    with transaccion(bd) as s:
        return list(s.execute(select(Notificacion).order_by(Notificacion.id)).scalars())


def base_caida(*_: Any) -> Any:
    raise OperationalError("select 1", {}, Exception("base caída"))


# ── 1. Un reinicio con la base caída no pierde el acuse ──────────────────────────────────


class TelegramConOffset:
    """Telegram que respeta `offset`: lo confirmado no vuelve; lo no confirmado sí."""

    def __init__(self) -> None:
        self.boton = ""
        self.updates: list[dict[str, Any]] = []
        self.pedidos: list[int | None] = []

    def tocar(self) -> None:
        self.updates.append(
            {
                "update_id": 10,
                "callback_query": {
                    "id": "q1",
                    "data": self.boton,
                    "message": {"message_id": 41, "chat": {"id": -100777}},
                },
            }
        )

    def __call__(self, req: httpx.Request) -> httpx.Response:
        metodo = req.url.path.rsplit("/", 1)[-1]
        datos = json.loads(req.content or b"{}")
        if metodo == "getUpdates":
            offset = datos.get("offset")
            self.pedidos.append(offset)
            if offset is not None:
                self.updates = [u for u in self.updates if u["update_id"] >= offset]
            return httpx.Response(200, json={"ok": True, "result": list(self.updates)})
        if metodo == "sendMessage":
            self.boton = datos["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 41}})
        return httpx.Response(200, json={"ok": True, "result": True})


def _despachador(bd: Engine, tg: TelegramConOffset) -> Despachador:
    return Despachador(
        bd, CanalTelegram("1:SECRETO", httpx.Client(transport=httpx.MockTransport(tg)))
    )


def test_un_reinicio_con_la_base_caida_no_pierde_el_acuse(
    con_grave: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    tg = TelegramConOffset()
    d1 = _despachador(con_grave, tg)
    assert d1.ciclo().avisos_enviados == 1
    tg.tocar()

    with monkeypatch.context() as m:
        m.setattr(modulo, "transaccion", base_caida)
        for _ in range(3):  # la base sigue caída varios ciclos
            assert d1.ciclo().error_bd is not None
    # Con acuses sin guardar no se vuelve a pedir updates: no se confirma el offset ante Telegram.
    assert len([o for o in tg.pedidos if o is not None]) == 0

    d2 = _despachador(con_grave, tg)  # el proceso se reinicia: la lista en memoria se perdió
    assert d2.ciclo().acusados == 1
    assert filas(con_grave)[0].estado == "acusada"


# ── 5. Un acuse deshecho no se informa como guardado ─────────────────────────────────────


def test_si_la_transaccion_revierte_no_se_cuenta_el_acuse(
    con_grave: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    tg = TelegramConOffset()
    d = _despachador(con_grave, tg)
    d.ciclo()
    tg.tocar()
    real = modulo.transaccion
    cierres: list[int] = []

    @contextmanager
    def revierte_al_cerrar(motor: Engine) -> Iterator[Any]:
        with real(motor) as s:
            yield s
            cierres.append(1)
            raise OperationalError("commit", {}, Exception("se cortó al confirmar"))

    with monkeypatch.context() as m:
        m.setattr(modulo, "transaccion", revierte_al_cerrar)
        r = d.ciclo()
    assert cierres and r.error_bd is not None and r.acusados == 0
    assert filas(con_grave)[0].estado == "enviada"  # la base no lo guardó
    assert d.ciclo().acusados == 1  # y el acuse retenido se guarda en el ciclo siguiente


# ── 4. Ninguna falla de SQLAlchemy tumba el ciclo; un error de programación sí se ve ─────


@pytest.mark.parametrize(
    "error", [TiempoDelPool("pool agotado"), InvalidRequestError("sesión inválida")]
)
def test_otras_fallas_de_sqlalchemy_tampoco_tumban_el_ciclo(
    con_grave: Engine, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def falla(*_: Any) -> Any:
        raise error

    monkeypatch.setattr(modulo, "transaccion", falla)
    r = _despachador(con_grave, TelegramConOffset()).ciclo()
    assert r.error_bd == type(error).__name__


def test_un_error_de_programacion_no_se_traga(
    con_grave: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falla(*_: Any) -> Any:
        raise ValueError("bug")

    monkeypatch.setattr(modulo, "transaccion", falla)
    with pytest.raises(ValueError):
        _despachador(con_grave, TelegramConOffset()).ciclo()
