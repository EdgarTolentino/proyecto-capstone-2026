"""La pieza que convierte 18.000 cuadros en una docena de hallazgos (ADR-004)."""

from __future__ import annotations

import pytest
from gepp_core import AgregadorDeHallazgos, Caja, Regla, Severidad, TipoEPP, agregar

from .conftest import cuadro


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
