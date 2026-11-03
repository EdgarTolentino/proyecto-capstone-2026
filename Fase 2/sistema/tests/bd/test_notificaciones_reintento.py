"""`--reintentar-agotados`: borde de los intentos, rechazos permanentes que no se reviven."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from gepp_api.notificaciones.__main__ import main, reintentar_agotados
from gepp_api.notificaciones.canal import Aviso, Estado, ResultadoEnvio
from gepp_api.notificaciones.despachador import Despachador
from gepp_bd import transaccion
from gepp_bd.modelos import Auditoria, Notificacion
from gepp_bd.repositorios.notificaciones import MAXIMO_INTENTOS, PREFIJO_RECHAZO
from sqlalchemy import Engine, select, text, update

from .test_notificaciones_robustez import CanalFalso, filas, sembrar

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("intentos", "vuelve"),
    [(MAXIMO_INTENTOS - 1, False), (MAXIMO_INTENTOS, True), (MAXIMO_INTENTOS + 1, True)],
    ids=["4_no", "5_si", "6_si"],
)
def test_reintentar_agotados_en_el_borde(bd: Engine, intentos: int, vuelve: bool) -> None:
    sembrar(bd, 1)
    with transaccion(bd) as s:
        s.execute(update(Notificacion).values(estado="fallida", intentos=intentos))
    assert reintentar_agotados(bd) == int(vuelve)
    (n,) = filas(bd)
    assert (n.estado, n.intentos) == (("pendiente", 0) if vuelve else ("fallida", intentos))
    with transaccion(bd) as s:
        (a,) = s.execute(
            select(Auditoria).where(Auditoria.accion == "aviso:reintentar_agotados")
        ).scalars()
    assert a.motivo == f"{int(vuelve)} avisos vueltos a pendiente"


def test_reintentar_solo_toca_agotados_y_luego_se_envian(bd: Engine) -> None:
    sembrar(bd, 3)
    ids = [n.id for n in filas(bd)]
    estados = [("fallida", MAXIMO_INTENTOS), ("fallida", 1), ("enviada", MAXIMO_INTENTOS)]
    with transaccion(bd) as s:
        for i, (estado, intentos) in zip(ids, estados, strict=True):
            s.execute(
                update(Notificacion)
                .where(Notificacion.id == i)
                .values(estado=estado, intentos=intentos)
            )
    assert reintentar_agotados(bd) == 1
    # Rechazo permanente (1 intento) y enviada no se tocan: reintentarlos no arregla nada.
    assert [(n.estado, n.intentos) for n in filas(bd)] == [
        ("pendiente", 0),
        ("fallida", 1),
        ("enviada", MAXIMO_INTENTOS),
    ]
    canal = CanalFalso()
    assert Despachador(bd, canal).ciclo().avisos_enviados == 1


def test_una_opcion_desconocida_no_hace_nada_y_falla() -> None:
    with pytest.raises(SystemExit) as e:
        main(["--reintentar-todo"])
    assert e.value.code == 2


# ── 2. 4 fallos transitorios y un 403: el comando no lo reactiva ─────────────────────────


@dataclass
class CanalGuionado:
    nombre: str = "telegram"
    respuestas: list[ResultadoEnvio] = field(default_factory=list)

    def enviar(self, aviso: Aviso, destino: str) -> ResultadoEnvio:
        assert aviso.token_acuse and destino
        return self.respuestas.pop(0)

    def acuses_recibidos(self) -> list[str]:
        return []


def _correr(bd: Engine, respuestas: list[ResultadoEnvio]) -> None:
    d = Despachador(bd, CanalGuionado(respuestas=list(respuestas)))
    for _ in respuestas:
        with bd.begin() as c:  # sin esperar el reintento: como en test_despachador.py
            c.execute(text("UPDATE notificacion SET reintentar_despues = NULL"))
        d.ciclo()


TRANSITORIO = ResultadoEnvio(Estado.FALLO_TRANSITORIO, reintentar_en_s=30, motivo="502")
RECHAZO = ResultadoEnvio(Estado.RECHAZADO_PERMANENTE, motivo="403: bot bloqueado")


def test_cuatro_transitorios_y_un_403_no_se_reviven(bd: Engine) -> None:
    sembrar(bd, 1)
    _correr(bd, [TRANSITORIO] * (MAXIMO_INTENTOS - 1) + [RECHAZO])
    (n,) = filas(bd)
    assert (n.estado, n.intentos) == ("fallida", MAXIMO_INTENTOS)
    assert (n.motivo or "").startswith(PREFIJO_RECHAZO)
    assert reintentar_agotados(bd) == 0
    assert filas(bd)[0].estado == "fallida"


def test_cinco_transitorios_si_se_reviven(bd: Engine) -> None:  # el control del anterior
    sembrar(bd, 1)
    _correr(bd, [TRANSITORIO] * MAXIMO_INTENTOS)
    (n,) = filas(bd)
    assert (n.estado, n.intentos) == ("fallida", MAXIMO_INTENTOS)
    assert not (n.motivo or "").startswith(PREFIJO_RECHAZO)
    assert reintentar_agotados(bd) == 1
    assert (filas(bd)[0].estado, filas(bd)[0].intentos) == ("pendiente", 0)


@pytest.mark.parametrize(
    ("motivo", "vuelve"),
    [
        ("403: Forbidden: bot was blocked by the user", False),  # lo guardado con el código viejo
        ("401: Unauthorized", False),
        ("400: Bad Request: chat not found", False),
        ("428: borde de abajo", False),
        ("430: borde de arriba", False),
        ("429: Too Many Requests: retry after 17", True),  # transitorio: sí se reintenta
        ("502: Bad Gateway", True),
        ("ReadTimeout", True),
        ("4290: no es un código 4xx", True),
        ("500: el proxy dijo 403: prohibido", True),  # el 4xx va AL INICIO, no en cualquier parte
        (None, True),
    ],
    ids=[
        "403",
        "401",
        "400",
        "428",
        "430",
        "429",
        "502",
        "timeout",
        "4290",
        "403_adentro",
        "sin_motivo",
    ],
)
def test_los_rechazos_guardados_antes_del_prefijo_tampoco_se_reviven(
    bd: Engine, motivo: str | None, vuelve: bool
) -> None:
    sembrar(bd, 1)
    with transaccion(bd) as s:
        s.execute(
            update(Notificacion).values(estado="fallida", intentos=MAXIMO_INTENTOS, motivo=motivo)
        )
    assert reintentar_agotados(bd) == int(vuelve)
    assert filas(bd)[0].estado == ("pendiente" if vuelve else "fallida")
