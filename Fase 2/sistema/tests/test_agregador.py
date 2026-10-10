"""La pieza que convierte 18.000 cuadros en una docena de hallazgos (ADR-004)."""

from __future__ import annotations

import random
from itertools import pairwise

import pytest
from gepp_core import AgregadorDeHallazgos, Caja, Regla, Severidad, TipoEPP, agregar

from .conftest import cuadro, en


def secuencia(*, sin_casco_desde: float, sin_casco_hasta: float, total: float, fps: float):
    """Genera cuadros a `fps`, sin casco en el intervalo indicado."""
    paso = 1.0 / fps
    n = int(total * fps)
    for i in range(n):
        t = i * paso
        yield cuadro(t=t, idx=i, con_casco=not (sin_casco_desde <= t < sin_casco_hasta))


def test_incumplimiento_breve_no_genera_hallazgo(regla: Regla) -> None:
    """Un casco tapado medio segundo por un brazo no puede disparar una alerta."""
    cuadros = secuencia(sin_casco_desde=1.0, sin_casco_hasta=1.6, total=10.0, fps=5)
    assert list(agregar(regla, cuadros)) == []


def test_incumplimiento_sostenido_genera_un_hallazgo(regla: Regla) -> None:
    cuadros = secuencia(sin_casco_desde=1.0, sin_casco_hasta=9.0, total=12.0, fps=5)
    hallazgos = list(agregar(regla, cuadros))

    assert len(hallazgos) == 1
    h = hallazgos[0]
    assert h.epp_faltante == {TipoEPP.CASCO}
    assert h.severidad is Severidad.ALTA
    assert h.regla_id == regla.id and h.regla_version == regla.version
    assert h.duracion_segundos == pytest.approx(7.8, abs=0.3)
    assert h.cuadros_evidencia  # hay recortes que mostrar al prevencionista


def test_oclusion_breve_no_parte_el_hallazgo_en_dos(regla: Regla) -> None:
    """Sin esta histéresis, un incumplimiento continuo se contaría tres veces
    y el ranking de zonas peligrosas quedaría inflado."""
    paso = 0.2
    cuadros = []
    for i in range(60):  # 12 s a 5 fps
        t = i * paso
        oculto = 5.0 <= t < 6.0  # 1 s de oclusión, menor que cierre_segundos=3
        con_casco = not (2.0 <= t < 10.0) or oculto
        cuadros.append(cuadro(t=t, idx=i, con_casco=con_casco if not oculto else True))

    hallazgos = list(agregar(regla, cuadros))
    assert len(hallazgos) == 1


def test_silencio_prolongado_cierra_el_hallazgo(regla: Regla) -> None:
    paso = 0.2
    cuadros = []
    for i in range(100):  # 20 s a 5 fps
        t = i * paso
        # sin casco 2-6 s, con casco 6-14 s (8 s > cierre), sin casco 14-19 s
        sin_casco = (2.0 <= t < 6.0) or (14.0 <= t < 19.0)
        cuadros.append(cuadro(t=t, idx=i, con_casco=not sin_casco))

    hallazgos = list(agregar(regla, cuadros))
    assert len(hallazgos) == 2


def test_dos_personas_generan_hallazgos_independientes(regla: Regla) -> None:
    otra = Caja(0.70, 0.20, 0.82, 0.80)
    cuadros = []
    for i in range(50):  # 10 s a 5 fps
        t = i * 0.2
        dets = cuadro(t=t, idx=i, con_casco=False, track_id=1)
        dets += cuadro(t=t, idx=i, con_chaleco=False, track_id=2, persona=otra)
        cuadros.append(dets)

    hallazgos = sorted(agregar(regla, cuadros), key=lambda h: h.track_id)
    assert len(hallazgos) == 2
    assert hallazgos[0].epp_faltante == {TipoEPP.CASCO}
    assert hallazgos[1].epp_faltante == {TipoEPP.CHALECO}


