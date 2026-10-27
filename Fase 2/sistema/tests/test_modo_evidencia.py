"""Modo de incumplimiento: por AUSENCIA (lo exigido que no se ve) o por EVIDENCIA (el modelo vio
la falta: `cabeza`, `sin_chaleco`). ADR-013, #31."""

from __future__ import annotations

import pytest
from gepp_core import (
    Caja,
    ClaseDetectada,
    Deteccion,
    ModoIncumplimiento,
    Regla,
    Severidad,
    TipoEPP,
    agregar,
    epp_faltante,
)
from gepp_core.asociacion import EVIDENCIA_DE_FALTA
from gepp_core.dominio import FRANJA_ESPERADA

from .conftest import PERSONA, caja_en_franja, cuadro, en

AUSENCIA, EVIDENCIA = ModoIncumplimiento.AUSENCIA, ModoIncumplimiento.EVIDENCIA
CASCO, CHALECO, LENTES = TipoEPP.CASCO, TipoEPP.CHALECO, TipoEPP.LENTES
#: Umbral diádico: los bordes son exactos (regla 5).
UMBRAL = 0.5
JUSTO_DEBAJO = UMBRAL - 2.0**-10


def _evidencia(
    clase: ClaseDetectada, caja: Caja, confianza: float = 0.75, t: float = 0, idx: int = 0
) -> Deteccion:
    return Deteccion(capture_ts=en(t), cuadro_idx=idx, clase=clase, caja=caja, confianza=confianza)


def _cabeza(
    confianza: float = 0.75, desde: float = 0.02, hasta: float = 0.18, t: float = 0, idx: int = 0
) -> Deteccion:
    caja = caja_en_franja(PERSONA, desde, hasta)
    return _evidencia(ClaseDetectada.CABEZA, caja, confianza, t, idx)


def _faltante(dets, exigido, modo, confianza_minima=UMBRAL):  # type: ignore[no-untyped-def]
    return epp_faltante(dets[0], dets, frozenset(exigido), confianza_minima, modo)


def _regla(modo: ModoIncumplimiento) -> Regla:
    return Regla(
        id=1,
        version=1,
        nombre="r",
        epp_exigido=frozenset({CASCO}),
        severidad=Severidad.ALTA,
        confianza_minima=UMBRAL,
        modo=modo,
    )


def test_el_modo_por_defecto_es_ausencia() -> None:
    r = Regla(id=1, version=1, nombre="r", epp_exigido=frozenset({CASCO}), severidad=Severidad.ALTA)
    assert r.modo is AUSENCIA


def test_casco_que_el_modelo_no_ve_falta_por_ausencia_pero_no_por_evidencia() -> None:
    """La persona lleva casco, el modelo no lo vio y tampoco vio una cabeza: sin evidencia."""
    dets = cuadro(t=0, idx=0, con_casco=False, con_chaleco=True)
    assert _faltante(dets, {CASCO}, AUSENCIA) == {CASCO}
    assert _faltante(dets, {CASCO}, EVIDENCIA) == set()


def test_cabeza_sin_casco_en_la_franja_falta() -> None:
    dets = [*cuadro(t=0, idx=0, con_casco=False), _cabeza()]
    assert _faltante(dets, {CASCO}, EVIDENCIA) == {CASCO}


def test_cabeza_fuera_de_la_franja_no_falta() -> None:
    """Una «cabeza» a la altura del pecho no es la cabeza de esta persona."""
    dets = [*cuadro(t=0, idx=0, con_casco=False), _cabeza(desde=0.40, hasta=0.60)]
    assert _faltante(dets, {CASCO}, EVIDENCIA) == set()


def test_cabeza_de_otra_persona_no_se_le_atribuye() -> None:
    otra = Caja(0.70, 0.20, 0.82, 0.80)
    dets = [
        *cuadro(t=0, idx=0, con_casco=False),
        _evidencia(ClaseDetectada.CABEZA, caja_en_franja(otra, 0.02, 0.18)),
    ]
    assert _faltante(dets, {CASCO}, EVIDENCIA) == set()


def test_casco_y_cabeza_a_la_vez_no_falta_porque_el_casco_esta_puesto() -> None:
    dets = [*cuadro(t=0, idx=0, con_casco=True), _cabeza()]
    assert _faltante(dets, {CASCO}, EVIDENCIA) == set()


def test_cabeza_justo_en_la_confianza_minima_cuenta_y_justo_debajo_no() -> None:
    en_borde = [*cuadro(t=0, idx=0, con_casco=False), _cabeza(UMBRAL)]
    debajo = [*cuadro(t=0, idx=0, con_casco=False), _cabeza(JUSTO_DEBAJO)]
    assert _faltante(en_borde, {CASCO}, EVIDENCIA) == {CASCO}
    assert _faltante(debajo, {CASCO}, EVIDENCIA) == set()


def test_sin_chaleco_funciona_igual_para_el_chaleco() -> None:
    caja = caja_en_franja(PERSONA, 0.30, 0.55)
    dets = [
        *cuadro(t=0, idx=0, con_chaleco=False),
        _evidencia(ClaseDetectada.SIN_CHALECO, caja),
    ]
    assert _faltante(dets, {CHALECO}, EVIDENCIA) == {CHALECO}
    assert _faltante(cuadro(t=0, idx=0, con_chaleco=False), {CHALECO}, EVIDENCIA) == set()


