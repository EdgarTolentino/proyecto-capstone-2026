"""`pedido_ingesta`: un pedido abierto por archivo, incluso en concurrencia, y su ciclo de vida."""

from __future__ import annotations

import threading
import time

import pytest
from gepp_bd.modelos import ESTADOS_PEDIDO, PedidoIngesta
from gepp_bd.repositorios import pedidos
from gepp_bd.repositorios.pedidos import PedidoExistente
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


@pytest.fixture
def fuente_id(bd: Engine) -> int:
    with bd.begin() as c:
        c.execute(text("INSERT INTO faena (nombre) VALUES ('f')"))
        c.execute(text("INSERT INTO area (faena_id, nombre) VALUES (1, 'a')"))
        c.execute(
            text("INSERT INTO fuente (area_id, nombre, tipo, uri) VALUES (1,'c','carpeta','/x')")
        )
    return 1


def _crear(bd: Engine, archivo: str, fuente_id: int) -> int:
    with Session(bd) as s, s.begin():
        return pedidos.crear(s, archivo=archivo, fuente_id=fuente_id).id


def _estado(bd: Engine, pedido_id: int) -> str:
    with bd.connect() as c:
        return str(
            c.execute(
                text("SELECT estado FROM pedido_ingesta WHERE id = :i"), {"i": pedido_id}
            ).scalar_one()
        )


def _tomar(bd: Engine) -> PedidoIngesta | None:
    with Session(bd) as s, s.begin():
        pedido = pedidos.tomar_siguiente(s)
        if pedido is not None:
            s.expunge(pedido)
        return pedido


# ── Crear ──────────────────────────────────────────────────────────────────────────────────


def test_un_pedido_nuevo_queda_pendiente_con_los_tiempos_de_la_base(
    bd: Engine, fuente_id: int
) -> None:
    with Session(bd) as s, s.begin():
        p = pedidos.crear(s, archivo="a.mp4", fuente_id=fuente_id)
        assert (p.estado, p.archivo, p.fuente_id, p.usuario_id) == ("pendiente", "a.mp4", 1, None)
        assert p.motivo is None and p.video_id is None
        assert p.creado_en is not None and p.actualizado_en is not None


def test_el_mismo_archivo_abierto_dos_veces_falla(bd: Engine, fuente_id: int) -> None:
    _crear(bd, "a.mp4", fuente_id)
    with pytest.raises(PedidoExistente), Session(bd) as s, s.begin():
        pedidos.crear(s, archivo="a.mp4", fuente_id=fuente_id)


def test_un_archivo_tomado_tampoco_se_puede_pedir_de_nuevo(bd: Engine, fuente_id: int) -> None:
    _crear(bd, "a.mp4", fuente_id)
    assert _tomar(bd) is not None
    with pytest.raises(PedidoExistente), Session(bd) as s, s.begin():
        pedidos.crear(s, archivo="a.mp4", fuente_id=fuente_id)


def test_archivos_distintos_conviven(bd: Engine, fuente_id: int) -> None:
    _crear(bd, "a.mp4", fuente_id)
    _crear(bd, "b.mp4", fuente_id)
    with Session(bd) as s:
        assert len(pedidos.recientes(s)) == 2


@pytest.mark.parametrize("cierre", ["registrado", "rechazado"])
def test_un_pedido_cerrado_no_impide_pedir_el_archivo_otra_vez(
    bd: Engine, fuente_id: int, cierre: str
) -> None:
    """El índice único es PARCIAL: solo cuenta `pendiente` y `tomado`."""
    primero = _crear(bd, "a.mp4", fuente_id)
    _tomar(bd)
    with Session(bd) as s, s.begin():
        if cierre == "registrado":
            s.execute(
                text(
                    "INSERT INTO video (fuente_id, ruta, hash_sha256, bytes, capture_ts_inicio,"
                    " origen_capture_ts) VALUES (1, '/x.mp4', repeat('a', 64), 1, now(), 'manual')"
                )
            )
            assert pedidos.registrar(s, primero, 1)
        else:
            assert pedidos.rechazar(s, primero, "ya registrado")
    segundo = _crear(bd, "a.mp4", fuente_id)
    assert segundo != primero and _estado(bd, segundo) == "pendiente"
    # y varios cerrados del mismo archivo conviven
    _tomar(bd)
    with Session(bd) as s, s.begin():
        assert pedidos.rechazar(s, segundo, "otra vez")
    _crear(bd, "a.mp4", fuente_id)