@pytest.mark.parametrize("fps", [2.0, 5.0, 10.0, 15.0])
def test_la_regla_en_segundos_es_invariante_a_la_cadencia(regla: Regla, fps: float) -> None:
    """El test que protege la v2.

    El mismo incumplimiento, muestreado a distinta cadencia, tiene que producir el
    mismo hallazgo. Si los umbrales estuvieran en cuadros en vez de en segundos,
    cambiar de 5 fps (archivo) a lo que dé la GPU en vivo alteraría en silencio
    todas las reglas ya validadas con el cliente. Ver ADR-005.
    """
    cuadros = secuencia(sin_casco_desde=2.0, sin_casco_hasta=8.0, total=12.0, fps=fps)
    hallazgos = list(agregar(regla, cuadros))

    assert len(hallazgos) == 1
    assert hallazgos[0].epp_faltante == {TipoEPP.CASCO}
    assert hallazgos[0].duracion_segundos == pytest.approx(6.0, abs=1.0 / fps + 0.05)


def test_umbral_de_confirmacion_se_deriva_de_los_fps(regla: Regla) -> None:
    assert regla.cuadros_de_confirmacion(fps=5.0) == 10
    assert regla.cuadros_de_confirmacion(fps=2.0) == 4
    with pytest.raises(ValueError, match="fps"):
        regla.cuadros_de_confirmacion(fps=0)


def test_cerrar_emite_lo_que_quedaba_vivo(regla: Regla) -> None:
    """Al terminar el video, un incumplimiento en curso no se pierde."""
    agregador = AgregadorDeHallazgos(regla)
    for i in range(30):  # 6 s sin casco, el video termina ahí
        agregador.procesar_cuadro(cuadro(t=i * 0.2, idx=i, con_casco=False))

    assert agregador.procesar_cuadro([]) == []
    pendientes = agregador.cerrar()
    assert len(pendientes) == 1
    assert pendientes[0].epp_faltante == {TipoEPP.CASCO}


# ── Un silencio de al menos `cierre_segundos` cierra la racha, también si reincide ───────
#
# Antes, `_acumular` sumaba el cuadro a la racha sin mirar el silencio: dos cuadros con
# incumplimiento separados por 3,0 s (= cierre_segundos) quedaban en UN hallazgo confirmado solo
# por el span (#163, caso B). Los tiempos son múltiplos de 0,25 s (diádicos): el borde es exacto.

PASO_DIADICO = 0.25  # 4 fps


def _con_incumplimientos(incumple: set[float], hasta: float) -> list[list]:
    """Un cuadro cada 0,25 s de 0 a `hasta`, con casco salvo en los instantes de `incumple`."""
    n = round(hasta / PASO_DIADICO) + 1
    return [
        cuadro(t=i * PASO_DIADICO, idx=i, con_casco=(i * PASO_DIADICO) not in incumple)
        for i in range(n)
    ]


def _tramo(desde: float, hasta: float) -> set[float]:
    n = round((hasta - desde) / PASO_DIADICO) + 1
    return {desde + i * PASO_DIADICO for i in range(n)}


def test_silencio_exacto_de_cierre_no_fusiona_dos_incumplimientos(regla: Regla) -> None:
    """t=0 y t=3,0 con EPP en medio: dos rachas de 1 cuadro, ninguna llega a 2,0 s."""
    assert regla.cierre_segundos == 3.0
    assert list(agregar(regla, _con_incumplimientos({0.0, 3.0}, hasta=3.0))) == []


def test_silencio_justo_menor_que_el_cierre_si_fusiona(regla: Regla) -> None:
    """t=0 y t=2,75: la oclusión breve se tolera, como siempre (2 cuadros, 2,75 s)."""
    (h,) = agregar(regla, _con_incumplimientos({0.0, 2.75}, hasta=2.75))
    assert (h.cuadros_confirmados, h.duracion_segundos) == (2, 2.75)


