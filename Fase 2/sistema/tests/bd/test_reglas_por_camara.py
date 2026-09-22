"""Las reglas tal como se aplican en cada cámara: zona, horario y EPP evaluable (PT-12)."""

from __future__ import annotations

from datetime import time
from pathlib import Path

import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Fuente, Zona
from gepp_bd.modelos import Regla as FilaRegla
from gepp_bd.repositorios import reglas
from gepp_bd.semilla import cargar, leer
from gepp_core import TipoEPP
from sqlalchemy import Engine, update

pytestmark = pytest.mark.integration

PERFIL = Path(__file__).resolve().parents[2] / "perfiles" / "construccion.yaml"
CASCO, CHALECO = TipoEPP.CASCO, TipoEPP.CHALECO


@pytest.fixture
def sembrada(bd: Engine) -> Engine:
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
    return bd


def _en_camara_1(motor: Engine, evaluable: list[str] | None, **regla: object):  # type: ignore[no-untyped-def]
    with transaccion(motor) as s:
        s.execute(update(Zona).where(Zona.fuente_id == 1).values(evaluable=evaluable))
        if regla:
            s.execute(update(FilaRegla).where(FilaRegla.id == 1).values(**regla))
        s.flush()
        s.expire_all()
        fila, fuente = s.get(FilaRegla, 1), s.get(Fuente, 1)
        assert fila is not None and fuente is not None
        return reglas.en_fuente(s, fila, fuente)


@pytest.mark.parametrize(
    ("evaluable", "exigido"),
    [
        (None, {CASCO, CHALECO}),  # sin medir: no restringe
        (["casco", "chaleco", "arnes"], {CASCO, CHALECO}),
        (["casco"], {CASCO}),  # el chaleco no se resuelve en esta cámara: no se exige
    ],
)
def test_solo_se_exige_lo_evaluable(sembrada: Engine, evaluable, exigido) -> None:  # type: ignore[no-untyped-def]
    r = _en_camara_1(sembrada, evaluable)
    assert r is not None and r.epp_exigido == frozenset(exigido)


@pytest.mark.parametrize("evaluable", [[], ["arnes"]])
def test_si_nada_es_evaluable_la_regla_no_se_aplica(sembrada: Engine, evaluable) -> None:  # type: ignore[no-untyped-def]
    """El motor nunca exige lo que la cámara no ve (#35)."""
    assert _en_camara_1(sembrada, evaluable) is None


def test_la_zona_de_interes_de_la_camara_pasa_a_la_regla(sembrada: Engine) -> None:
    r = _en_camara_1(sembrada, None)
    assert r is not None and r.zona == ((0, 0), (1, 0), (1, 1), (0, 1))


def test_una_regla_con_zona_de_otra_camara_no_se_aplica_aqui(sembrada: Engine) -> None:
    # La zona 2 es de la cámara 02.
    assert _en_camara_1(sembrada, None, zona_id=2) is None


def test_el_turno_se_vuelve_ventana_en_hora_de_la_faena(sembrada: Engine) -> None:
    r = _en_camara_1(sembrada, None, turno="B")
    assert r is not None and r.ventana is not None
    assert (r.ventana.desde, r.ventana.hasta, r.ventana.zona_horaria) == (
        time(20),
        time(8),
        "America/Santiago",
    )


def test_el_horario_explicito_manda_sobre_el_turno(sembrada: Engine) -> None:
    r = _en_camara_1(sembrada, None, turno="B", hora_desde=time(9), hora_hasta=time(10))
    assert r is not None and r.ventana is not None
    assert (r.ventana.desde, r.ventana.hasta) == (time(9), time(10))


def test_un_turno_inexistente_es_un_error_visible(sembrada: Engine) -> None:
    with pytest.raises(ValueError, match="turno 'Z'"):
        _en_camara_1(sembrada, None, turno="Z")