def test_dos_pedidos_simultaneos_del_mismo_archivo_crean_uno_solo(
    bd: Engine, fuente_id: int
) -> None:
    """La segunda conexión espera a la primera (índice único) y al confirmar ésta, falla."""
    a, b = Session(bd), Session(bd)
    resultado: list[object] = []

    def segundo() -> None:
        try:
            pedidos.crear(b, archivo="a.mp4", fuente_id=fuente_id)
            b.commit()
            resultado.append("creado")
        except PedidoExistente as e:
            b.rollback()
            resultado.append(e)

    try:
        pedidos.crear(a, archivo="a.mp4", fuente_id=fuente_id)  # sin confirmar todavía
        hilo = threading.Thread(target=segundo)
        hilo.start()
        time.sleep(0.5)
        assert hilo.is_alive(), "la segunda debió quedar esperando a la primera"
        a.commit()
        hilo.join(timeout=10)
        assert not hilo.is_alive()
    finally:
        a.close()
        b.close()
    assert len(resultado) == 1 and isinstance(resultado[0], PedidoExistente)
    with Session(bd) as s:
        assert len(pedidos.recientes(s)) == 1


@pytest.mark.usefixtures("fuente_id")
def test_una_fuente_inexistente_viola_la_llave_foranea(bd: Engine) -> None:
    with (
        pytest.raises(IntegrityError, match="fk_pedido_ingesta_fuente_id_fuente"),
        Session(bd) as s,
        s.begin(),
    ):
        pedidos.crear(s, archivo="a.mp4", fuente_id=0)


# ── El CHECK de estados ────────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("fuente_id")
@pytest.mark.parametrize("estado", ESTADOS_PEDIDO)
def test_los_cuatro_estados_son_validos(bd: Engine, estado: str) -> None:
    with bd.begin() as c:
        c.execute(
            text("INSERT INTO pedido_ingesta (archivo, fuente_id, estado) VALUES ('a.mp4', 1, :e)"),
            {"e": estado},
        )


@pytest.mark.usefixtures("fuente_id")
@pytest.mark.parametrize("estado", ["", "Pendiente", "listo", "en_cola", "cancelado"])
def test_un_estado_invalido_lo_rechaza_la_base(bd: Engine, estado: str) -> None:
    with pytest.raises(IntegrityError, match="ck_pedido_ingesta_estado"), bd.begin() as c:
        c.execute(
            text("INSERT INTO pedido_ingesta (archivo, fuente_id, estado) VALUES ('a.mp4', 1, :e)"),
            {"e": estado},
        )


# ── Tomar ──────────────────────────────────────────────────────────────────────────────────


def test_sin_pedidos_no_hay_nada_que_tomar(bd: Engine, fuente_id: int) -> None:
    del fuente_id
    assert _tomar(bd) is None


def test_se_toma_el_mas_antiguo_y_pasa_a_tomado(bd: Engine, fuente_id: int) -> None:
    primero = _crear(bd, "a.mp4", fuente_id)
    segundo = _crear(bd, "b.mp4", fuente_id)
    tomado = _tomar(bd)
    assert tomado is not None and tomado.id == primero and tomado.estado == "tomado"
    assert _estado(bd, primero) == "tomado" and _estado(bd, segundo) == "pendiente"
    otro = _tomar(bd)
    assert otro is not None and otro.id == segundo
    assert _tomar(bd) is None  # no vuelve a entregar los ya tomados


