"""El muestreador y los cuadros que salta: sin observador no se decodifican, con él sí."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest
from gepp_worker.fuente import Cuadro, PropiedadesFuente
from gepp_worker.muestreo import Muestreador, pasa

from .conftest import T0

FPS_ORIGEN = 30.0
TOTAL = 30


class FuenteContada:
    """Una fuente de TOTAL cuadros que cuenta cuántas veces se decodifica."""

    def __init__(self) -> None:
        self.indice = -1
        self.decodificados: list[int] = []

    def abrir(self) -> None:
        self.indice = -1

    def tomar(self) -> bool:
        self.indice += 1
        return self.indice < TOTAL

    def recuperar(self) -> Cuadro | None:
        self.decodificados.append(self.indice)
        return Cuadro(
            self.indice,
            T0 + timedelta(seconds=self.indice / FPS_ORIGEN),
            np.zeros((2, 2, 3), np.uint8),
        )

    def cerrar(self) -> None: ...

    def propiedades(self) -> PropiedadesFuente:
        return PropiedadesFuente(True, FPS_ORIGEN, 2, 2, TOTAL, T0, "mtime", False)


class Observador:
    def __init__(self, quiere: set[int] | None = None) -> None:
        self._quiere = quiere
        self.recibidos: list[int] = []
        self.eventos: list[tuple[str, int]] = []

    def quiere(self, indice: int) -> bool:
        return self._quiere is None or indice in self._quiere

    def al_saltar(self, cuadro: Cuadro) -> None:
        self.recibidos.append(cuadro.indice)
        self.eventos.append(("saltado", cuadro.indice))


def recorrer(muestreador: Muestreador, observador: Observador | None = None) -> list[int]:
    muestreador.abrir()
    analizados = []
    while muestreador.tomar():
        c = muestreador.recuperar()
        assert c is not None
        analizados.append(c.indice)
        if observador is not None:
            observador.eventos.append(("analizado", c.indice))
    return analizados


MUESTREADOS = [i for i in range(TOTAL) if pasa(i, FPS_ORIGEN, 5.0)]


def test_sin_observador_solo_se_decodifican_los_muestreados() -> None:
    fuente = FuenteContada()
    analizados = recorrer(Muestreador(fuente, 5.0))
    assert analizados == MUESTREADOS and len(MUESTREADOS) == 5
    assert fuente.decodificados == MUESTREADOS  # ni un cuadro más: eso era el costo a evitar


def test_con_observador_se_decodifica_cada_cuadro_una_vez_y_se_entrega_el_saltado() -> None:
    fuente, obs = FuenteContada(), Observador()
    analizados = recorrer(Muestreador(fuente, 5.0, saltados=obs), obs)
    assert analizados == MUESTREADOS  # el análisis no cambia
    assert obs.recibidos == [i for i in range(TOTAL) if i not in MUESTREADOS]
    assert sorted(fuente.decodificados) == list(range(TOTAL))  # todos, una vez


def test_los_cuadros_llegan_en_orden_de_video_y_tambien_los_de_la_cola() -> None:
    fuente, obs = FuenteContada(), Observador()
    recorrer(Muestreador(fuente, 5.0, saltados=obs), obs)
    orden = [i for _, i in obs.eventos]
    assert orden == list(range(TOTAL))  # incluidos los 24..29 después del último muestreado
    assert MUESTREADOS[-1] < TOTAL - 1


def test_el_observador_decide_cuales_se_decodifican() -> None:
    fuente, obs = FuenteContada(), Observador(quiere={1, 2, 7})
    recorrer(Muestreador(fuente, 5.0, saltados=obs), obs)
    assert obs.recibidos == [1, 2, 7]
    assert sorted(fuente.decodificados) == sorted([*MUESTREADOS, 1, 2, 7])


def test_un_observador_que_no_quiere_nada_equivale_a_no_tener_observador() -> None:
    fuente = FuenteContada()
    recorrer(Muestreador(fuente, 5.0, saltados=Observador(quiere=set())))
    assert fuente.decodificados == MUESTREADOS


@pytest.mark.parametrize("fps_objetivo", [5.0, 10.0, 30.0])
def test_el_analisis_es_el_mismo_con_y_sin_observador(fps_objetivo: float) -> None:
    sin = recorrer(Muestreador(FuenteContada(), fps_objetivo))
    con = recorrer(Muestreador(FuenteContada(), fps_objetivo, saltados=Observador()))
    assert sin == con