def test_la_evidencia_de_un_epp_no_vale_para_otro() -> None:
    """`cabeza` dice que falta el casco, no el chaleco."""
    dets = [*cuadro(t=0, idx=0, con_chaleco=False), _cabeza()]
    assert _faltante(dets, {CHALECO}, EVIDENCIA) == set()


def test_un_epp_sin_clase_de_evidencia_se_evalua_por_ausencia() -> None:
    """Lentes no tiene clase de evidencia: sin lentes visibles sigue faltando, en ambos modos."""
    assert LENTES not in EVIDENCIA_DE_FALTA.values()
    dets = cuadro(t=0, idx=0)
    assert _faltante(dets, {LENTES}, AUSENCIA) == {LENTES}
    assert _faltante(dets, {LENTES}, EVIDENCIA) == {LENTES}


def test_modo_mixto_solo_exige_evidencia_donde_la_hay() -> None:
    dets = cuadro(t=0, idx=0, con_casco=False, con_chaleco=False)
    assert _faltante(dets, {CASCO, CHALECO, LENTES}, EVIDENCIA) == {LENTES}


def test_el_agregador_usa_el_modo_de_la_regla() -> None:
    """Sin casco visible y sin cabeza durante 10 s: alerta por ausencia, ninguna por evidencia."""
    cuadros = [cuadro(t=i * 0.5, idx=i, con_casco=False) for i in range(21)]
    assert len(list(agregar(_regla(AUSENCIA), cuadros))) == 1
    assert list(agregar(_regla(EVIDENCIA), cuadros)) == []


def test_el_agregador_alerta_por_evidencia_sostenida() -> None:
    cuadros = [
        [*cuadro(t=i * 0.5, idx=i, con_casco=False), _cabeza(t=i * 0.5, idx=i)] for i in range(21)
    ]
    hallazgos = list(agregar(_regla(EVIDENCIA), cuadros))
    assert len(hallazgos) == 1 and hallazgos[0].epp_faltante == frozenset({CASCO})


@pytest.mark.parametrize("modo", ["ausencia", "evidencia"])
def test_el_modo_se_construye_desde_su_texto(modo: str) -> None:
    assert ModoIncumplimiento(modo).value == modo


def test_un_modo_desconocido_se_rechaza() -> None:
    with pytest.raises(ValueError):
        ModoIncumplimiento("otro")


# ── La asociación es por el CENTRO de la evidencia, con bordes incluidos (revisión de Codex) ──


def _franja_del_casco() -> Caja:
    return PERSONA.franja(*FRANJA_ESPERADA[CASCO])


def _cabeza_con_centro_en(cy: float, medio_alto: float) -> Deteccion:
    """Una cabeza cuyo centro vertical es exactamente `cy` (se comprueba, no se supone)."""
    caja = Caja(0.43, cy - medio_alto, 0.49, cy + medio_alto)
    assert caja.centro[1] == cy, "la caja de prueba no quedó centrada donde se pidió"
    return _evidencia(ClaseDetectada.CABEZA, caja)


def _cabeza_con_centro_en_aprox(cy: float, medio_alto: float = 2.0**-4) -> Deteccion:
    return _evidencia(ClaseDetectada.CABEZA, Caja(0.43, cy - medio_alto, 0.49, cy + medio_alto))


def test_un_sin_chaleco_con_la_caja_de_la_persona_entera_falta() -> None:
    """El modelo marca a la persona completa como `sin_chaleco`: la caja sale de la franja del
    chaleco, pero su CENTRO cae dentro. Exigir la caja entera dentro de la franja lo perdería."""
    dets = [
        *cuadro(t=0, idx=0, con_chaleco=False),
        _evidencia(ClaseDetectada.SIN_CHALECO, PERSONA),
    ]
    assert _faltante(dets, {CHALECO}, EVIDENCIA) == {CHALECO}


@pytest.mark.parametrize("borde", ["superior", "inferior"])
def test_una_cabeza_centrada_justo_en_el_borde_de_la_franja_cuenta(borde: str) -> None:
    franja = _franja_del_casco()
    cy = franja.y1 if borde == "superior" else franja.y2
    dets = [*cuadro(t=0, idx=0, con_casco=False), _cabeza_con_centro_en(cy, 2.0**-6)]
    assert _faltante(dets, {CASCO}, EVIDENCIA) == {CASCO}


@pytest.mark.parametrize("borde", ["superior", "inferior"])
def test_una_cabeza_centrada_justo_afuera_de_la_franja_no_cuenta(borde: str) -> None:
    franja = _franja_del_casco()
    hueco = 2.0**-20  # mucho mayor que el redondeo, mucho menor que cualquier error real
    cabeza = _cabeza_con_centro_en_aprox(
        franja.y1 - hueco if borde == "superior" else franja.y2 + hueco
    )
    centro = cabeza.caja.centro[1]
    assert centro < franja.y1 if borde == "superior" else centro > franja.y2  # precondición
    dets = [*cuadro(t=0, idx=0, con_casco=False), cabeza]
    assert _faltante(dets, {CASCO}, EVIDENCIA) == set()
