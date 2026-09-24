"""Cola de trabajos en Redis (PT-06), con fakeredis: sin servidor, mismas órdenes."""

from __future__ import annotations

import fakeredis
import pytest
from gepp_worker.cola import MAXIMO_INTENTOS, ColaTrabajos, EstadoTrabajo, Trabajo


def _trabajo(n: int = 1) -> Trabajo:
    return Trabajo(ruta=f"/datos/v{n}.mp4", hash_sha256=f"{n:064x}", bytes=10, fuente_id=1)


@pytest.fixture
def cola() -> ColaTrabajos:
    return ColaTrabajos(fakeredis.FakeRedis())


def test_el_mismo_hash_se_encola_una_sola_vez(cola: ColaTrabajos) -> None:
    assert cola.encolar(_trabajo()) is True
    assert cola.encolar(_trabajo()) is False
    assert cola.pendientes() == 1


def test_se_toma_en_orden_de_llegada(cola: ColaTrabajos) -> None:
    for n in (1, 2, 3):
        cola.encolar(_trabajo(n))
    tomados = [cola.tomar() for _ in range(3)]
    assert [t.ruta for t in tomados if t] == ["/datos/v1.mp4", "/datos/v2.mp4", "/datos/v3.mp4"]
    assert cola.tomar() is None


def test_el_estado_sigue_al_trabajo(cola: ColaTrabajos) -> None:
    t = _trabajo()
    assert cola.estado(t.hash_sha256) is None
    cola.encolar(t)
    assert cola.estado(t.hash_sha256) is EstadoTrabajo.PENDIENTE
    tomado = cola.tomar()
    assert tomado is not None
    assert cola.estado(t.hash_sha256) is EstadoTrabajo.PROCESANDO
    cola.confirmar(tomado)
    assert cola.estado(t.hash_sha256) is EstadoTrabajo.LISTO
    assert cola.encolar(t) is False  # un video listo no vuelve a la cola


@pytest.mark.parametrize("maximo", [1, 3])
def test_los_reintentos_terminan_en_error_al_llegar_al_maximo(maximo: int) -> None:
    cola = ColaTrabajos(fakeredis.FakeRedis(), maximo_intentos=maximo)
    cola.encolar(_trabajo())
    estados = []
    for _ in range(maximo):
        tomado = cola.tomar()
        assert tomado is not None
        estados.append(cola.reintentar(tomado, "falló"))
    assert estados == [EstadoTrabajo.PENDIENTE] * (maximo - 1) + [EstadoTrabajo.ERROR]
    assert cola.tomar() is None
    assert cola.detalle(_trabajo().hash_sha256)["intentos"] == str(maximo)
    assert cola.detalle(_trabajo().hash_sha256)["motivo"] == "falló"


def test_un_maximo_menor_que_uno_se_rechaza() -> None:
    with pytest.raises(ValueError, match="al menos 1"):
        ColaTrabajos(fakeredis.FakeRedis(), maximo_intentos=0)


def test_lo_que_quedo_procesando_vuelve_a_la_cola(cola: ColaTrabajos) -> None:
    cola.encolar(_trabajo(1))
    cola.encolar(_trabajo(2))
    cola.tomar()  # el trabajador "muere" con este en la mano
    assert cola.recuperar_huerfanos() == 1
    assert cola.estado(_trabajo(1).hash_sha256) is EstadoTrabajo.PENDIENTE
    assert cola.pendientes() == 2
    assert cola.recuperar_huerfanos() == 0


@pytest.mark.parametrize(("valor", "esperado"), [(None, MAXIMO_INTENTOS), ("5", 5)])
def test_el_maximo_de_intentos_sale_del_entorno(
    monkeypatch: pytest.MonkeyPatch, valor: str | None, esperado: int
) -> None:
    from gepp_worker.__main__ import _cola

    monkeypatch.setenv("GEPP_REDIS_URL", "redis://localhost:6379/0")  # no conecta al crearse
    if valor is None:
        monkeypatch.delenv("GEPP_MAXIMO_INTENTOS", raising=False)
    else:
        monkeypatch.setenv("GEPP_MAXIMO_INTENTOS", valor)
    assert _cola().maximo_intentos == esperado


def test_reencolar_deja_la_cuenta_en_cero_aunque_el_hash_ya_estuviera() -> None:
    cola = ColaTrabajos(fakeredis.FakeRedis())
    trabajo = Trabajo("/v/a.mp4", "a" * 64, 10, 1)
    assert cola.encolar(trabajo)
    for _ in range(MAXIMO_INTENTOS):
        cola.reintentar(cola.tomar() or trabajo, "falla")
    assert cola.estado(trabajo.hash_sha256) is EstadoTrabajo.ERROR
    assert not cola.encolar(trabajo)  # encolar respeta el hash: no vuelve solo

    cola.reencolar(trabajo)
    assert cola.estado(trabajo.hash_sha256) is EstadoTrabajo.PENDIENTE
    assert "motivo" not in cola.detalle(trabajo.hash_sha256)
    tomado = cola.tomar()
    assert tomado is not None and tomado.intentos == 0