def test_tomar_actualiza_actualizado_en_pero_no_creado_en(bd: Engine, fuente_id: int) -> None:
    pedido_id = _crear(bd, "a.mp4", fuente_id)
    with bd.connect() as c:
        antes = c.execute(
            text("SELECT creado_en, actualizado_en FROM pedido_ingesta WHERE id = :i"),
            {"i": pedido_id},
        ).one()
    time.sleep(0.05)
    _tomar(bd)
    with bd.connect() as c:
        despues = c.execute(
            text("SELECT creado_en, actualizado_en FROM pedido_ingesta WHERE id = :i"),
            {"i": pedido_id},
        ).one()
    assert despues.creado_en == antes.creado_en
    assert despues.actualizado_en > antes.actualizado_en


def test_dos_trabajadores_a_la_vez_no_toman_el_mismo_pedido(bd: Engine, fuente_id: int) -> None:
    """A reserva el primero sin confirmar; B tiene que saltarlo (SKIP LOCKED) y no esperar."""
    primero = _crear(bd, "a.mp4", fuente_id)
    segundo = _crear(bd, "b.mp4", fuente_id)
    a, b = Session(bd), Session(bd)
    try:
        b.execute(text("SET lock_timeout = '2s'"))  # si no salta, falla en vez de colgarse
        de_a = pedidos.tomar_siguiente(a)
        de_b = pedidos.tomar_siguiente(b)
        assert de_a is not None and de_b is not None
        assert {de_a.id, de_b.id} == {primero, segundo}
        assert de_a.id == primero
        # con los dos reservados, un tercero no encuentra nada
        c = Session(bd)
        try:
            assert pedidos.tomar_siguiente(c) is None
        finally:
            c.close()
        a.commit()
        b.commit()
    finally:
        a.close()
        b.close()
    assert _estado(bd, primero) == "tomado" and _estado(bd, segundo) == "tomado"


# ── Cerrar ─────────────────────────────────────────────────────────────────────────────────


def test_registrar_guarda_el_video_y_lo_medido(bd: Engine, fuente_id: int) -> None:
    pedido_id = _crear(bd, "a.mp4", fuente_id)
    _tomar(bd)
    with bd.begin() as c:
        c.execute(
            text(
                "INSERT INTO video (fuente_id, ruta, hash_sha256, bytes, capture_ts_inicio,"
                " origen_capture_ts) VALUES (1, '/x.mp4', repeat('a', 64), 1, now(), 'manual')"
            )
        )
    with Session(bd) as s, s.begin():
        assert pedidos.registrar(s, pedido_id, 1, bytes=1234, mtime_ns=99)
    with Session(bd) as s:
        p = s.get(PedidoIngesta, pedido_id)
        assert p is not None
        assert (p.estado, p.video_id, p.bytes, p.mtime_ns, p.motivo) == (
            "registrado",
            1,
            1234,
            99,
            None,
        )


def test_rechazar_guarda_el_motivo(bd: Engine, fuente_id: int) -> None:
    pedido_id = _crear(bd, "a.mp4", fuente_id)
    _tomar(bd)
    with Session(bd) as s, s.begin():
        assert pedidos.rechazar(s, pedido_id, "el archivo cambió mientras se leía")
    with Session(bd) as s:
        p = s.get(PedidoIngesta, pedido_id)
        assert p is not None and p.estado == "rechazado"
        assert p.motivo == "el archivo cambió mientras se leía" and p.video_id is None


def test_solo_se_cierra_lo_que_esta_tomado(bd: Engine, fuente_id: int) -> None:
    """Un pendiente no se cierra, y uno ya cerrado no se cierra dos veces."""
    pedido_id = _crear(bd, "a.mp4", fuente_id)
    with Session(bd) as s, s.begin():
        assert pedidos.rechazar(s, pedido_id, "x") is False
        assert pedidos.registrar(s, pedido_id, 1) is False
    assert _estado(bd, pedido_id) == "pendiente"
    _tomar(bd)
    with Session(bd) as s, s.begin():
        assert pedidos.rechazar(s, pedido_id, "primero") is True
        assert pedidos.rechazar(s, pedido_id, "segundo") is False
    with Session(bd) as s:
        p = s.get(PedidoIngesta, pedido_id)
        assert p is not None and p.motivo == "primero"


