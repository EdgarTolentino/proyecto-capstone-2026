"""El despachador no muere con la base y los avisos agotados se pueden reintentar."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from gepp_api.notificaciones import despachador as modulo
from gepp_api.notificaciones.canal import Aviso, Estado, ResultadoEnvio
from gepp_api.notificaciones.despachador import Despachador
from gepp_bd import transaccion
from gepp_bd.modelos import Notificacion
from gepp_bd.repositorios import hallazgos
from gepp_bd.semilla import cargar, leer
from gepp_core import Hallazgo, Severidad, TipoEPP
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.exc import OperationalError

from ..conftest import T0

pytestmark = pytest.mark.integration

PERFIL = Path(__file__).resolve().parents[2] / "perfiles" / "construccion.yaml"
BASE = Hallazgo(
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


@dataclass
class CanalFalso:
    nombre: str = "telegram"
    enviados: list[tuple[Aviso, str]] = field(default_factory=list)
    acuses: list[str] = field(default_factory=list)

    def enviar(self, aviso: Aviso, destino: str) -> ResultadoEnvio:
        self.enviados.append((aviso, destino))
        return ResultadoEnvio(Estado.ACEPTADO, id_externo=str(len(self.enviados)))

    def acuses_recibidos(self) -> list[str]:
        salida, self.acuses = self.acuses, []
        return salida


def sembrar(bd: Engine, n: int) -> None:
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
    aviso = hallazgos.NuevaNotificacion(canal="telegram", destinatario="chat-1")
    with transaccion(bd) as s:
        for i in range(n):
            h = replace(BASE, track_id=i + 1)
            hallazgos.guardar(s, h, hallazgos.Contexto(fuente_id=1, area_id=1), [aviso])


def filas(bd: Engine) -> list[Notificacion]:
    with transaccion(bd) as s:
        return list(s.execute(select(Notificacion).order_by(Notificacion.id)).scalars())


def test_con_la_base_caida_el_ciclo_no_lanza_y_lo_anota() -> None:
    caida = create_engine(
        "postgresql+psycopg://gepp:x@127.0.0.1:1/gepp", connect_args={"connect_timeout": 1}
    )
    r = Despachador(caida, CanalFalso()).ciclo()
    assert r.error_bd is not None and r.avisos_enviados == 0


def test_un_acuse_no_se_pierde_si_la_base_cae_justo_entonces(
    bd: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sembrar(bd, 1)
    canal = CanalFalso()
    d = Despachador(bd, canal)
    assert d.ciclo().avisos_enviados == 1
    canal.acuses = [filas(bd)[0].token_acuse or ""]  # Telegram lo entrega una sola vez

    real = modulo.transaccion
    cae: list[Any] = [True]

    def transaccion_que_cae(motor: Engine) -> Any:
        if cae:
            cae.clear()
            raise OperationalError("select 1", {}, Exception("base caída"))
        return real(motor)

    monkeypatch.setattr(modulo, "transaccion", transaccion_que_cae)
    r = d.ciclo()
    assert r.error_bd is not None and r.acusados == 0
    r = d.ciclo()  # la base volvió: el acuse que ya había salido del canal se guarda ahora
    assert r.error_bd is None and r.acusados == 1
    assert filas(bd)[0].estado == "acusada"
    assert d.ciclo().acusados == 0  # y no se re-aplica en cada ciclo siguiente
    assert d._acuses_sin_guardar == []
