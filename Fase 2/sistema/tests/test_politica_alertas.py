"""Política de alertas (ADR-008): dos velocidades, agrupación, esperas y presupuesto."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from gepp_api.notificaciones.canal import MAXIMO_CUERPO, Aviso
from gepp_api.notificaciones.politica import (
    ESPERA_GLOBAL,
    ESPERA_POR_CAMARA,
    PRESUPUESTO_POR_TURNO,
    Decision,
    Historial,
    Pendiente,
    agrupar,
    decidir,
    es_grave,
    texto_inmediato,
    texto_resumen,
)

from .conftest import T0

TZ = ZoneInfo("America/Santiago")


def pend(
    i: int,
    *,
    sev: int = 4,
    dur: float = 30,
    area: str = "Acceso",
    fuente: int = 1,
    epp: tuple[str, ...] = ("casco",),
    dest: str = "chat-1",
    t: float = 0,
) -> Pendiente:
    return Pendiente(
        i,
        dest,
        "telegram",
        area,
        fuente,
        epp,
        sev,
        dur,
        T0 + timedelta(seconds=t),
        T0 + timedelta(seconds=t + dur),
    )


@pytest.mark.parametrize(
    ("sev", "dur", "grave"),
    [(4, 1, True), (3, 120.0, False), (3, 120.1, True), (1, 10, False)],
)
def test_solo_lo_grave_avisa_en_el_momento(sev: int, dur: float, grave: bool) -> None:
    assert es_grave(pend(1, sev=sev, dur=dur)) is grave


def test_tres_personas_sin_casco_en_un_area_son_un_solo_mensaje() -> None:
    grupos = agrupar([pend(1), pend(2, t=60), pend(3, t=120), pend(4, epp=("chaleco",))])
    assert sorted(len(g.items) for g in grupos) == [1, 3]


def test_el_presupuesto_corta_en_el_septimo() -> None:
    h = Historial()
    ahora = T0
    enviados = 0
    for i in range(PRESUPUESTO_POR_TURNO + 1):
        (v,) = decidir(agrupar([pend(i, fuente=i, area=f"A{i}")]), h, ahora)
        enviados += v.decision is Decision.ENVIAR
        if i < PRESUPUESTO_POR_TURNO:
            assert v.decision is Decision.ENVIAR
        else:
            assert (v.decision, v.motivo) == (Decision.AL_RESUMEN, "presupuesto_agotado")
        ahora += ESPERA_GLOBAL  # justo en el borde: la espera ya se cumplió
    assert enviados == PRESUPUESTO_POR_TURNO


def test_la_espera_global_retiene_y_despues_suelta() -> None:
    h = Historial()
    (a, b) = decidir(agrupar([pend(1, area="A", fuente=1), pend(2, area="B", fuente=2)]), h, T0)
    assert (a.decision, b.decision) == (Decision.ENVIAR, Decision.ESPERAR)
    (b2,) = decidir(
        agrupar([pend(2, area="B", fuente=2)]), h, T0 + ESPERA_GLOBAL - timedelta(seconds=1)
    )
    assert b2.decision is Decision.ESPERAR
    (b3,) = decidir(agrupar([pend(2, area="B", fuente=2)]), h, T0 + ESPERA_GLOBAL)
    assert b3.decision is Decision.ENVIAR


def test_una_camara_recien_avisada_no_vuelve_a_interrumpir() -> None:
    h = Historial()
    decidir(agrupar([pend(1, fuente=7)]), h, T0)
    (v,) = decidir(agrupar([pend(2, fuente=7, epp=("chaleco",))]), h, T0 + ESPERA_GLOBAL)
    assert (v.decision, v.motivo) == (Decision.AL_RESUMEN, "espera_por_camara")
    (v2,) = decidir(agrupar([pend(3, fuente=7, epp=("chaleco",))]), h, T0 + ESPERA_POR_CAMARA)
    assert v2.decision is Decision.ENVIAR


def test_el_aviso_nombra_area_y_turno_nunca_a_una_persona() -> None:
    (g,) = agrupar([pend(1), pend(2, t=240)])
    titulo, cuerpo = texto_inmediato(g, "B", TZ)
    assert titulo == "Acceso · turno B"
    # T0 = 22:10 en Santiago; el segundo termina 4 min 30 s después.
    assert cuerpo.startswith("2 personas sin casco entre 22:10 y 22:14.")
    assert "Requiere validación humana" in cuerpo
    Aviso(titulo, cuerpo, "t")  # respeta los límites del canal más restrictivo


def test_el_resumen_cabe_en_el_canal_mas_restrictivo() -> None:
    filas = [(f"Área de trabajo número {i:03d}", ("casco", "chaleco", "arnes")) for i in range(200)]
    titulo, cuerpo = texto_resumen(filas, "A")
    assert len(cuerpo) <= MAXIMO_CUERPO and cuerpo.endswith("Requiere validación humana.")
    assert titulo == "Resumen del turno A"


def test_un_aviso_demasiado_largo_no_se_construye() -> None:
    with pytest.raises(ValueError, match="título"):
        Aviso("x" * 61, "cuerpo", "t")