def test_cerrar_un_pedido_inexistente_devuelve_false(bd: Engine, fuente_id: int) -> None:
    del fuente_id
    with Session(bd) as s, s.begin():
        assert pedidos.rechazar(s, 999, "x") is False


@pytest.mark.parametrize("medido", [0, 1])
def test_cerrar_guarda_lo_medido_aunque_sea_cero(bd: Engine, fuente_id: int, medido: int) -> None:
    """0 es una medida, no «sin medida»: la guarda es `is not None`, no la verdad del valor."""
    pedido_id = _crear(bd, "a.mp4", fuente_id)
    _tomar(bd)
    with Session(bd) as s, s.begin():
        assert pedidos.rechazar(s, pedido_id, "x", bytes=medido, mtime_ns=medido)
    with Session(bd) as s:
        p = s.get(PedidoIngesta, pedido_id)
        assert p is not None and (p.bytes, p.mtime_ns) == (medido, medido)


def test_cerrar_sin_medidas_conserva_las_que_ya_tenia(bd: Engine, fuente_id: int) -> None:
    pedido_id = _crear(bd, "a.mp4", fuente_id)
    _tomar(bd)
    with bd.begin() as c:
        c.execute(
            text("UPDATE pedido_ingesta SET bytes = 1234, mtime_ns = 99 WHERE id = :i"),
            {"i": pedido_id},
        )
    with Session(bd) as s, s.begin():
        assert pedidos.rechazar(s, pedido_id, "x")  # sin bytes ni mtime_ns
    with Session(bd) as s:
        p = s.get(PedidoIngesta, pedido_id)
        assert p is not None and (p.bytes, p.mtime_ns) == (1234, 99)


# ── Recuperar y listar ─────────────────────────────────────────────────────────────────────


def test_al_arrancar_los_tomados_vuelven_a_pendiente(bd: Engine, fuente_id: int) -> None:
    tomado = _crear(bd, "a.mp4", fuente_id)
    _tomar(bd)
    pendiente = _crear(bd, "b.mp4", fuente_id)
    cerrado = _crear(bd, "c.mp4", fuente_id)
    _tomar(bd)  # toma b
    _tomar(bd)  # toma c
    with Session(bd) as s, s.begin():
        assert pedidos.rechazar(s, cerrado, "x")
    with Session(bd) as s, s.begin():
        assert pedidos.recuperar_tomados(s) == 2
    assert _estado(bd, tomado) == "pendiente" and _estado(bd, pendiente) == "pendiente"
    assert _estado(bd, cerrado) == "rechazado"
    with Session(bd) as s, s.begin():
        assert pedidos.recuperar_tomados(s) == 0


def test_los_recientes_van_del_mas_nuevo_al_mas_viejo_y_respetan_el_limite(
    bd: Engine, fuente_id: int
) -> None:
    ids = [_crear(bd, f"v{i}.mp4", fuente_id) for i in range(5)]
    with Session(bd) as s:
        assert [p.id for p in pedidos.recientes(s)] == ids[::-1]
        assert [p.id for p in pedidos.recientes(s, 2)] == ids[:-3:-1]
        assert pedidos.recientes(s, 0) == []


@pytest.mark.parametrize(("creados", "listados"), [(49, 49), (50, 50), (51, 50)])
def test_el_limite_por_defecto_es_50(
    bd: Engine, fuente_id: int, creados: int, listados: int
) -> None:
    assert pedidos.LIMITE_RECIENTES == 50
    with Session(bd) as s, s.begin():
        for i in range(creados):
            pedidos.crear(s, archivo=f"v{i}.mp4", fuente_id=fuente_id)
    with Session(bd) as s:
        assert len(pedidos.recientes(s)) == listados


def test_un_limite_negativo_es_un_error(bd: Engine, fuente_id: int) -> None:
    del fuente_id
    with Session(bd) as s, pytest.raises(ValueError, match="negativo"):
        pedidos.recientes(s, -1)