def test_silencio_mayor_que_el_cierre_no_fusiona(regla: Regla) -> None:
    assert list(agregar(regla, _con_incumplimientos({0.0, 3.25}, hasta=3.25))) == []


def test_cuadros_contiguos_son_una_sola_racha(regla: Regla) -> None:
    """Extremo bajo: cuadros contiguos (silencio de un paso) son una sola racha."""
    (h,) = agregar(regla, _con_incumplimientos(_tramo(0.0, 2.0), hasta=2.0))
    assert (h.cuadros_confirmados, h.duracion_segundos) == (9, 2.0)  # 9 cuadros, 8 pasos


def test_racha_confirmada_que_reincide_tras_el_cierre_se_emite_y_abre_otra(regla: Regla) -> None:
    """0 a 2,5 s continuo (confirmada), EPP, y vuelve a incumplir 3,0 s después del último."""
    incumple = _tramo(0.0, 2.5) | {5.5}
    (h,) = agregar(regla, _con_incumplimientos(incumple, hasta=5.5))
    assert (h.cuadros_confirmados, h.duracion_segundos) == (11, 2.5)  # solo la primera


@pytest.mark.parametrize(
    ("hasta_segunda", "hallazgos"),
    [(7.25, 1), (7.5, 2)],  # la segunda dura 1,75 s (no se confirma) o 2,0 s (justo en el umbral)
)
def test_la_segunda_racha_solo_se_confirma_al_llegar_a_la_confirmacion(
    regla: Regla, hasta_segunda: float, hallazgos: int
) -> None:
    incumple = _tramo(0.0, 2.5) | _tramo(5.5, hasta_segunda)
    hs = sorted(
        agregar(regla, _con_incumplimientos(incumple, hasta=hasta_segunda)),
        key=lambda h: h.ts_inicio,
    )
    assert len(hs) == hallazgos
    assert hs[0].duracion_segundos == 2.5
    if hallazgos == 2:
        assert (hs[1].cuadros_confirmados, hs[1].duracion_segundos) == (9, 2.0)


@pytest.mark.parametrize("semilla", range(40))
def test_ningun_hallazgo_tiene_un_hueco_de_cierre_segundos_ni_pasa_la_cota(
    regla: Regla, semilla: int
) -> None:
    """Propiedad sobre patrones al azar (reproducibles): dentro de un hallazgo, dos cuadros con
    incumplimiento consecutivos distan menos de `cierre_segundos`; y los cuadros nunca pasan de
    round(duracion_s · fps) + 1 (N cuadros abarcan N-1 pasos)."""
    azar = random.Random(semilla)
    total = 60.0
    # Ráfagas de 1 a 12 cuadros con incumplimiento separadas por 1 a 16 cuadros con EPP: los
    # huecos de exactamente 12 cuadros (3,0 s = cierre_segundos) salen seguido.
    instantes: list[float] = []
    paso = 0
    while paso * PASO_DIADICO < total:
        for _ in range(azar.randint(1, 12)):
            instantes.append(paso * PASO_DIADICO)
            paso += 1
        paso += azar.randint(1, 16)
    instantes = [t for t in instantes if t <= total]
    incumple = set(instantes)
    fps = 1 / PASO_DIADICO
    for h in agregar(regla, _con_incumplimientos(incumple, hasta=total)):
        t0 = (h.ts_inicio - en(0)).total_seconds()
        t1 = (h.ts_fin - en(0)).total_seconds()
        dentro = [t for t in instantes if t0 <= t <= t1]
        assert h.cuadros_confirmados == len(dentro)
        assert all(b - a < regla.cierre_segundos for a, b in pairwise(dentro))
        assert h.cuadros_confirmados <= round(h.duracion_segundos * fps) + 1
        assert h.duracion_segundos >= regla.confirmacion_segundos
