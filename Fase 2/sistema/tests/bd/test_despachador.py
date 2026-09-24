"""El despachador contra PostgreSQL real, con un canal falso que registra lo que "envía"."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from gepp_api.notificaciones.canal import Aviso, Estado, ResultadoEnvio
from gepp_api.notificaciones.despachador import Despachador
from gepp_api.notificaciones.politica import PRESUPUESTO_POR_TURNO
from gepp_bd import transaccion
from gepp_bd.modelos import Auditoria, Notificacion
from gepp_bd.repositorios import hallazgos
from gepp_bd.semilla import cargar, leer
from gepp_core import Hallazgo, Severidad, TipoEPP
from sqlalchemy import Engine, select, text

from ..conftest import T0

pytestmark = pytest.mark.integration

SANTIAGO = ZoneInfo("America/Santiago")
PERFIL = Path(__file__).resolve().parents[2] / "perfiles" / "construccion.yaml"


@dataclass
class CanalFalso:
    nombre: str = "telegram"
    respuestas: list[ResultadoEnvio] = field(default_factory=list)
    enviados: list[tuple[Aviso, str]] = field(default_factory=list)
    acuses: list[str] = field(default_factory=list)

    def enviar(self, aviso: Aviso, destino: str) -> ResultadoEnvio:
        self.enviados.append((aviso, destino))
        if self.respuestas:
            return self.respuestas.pop(0)
        return ResultadoEnvio(Estado.ACEPTADO, id_externo=str(len(self.enviados)))

    def acuses_recibidos(self) -> list[str]:
        salida, self.acuses = self.acuses, []
        return salida


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


def sembrar(motor: Engine, *hs: Hallazgo, area_id: int = 1, fuente_id: int = 1) -> None:
    aviso = hallazgos.NuevaNotificacion(canal="telegram", destinatario="chat-1")
    with transaccion(motor) as s:
        for h in hs:
            hallazgos.guardar(
                s, h, hallazgos.Contexto(fuente_id=fuente_id, area_id=area_id), [aviso]
            )


def filas(motor: Engine) -> list[Notificacion]:
    with transaccion(motor) as s:
        return list(s.execute(select(Notificacion).order_by(Notificacion.id)).scalars())


@pytest.fixture
def sembrada(bd: Engine) -> Engine:
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
    return bd


def test_lo_corriente_no_interrumpe_va_al_resumen(sembrada: Engine) -> None:
    sembrar(sembrada, replace(BASE, severidad=Severidad.ALTA))
    canal = CanalFalso()
    r = Despachador(sembrada, canal).ciclo()
    assert canal.enviados == [] and r.al_resumen == 1
    (n,) = filas(sembrada)
    assert (n.tipo, n.estado, n.motivo) == ("resumen_turno", "pendiente", "corriente")


def test_tres_graves_de_un_area_son_un_solo_aviso_sin_nombres(sembrada: Engine) -> None:
    sembrar(
        sembrada,
        *(
            replace(
                BASE,
                track_id=i,
                ts_inicio=T0 + timedelta(seconds=60 * i),
                ts_fin=T0 + timedelta(seconds=60 * i + 30),
            )
            for i in range(3)
        ),
    )
    canal = CanalFalso()
    r = Despachador(sembrada, canal).ciclo()
    assert r.avisos_enviados == 1
    ((aviso, destino),) = canal.enviados
    assert destino == "chat-1"
    assert aviso.titulo.startswith("Acceso y patio de materiales · turno ")
    assert aviso.cuerpo.startswith("3 personas sin casco entre 22:10 y 22:12")
    ns = filas(sembrada)
    assert {n.estado for n in ns} == {"enviada"} and len({n.token_acuse for n in ns}) == 1


def test_el_acuse_cierra_el_grupo_y_el_token_es_de_un_solo_uso(sembrada: Engine) -> None:
    sembrar(sembrada, BASE, replace(BASE, track_id=2))
    canal = CanalFalso()
    Despachador(sembrada, canal).ciclo()
    token = canal.enviados[0][0].token_acuse
    canal.acuses = [token, token]
    r = Despachador(sembrada, canal).ciclo()
    assert r.acusados == 2  # las dos filas del grupo, una sola vez
    assert {n.estado for n in filas(sembrada)} == {"acusada"}
    assert all(n.acusada_en is not None for n in filas(sembrada))


# Un instante fijo a media tarde del turno A y otro de madrugada del turno B, que empezó la
# víspera: con `now()` la prueba fallaba si corría en los 11 minutos que siguen a un cambio de
# turno, porque los seis avisos "de este turno" quedaban en el anterior.
@pytest.mark.parametrize(
    "ahora",
    [
        datetime(2026, 9, 2, 14, 0, tzinfo=SANTIAGO),
        datetime(2026, 9, 3, 2, 0, tzinfo=SANTIAGO),
    ],
    ids=["turno_A", "turno_B_tras_medianoche"],
)
def test_el_presupuesto_de_seis_por_turno_se_cumple_y_queda_registrado(
    sembrada: Engine, ahora: datetime
) -> None:
    # Seis avisos ya enviados en este turno (ids externos distintos, hace más de 10 min).
    sembrar(
        sembrada, *(replace(BASE, track_id=i) for i in range(PRESUPUESTO_POR_TURNO)), fuente_id=2
    )
    with sembrada.begin() as c:
        c.execute(
            text(
                "UPDATE notificacion SET estado='enviada', id_externo=id::text,"
                " enviada_en = :en, creada_en = :en"
            ),
            {"en": ahora - timedelta(minutes=11)},
        )
    sembrar(sembrada, replace(BASE, track_id=99))  # el séptimo, en otra cámara
    with sembrada.begin() as c:
        c.execute(
            text("UPDATE notificacion SET creada_en = :en WHERE estado = 'pendiente'"),
            {"en": ahora - timedelta(minutes=1)},
        )
    canal = CanalFalso()
    r = Despachador(sembrada, canal, reloj=lambda: ahora).ciclo()
    assert canal.enviados == [] and r.motivos == ["presupuesto_agotado"]
    septima = filas(sembrada)[-1]
    assert (septima.tipo, septima.motivo) == ("resumen_turno", "presupuesto_agotado")
    with transaccion(sembrada) as s:
        acciones = list(s.execute(select(Auditoria.accion)).scalars())
    assert acciones == ["aviso:presupuesto_agotado"]


def test_si_el_canal_se_cae_no_se_pierde_nada(sembrada: Engine) -> None:
    sembrar(sembrada, BASE)
    caido = ResultadoEnvio(Estado.FALLO_TRANSITORIO, reintentar_en_s=30, motivo="ConnectError")
    canal = CanalFalso(respuestas=[caido])
    d = Despachador(sembrada, canal)
    assert d.ciclo().fallos == 1
    (n,) = filas(sembrada)
    assert (n.estado, n.intentos, n.motivo) == ("pendiente", 1, "ConnectError")
    d.ciclo()  # todavía no toca reintentar
    assert len(canal.enviados) == 1
    with sembrada.begin() as c:
        c.execute(text("UPDATE notificacion SET reintentar_despues = now() - interval '1 second'"))
    assert d.ciclo().avisos_enviados == 1  # el canal volvió: sale
    assert filas(sembrada)[0].estado == "enviada"


def test_tras_cinco_fallos_queda_fallida_y_un_rechazo_no_se_reintenta(sembrada: Engine) -> None:
    sembrar(sembrada, BASE)
    caido = ResultadoEnvio(Estado.FALLO_TRANSITORIO, reintentar_en_s=0, motivo="500")
    canal = CanalFalso(respuestas=[caido] * 5)
    d = Despachador(sembrada, canal)
    for _ in range(5):
        with sembrada.begin() as c:
            c.execute(text("UPDATE notificacion SET reintentar_despues = NULL"))
        d.ciclo()
    assert (filas(sembrada)[0].estado, filas(sembrada)[0].intentos) == ("fallida", 5)

    sembrar(sembrada, replace(BASE, track_id=5), fuente_id=2)
    rechazo = ResultadoEnvio(Estado.RECHAZADO_PERMANENTE, motivo="403: bot bloqueado")
    Despachador(sembrada, CanalFalso(respuestas=[rechazo])).ciclo()
    assert (filas(sembrada)[-1].estado, filas(sembrada)[-1].intentos) == ("fallida", 1)


def test_al_empezar_el_turno_sale_el_resumen_del_anterior(sembrada: Engine) -> None:
    sembrar(sembrada, *(replace(BASE, severidad=Severidad.MEDIA, track_id=i) for i in range(3)))
    canal = CanalFalso()
    d = Despachador(sembrada, canal)
    d.ciclo()  # los tres bajan al resumen del turno en curso
    assert canal.enviados == []
    with sembrada.begin() as c:  # ... y ese turno ya terminó
        c.execute(text("UPDATE notificacion SET creada_en = now() - interval '13 hours'"))
    r = d.ciclo()
    assert r.resumenes == 1
    ((aviso, _),) = canal.enviados
    assert aviso.titulo.startswith("Resumen del turno ")
    assert "• Acceso y patio de materiales: 3 sin casco" in aviso.cuerpo
    assert {n.estado for n in filas(sembrada)} == {"enviada"}
