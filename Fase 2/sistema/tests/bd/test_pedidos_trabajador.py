"""El trabajador atiende los pedidos de procesar un video desde la web (PR 4, ADR-009 y ADR-012).

Contra PostgreSQL y un Redis simulado (fakeredis), igual que `test_ingesta.py`; el video es de
ruido y el detector, el falso con guion. Las rutas del servidor nunca deben salir en un motivo.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fakeredis
import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Hallazgo, PedidoIngesta, Video
from gepp_bd.repositorios import pedidos, videos
from gepp_bd.semilla import cargar, leer
from gepp_vision.detectores import DetectorFalso, Guion
from gepp_worker import pedidos as modulo
from gepp_worker.cola import ColaTrabajos, EstadoTrabajo, Trabajo
from gepp_worker.pedidos import (
    CAMBIO,
    CLAVE_CANDADO,
    REEMPLAZADO,
    AtencionDePedidos,
    validar_carpeta_entrada,
)
from gepp_worker.trabajador import Configuracion, Trabajador
from gepp_worker.vigilante import sha256_de_archivo
from sqlalchemy import Engine, select, text

from .test_ingesta import GUION, MTIME, PERFIL, escribir_video_ruido

pytestmark = pytest.mark.integration

CAMARA_1, CAMARA_2 = 1, 2


class Entorno(SimpleNamespace):
    motor: Engine
    entrada: Path
    vigilada: Path
    cola: ColaTrabajos
    atencion: AtencionDePedidos
    trabajador: Trabajador
    tmp: Path


@pytest.fixture
def entorno(bd: Engine, tmp_path: Path) -> Iterator[Entorno]:
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
    entrada, vigilada = tmp_path / "pedidos", tmp_path / "vigilada"
    entrada.mkdir()
    vigilada.mkdir()
    cola = ColaTrabajos(fakeredis.FakeRedis())
    guion = Guion.desde_json(GUION)
    config = Configuracion(carpeta_evidencia=tmp_path / "evidencia", carpeta_entrada=entrada)
    trabajador = Trabajador(bd, cola, lambda: DetectorFalso(guion), config)
    atencion = AtencionDePedidos(bd, cola, entrada)
    yield Entorno(
        motor=bd,
        entrada=entrada,
        vigilada=vigilada,
        cola=cola,
        atencion=atencion,
        trabajador=trabajador,
        tmp=tmp_path,
    )
    atencion.cerrar()


def _en(nombre: str, e: Entorno) -> Path:
    """Escribe el video de ruido en la carpeta de entrada y devuelve su ruta."""
    destino = e.entrada / nombre
    escribir_video_ruido(destino)
    return destino


def _pedir(e: Entorno, archivo: str, fuente_id: int = CAMARA_2) -> int:
    with transaccion(e.motor) as s:
        return pedidos.crear(s, archivo=archivo, fuente_id=fuente_id).id


def _pedido(e: Entorno, pedido_id: int) -> PedidoIngesta:
    with transaccion(e.motor) as s:
        pedido = s.get(PedidoIngesta, pedido_id)
        assert pedido is not None
        s.expunge(pedido)
        return pedido


def _atender(e: Entorno) -> None:
    assert e.atencion.iniciar()
    assert e.atencion.atender_uno()


def _filas_video(e: Entorno) -> list[Video]:
    with transaccion(e.motor) as s:
        filas = list(s.execute(select(Video).order_by(Video.id)).scalars())
        s.expunge_all()
        return filas


# ── Pedido feliz ───────────────────────────────────────────────────────────────────────


def test_un_pedido_crea_el_video_con_la_camara_pedida_y_lo_encola(entorno: Entorno) -> None:
    e = entorno
    ruta = _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4", CAMARA_2)

    _atender(e)

    pedido = _pedido(e, pedido_id)
    (video,) = _filas_video(e)
    assert (pedido.estado, pedido.motivo, pedido.video_id) == ("registrado", None, video.id)
    assert (pedido.bytes, pedido.mtime_ns) == (ruta.stat().st_size, ruta.stat().st_mtime_ns)
    assert (video.fuente_id, video.estado, video.ruta) == (CAMARA_2, "en_cola", str(ruta))
    assert video.hash_sha256 == sha256_de_archivo(ruta)
    assert (video.origen_capture_ts, video.capture_ts_inicio) == ("mtime", MTIME)
    assert e.cola.estado(video.hash_sha256) is EstadoTrabajo.PENDIENTE


def test_el_trabajador_procesa_el_pedido_con_la_camara_pedida(entorno: Entorno) -> None:
    e = entorno
    _en("clip.mp4", e)
    _pedir(e, "clip.mp4", CAMARA_2)
    _atender(e)

    resultado = e.trabajador.atender_uno()

    assert resultado is not None and not resultado.omitido
    (video,) = _filas_video(e)
    assert (video.estado, video.fuente_id) == ("listo", CAMARA_2)
    with transaccion(e.motor) as s:
        assert {h.fuente_id for h in s.execute(select(Hallazgo)).scalars()} == {CAMARA_2}


# ── Rechazos: el motivo no lleva rutas ──────────────────────────────────────────────────


def _rechazado(e: Entorno, pedido_id: int) -> str:
    pedido = _pedido(e, pedido_id)
    assert pedido.estado == "rechazado" and pedido.video_id is None
    assert pedido.motivo and str(e.tmp) not in pedido.motivo
    assert _filas_video(e) == []
    return pedido.motivo


@pytest.mark.parametrize(
    ("archivo", "fragmento"),
    [
        ("sub/clip.mp4", "separadores"),  # la API lo habría parado; aquí se valida de nuevo
        (".oculto.mp4", "punto"),
        ("clip.txt", "extensión"),
    ],
)
def test_un_nombre_invalido_se_rechaza_al_tomarlo(
    entorno: Entorno, archivo: str, fragmento: str
) -> None:
    pedido_id = _pedir(entorno, archivo)
    _atender(entorno)
    assert fragmento in _rechazado(entorno, pedido_id)


def test_un_archivo_borrado_despues_del_pedido_se_rechaza(entorno: Entorno) -> None:
    e = entorno
    ruta = _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    ruta.unlink()
    _atender(e)
    assert "no hay un archivo" in _rechazado(e, pedido_id)


def test_un_enlace_creado_despues_del_pedido_se_rechaza(entorno: Entorno) -> None:
    e = entorno
    real = _en("real.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    (e.entrada / "clip.mp4").symlink_to(real)
    _atender(e)
    assert "no hay un archivo" in _rechazado(e, pedido_id)


class _OsConAccion:
    """El módulo `os` de `pedidos`, con una acción justo antes de abrir el archivo."""

    def __init__(self, antes_de_abrir: Any) -> None:
        self._antes = antes_de_abrir

    def open(self, ruta: Any, banderas: int, *args: Any) -> int:
        self._antes()
        return os.open(ruta, banderas, *args)

    def __getattr__(self, nombre: str) -> Any:
        return getattr(os, nombre)


def test_un_enlace_puesto_entre_la_validacion_y_la_apertura_no_se_sigue(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pasó la validación (era un archivo) y, antes de abrirlo, alguien lo cambia por un enlace
    al MISMO archivo original: el inodo coincidiría, solo `O_NOFOLLOW` lo detiene al abrir."""
    e = entorno
    ruta = _en("clip.mp4", e)
    original = e.tmp / "original.mp4"
    os.link(ruta, original)  # el mismo inodo con otro nombre: el enlace apunta al mismo archivo
    pedido_id = _pedir(e, "clip.mp4")

    def cambiar() -> None:
        ruta.unlink()
        ruta.symlink_to(original)

    monkeypatch.setattr(modulo, "os", _OsConAccion(cambiar))
    _atender(e)
    assert _rechazado(e, pedido_id) == REEMPLAZADO


def test_otro_archivo_con_el_mismo_nombre_entre_la_validacion_y_la_apertura(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otro archivo regular (otro inodo) toma el nombre: el descriptor no es el que se vio."""
    e = entorno
    ruta = _en("clip.mp4", e)
    otro = e.tmp / "otro.mp4"
    escribir_video_ruido(otro)
    pedido_id = _pedir(e, "clip.mp4")

    def reemplazar() -> None:
        os.replace(otro, ruta)

    monkeypatch.setattr(modulo, "os", _OsConAccion(reemplazar))
    _atender(e)
    assert _rechazado(e, pedido_id) == REEMPLAZADO


# ── Un archivo que cambia mientras se lee ───────────────────────────────────────────────


def _durante_el_hash(monkeypatch: pytest.MonkeyPatch, accion: Any) -> None:
    real = modulo._hash_del_descriptor

    def con_cambio(fd: int) -> str:
        digest = real(fd)
        accion()
        return digest

    monkeypatch.setattr(modulo, "_hash_del_descriptor", con_cambio)


def test_un_archivo_que_crece_durante_el_hash_se_rechaza(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = entorno
    ruta = _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    _durante_el_hash(monkeypatch, lambda: ruta.open("ab").write(b"x"))  # solo 1 byte más
    _atender(e)
    assert CAMBIO in _rechazado(e, pedido_id)
    assert _pedido(e, pedido_id).bytes == ruta.stat().st_size - 1  # lo medido al empezar


@pytest.mark.parametrize(("desfase_ns", "rechaza"), [(0, False), (1, True), (-1, True)])
def test_mismo_tamano_pero_otro_mtime_se_rechaza_desde_un_nanosegundo(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch, desfase_ns: int, rechaza: bool
) -> None:
    e = entorno
    ruta = _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    inicial = ruta.stat().st_mtime_ns
    _durante_el_hash(
        monkeypatch, lambda: os.utime(ruta, ns=(inicial + desfase_ns, inicial + desfase_ns))
    )
    _atender(e)
    if rechaza:
        assert CAMBIO in _rechazado(e, pedido_id)
    else:
        assert _pedido(e, pedido_id).estado == "registrado"


def test_el_archivo_reemplazado_por_otro_con_igual_tamano_y_fecha_durante_el_hash(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tamaño y mtime iguales, pero es otro archivo (otro inodo): el hash no es el del nombre."""
    e = entorno
    ruta = _en("clip.mp4", e)
    copia = e.tmp / "copia.mp4"
    shutil.copy2(ruta, copia)  # mismo contenido, tamaño y mtime; otro inodo
    pedido_id = _pedir(e, "clip.mp4")
    _durante_el_hash(monkeypatch, lambda: os.replace(copia, ruta))
    _atender(e)
    assert CAMBIO in _rechazado(e, pedido_id)


def test_el_archivo_que_desaparece_durante_el_hash_se_rechaza(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = entorno
    ruta = _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    _durante_el_hash(monkeypatch, ruta.unlink)
    _atender(e)
    assert CAMBIO in _rechazado(e, pedido_id)


# ── El hash ya está registrado ──────────────────────────────────────────────────────────


def test_un_hash_ya_registrado_con_otra_camara_se_rechaza_sin_tocar_la_fila(
    entorno: Entorno,
) -> None:
    e = entorno
    ruta = _en("clip.mp4", e)
    with transaccion(e.motor) as s:
        videos.registrar(
            s,
            videos.NuevoVideo(
                fuente_id=CAMARA_1,
                ruta="/otra/parte/viejo.mp4",
                hash_sha256=sha256_de_archivo(ruta),
                bytes=1,
                capture_ts_inicio=MTIME,
                origen_capture_ts="mtime",
            ),
        )
    antes = _filas_video(e)
    pedido_id = _pedir(e, "clip.mp4", CAMARA_2)

    _atender(e)

    pedido = _pedido(e, pedido_id)
    assert (pedido.estado, pedido.video_id) == ("rechazado", None)
    assert pedido.motivo == "ya registrado como cámara Cámara 01 · acceso"
    (despues,) = _filas_video(e)
    assert (despues.fuente_id, despues.ruta, despues.estado) == (
        antes[0].fuente_id,
        antes[0].ruta,
        antes[0].estado,
    )
    assert e.cola.estado(despues.hash_sha256) is None  # no se encoló nada


def _fila_de_un_pedido_caido(e: Entorno, ruta: Path, fuente_id: int, estado: str) -> None:
    with transaccion(e.motor) as s:
        video, _ = videos.registrar(
            s,
            videos.NuevoVideo(
                fuente_id=fuente_id,
                ruta=str(ruta),
                hash_sha256=sha256_de_archivo(ruta),
                bytes=ruta.stat().st_size,
                capture_ts_inicio=MTIME,
                origen_capture_ts="mtime",
            ),
        )
        videos.cambiar_estado(s, video.id, estado)


def test_un_pedido_caido_a_medias_reconoce_su_propia_fila(entorno: Entorno) -> None:
    """Murió entre crear el `video` y cerrar el pedido: al volver, la fila es suya."""
    e = entorno
    ruta = _en("clip.mp4", e)
    _fila_de_un_pedido_caido(e, ruta, CAMARA_2, "en_cola")
    pedido_id = _pedir(e, "clip.mp4", CAMARA_2)

    _atender(e)

    (video,) = _filas_video(e)
    assert _pedido(e, pedido_id).video_id == video.id
    assert _pedido(e, pedido_id).estado == "registrado"


@pytest.mark.parametrize(
    ("fuente_id", "estado"),
    [(CAMARA_1, "en_cola"), (CAMARA_2, "listo"), (CAMARA_2, "procesando")],
)
def test_la_fila_ajena_no_se_toma_por_propia(entorno: Entorno, fuente_id: int, estado: str) -> None:
    """Otra cámara, o ya procesada: es un contenido ya registrado, no el mismo pedido."""
    e = entorno
    ruta = _en("clip.mp4", e)
    _fila_de_un_pedido_caido(e, ruta, fuente_id, estado)
    pedido_id = _pedir(e, "clip.mp4", CAMARA_2)
    _atender(e)
    assert "ya registrado como cámara" in _rechazado_con_fila(e, pedido_id)


def _rechazado_con_fila(e: Entorno, pedido_id: int) -> str:
    pedido = _pedido(e, pedido_id)
    assert pedido.estado == "rechazado" and pedido.video_id is None
    assert pedido.motivo and str(e.tmp) not in pedido.motivo
    return pedido.motivo


# ── Recuperación y candado ──────────────────────────────────────────────────────────────


def test_al_arrancar_lo_que_quedo_tomado_vuelve_a_pendiente_y_se_atiende(entorno: Entorno) -> None:
    e = entorno
    _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    with transaccion(e.motor) as s:
        assert pedidos.tomar_siguiente(s) is not None  # un trabajador anterior murió aquí
    assert _pedido(e, pedido_id).estado == "tomado"

    assert e.atencion.iniciar()
    assert _pedido(e, pedido_id).estado == "pendiente"
    assert e.atencion.atender_uno()
    assert _pedido(e, pedido_id).estado == "registrado"


def test_sin_pedidos_no_hay_nada_que_atender(entorno: Entorno) -> None:
    assert entorno.atencion.iniciar()
    assert not entorno.atencion.atender_uno()


def _tomar_el_candado(motor: Engine) -> Any:
    conexion = motor.connect()
    assert conexion.execute(
        text("SELECT pg_try_advisory_lock(:k)"), {"k": CLAVE_CANDADO}
    ).scalar_one()
    conexion.commit()
    return conexion


def _soltar_el_candado(conexion: Any) -> None:
    """`close()` devuelve la conexión al pool y el candado sigue en ella: hay que soltarlo."""
    conexion.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": CLAVE_CANDADO})
    conexion.commit()
    conexion.close()


def test_con_el_candado_tomado_por_otro_no_se_atienden_pedidos(
    entorno: Entorno, capsys: pytest.CaptureFixture[str]
) -> None:
    e = entorno
    _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    ajeno = _tomar_el_candado(e.motor)
    try:
        assert not e.atencion.iniciar()  # no lanza, no muere
        assert not e.atencion.activa
        assert not e.trabajador.atender_pedido()
        assert "otro proceso atiende los pedidos" in capsys.readouterr().out
        assert _pedido(e, pedido_id).estado == "pendiente"
    finally:
        _soltar_el_candado(ajeno)

    assert e.atencion.iniciar()  # ya libre
    assert e.atencion.atender_uno()
    assert _pedido(e, pedido_id).estado == "registrado"


def test_el_candado_se_suelta_al_cerrar(entorno: Entorno) -> None:
    e = entorno
    otra = AtencionDePedidos(e.motor, e.cola, e.entrada)
    try:
        assert e.atencion.iniciar()
        assert not otra.iniciar()
        e.atencion.cerrar()
        assert otra.iniciar()
    finally:
        otra.cerrar()


def test_un_trabajador_sin_candado_no_recupera_los_tomados_del_otro(entorno: Entorno) -> None:
    e = entorno
    _pedir(e, "clip.mp4")
    with transaccion(e.motor) as s:
        pedidos.tomar_siguiente(s)  # lo tiene el trabajador que sí atiende
    ajeno = _tomar_el_candado(e.motor)
    try:
        assert not e.atencion.iniciar()
    finally:
        _soltar_el_candado(ajeno)
    with transaccion(e.motor) as s:
        assert s.execute(select(PedidoIngesta.estado)).scalar_one() == "tomado"


# ── El bucle del trabajador ─────────────────────────────────────────────────────────────


def _vueltas(n: int) -> Any:
    restantes = iter([True] * n)
    return lambda: next(restantes, False)


def test_el_bucle_atiende_el_pedido_y_procesa_el_video(entorno: Entorno) -> None:
    e = entorno
    _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4", CAMARA_2)

    e.trabajador.correr(seguir=_vueltas(1), espera_s=0)

    (video,) = _filas_video(e)
    assert (video.estado, video.fuente_id) == ("listo", CAMARA_2)
    assert _pedido(e, pedido_id).estado == "registrado"


def test_al_terminar_el_bucle_suelta_el_candado(entorno: Entorno) -> None:
    e = entorno
    e.trabajador.correr(seguir=_vueltas(1), espera_s=0)
    assert e.atencion.iniciar()  # si el trabajador no lo soltara, esto daría False


def test_sin_carpeta_de_entrada_el_trabajador_no_atiende_pedidos(
    entorno: Entorno, capsys: pytest.CaptureFixture[str]
) -> None:
    e = entorno
    _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    guion = Guion.desde_json(GUION)
    sin_entrada = Trabajador(
        e.motor,
        e.cola,
        lambda: DetectorFalso(guion),
        Configuracion(carpeta_evidencia=e.tmp / "evidencia"),
    )

    sin_entrada.correr(seguir=_vueltas(1), espera_s=0)

    assert "sin GEPP_CARPETA_ENTRADA" in capsys.readouterr().out
    assert _pedido(e, pedido_id).estado == "pendiente"
    assert not sin_entrada.atender_pedido()


# ── La base manda sobre Redis ───────────────────────────────────────────────────────────


def test_si_redis_falla_al_encolar_el_pedido_igual_queda_registrado(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = entorno
    _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")

    def caido(_trabajo: Trabajo) -> bool:
        raise ConnectionError("redis caído")

    monkeypatch.setattr(e.cola, "encolar", caido)
    _atender(e)

    assert _pedido(e, pedido_id).estado == "registrado"
    (video,) = _filas_video(e)
    assert video.estado == "en_cola"
    monkeypatch.undo()
    assert e.trabajador.reencolar_pedidos() == 1  # la base lo recupera
    assert e.cola.estado(video.hash_sha256) is EstadoTrabajo.PENDIENTE


def test_una_falla_inesperada_rechaza_el_pedido_con_el_motivo_sin_rutas(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = entorno
    ruta = _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")

    def falla(_ruta: Path) -> Any:
        raise RuntimeError(f"se rompió leyendo {ruta}")

    monkeypatch.setattr(e.atencion, "_hash_estable", falla)
    _atender(e)

    assert _rechazado(e, pedido_id) == "RuntimeError: se rompió leyendo clip.mp4"


def test_h4_procesar_usa_la_ruta_y_la_camara_de_la_fila_no_las_del_trabajo(
    entorno: Entorno,
) -> None:
    """Redis tenía el hash por el vigilante (cámara 1, otra ruta); la fila dice cámara 2."""
    e = entorno
    ruta = _en("clip.mp4", e)
    por_el_vigilante = Trabajo(
        str(e.vigilada / "no_existe.mp4"), sha256_de_archivo(ruta), ruta.stat().st_size, CAMARA_1
    )
    assert e.cola.encolar(por_el_vigilante)
    pedido_id = _pedir(e, "clip.mp4", CAMARA_2)
    _atender(e)  # `encolar` ya no encola: el hash estaba
    assert _pedido(e, pedido_id).estado == "registrado"

    resultado = e.trabajador.atender_uno()

    assert resultado is not None and not resultado.omitido  # abrió la ruta de la fila
    (video,) = _filas_video(e)
    assert (video.estado, video.fuente_id) == ("listo", CAMARA_2)
    with transaccion(e.motor) as s:
        assert {h.fuente_id for h in s.execute(select(Hallazgo)).scalars()} == {CAMARA_2}
    assert e.cola.estado(video.hash_sha256) is EstadoTrabajo.LISTO


def test_un_fallo_con_la_ruta_de_la_fila_no_la_deja_en_el_motivo(entorno: Entorno) -> None:
    """La ruta de la fila (con espacio) difiere de la del trabajo: ambas se sanean."""
    e = entorno
    carpeta = e.entrada / "mis videos"
    carpeta.mkdir()
    ruta = carpeta / "clip uno.mp4"
    ruta.write_bytes(b"esto no es un video" * 100)
    otra_ruta = str(e.vigilada / "otro.mp4")
    por_el_vigilante = Trabajo(otra_ruta, sha256_de_archivo(ruta), 1900, CAMARA_1)
    _fila_de_un_pedido_caido(e, ruta, CAMARA_2, "en_cola")
    assert e.cola.encolar(por_el_vigilante)

    assert e.trabajador.atender_uno() is None

    (video,) = _filas_video(e)
    assert video.estado == "reintentando"
    assert "clip uno.mp4" in (video.error_motivo or "")
    assert "mis videos" not in (video.error_motivo or "")


# ── Configuración ───────────────────────────────────────────────────────────────────────


def test_la_carpeta_de_entrada_valida(tmp_path: Path) -> None:
    entrada, vigilada = tmp_path / "pedidos", tmp_path / "vigilada"
    entrada.mkdir()
    vigilada.mkdir()
    assert validar_carpeta_entrada(entrada, vigilada) == entrada.resolve()


def test_nombres_parecidos_no_se_toman_por_anidados(tmp_path: Path) -> None:
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos2").mkdir()
    assert validar_carpeta_entrada(tmp_path / "videos2", tmp_path / "videos")


@pytest.mark.parametrize("caso", ["igual", "entrada_dentro", "vigilada_dentro", "enlace"])
def test_la_entrada_no_puede_coincidir_ni_anidarse_con_la_vigilada(
    tmp_path: Path, caso: str
) -> None:
    vigilada = tmp_path / "vigilada"
    vigilada.mkdir()
    entrada = {
        "igual": vigilada,
        "entrada_dentro": vigilada / "pedidos",
        "vigilada_dentro": tmp_path,
        "enlace": tmp_path / "atajo",
    }[caso]
    if caso == "entrada_dentro":
        entrada.mkdir()
    if caso == "enlace":
        entrada.symlink_to(vigilada)  # resuelta, es la misma carpeta
    with pytest.raises(ValueError, match="GEPP_CARPETA_VIGILADA"):
        validar_carpeta_entrada(entrada, vigilada)


def test_la_entrada_bajo_mnt_se_rechaza(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bajo /mnt/ rechazada"):
        validar_carpeta_entrada("/mnt/c/videos", tmp_path)


def test_la_entrada_inexistente_o_que_es_un_archivo_se_rechaza(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no es una carpeta"):
        validar_carpeta_entrada(tmp_path / "no_existe", tmp_path / "otra")
    archivo = tmp_path / "archivo.txt"
    archivo.write_text("x")
    with pytest.raises(ValueError, match="no es una carpeta"):
        validar_carpeta_entrada(archivo, tmp_path / "otra")


# ── Correcciones de la revisión de Codex ────────────────────────────────────────────────


class _RedisQueFallaEnLpush(fakeredis.FakeRedis):
    """Falla el LPUSH tantas veces como se le diga; lo demás es Redis."""

    fallos = 0

    def lpush(self, *args: Any, **kwargs: Any) -> Any:
        if self.fallos > 0:
            self.fallos -= 1
            raise ConnectionError("redis cayó entre el estado y la lista")
        return super().lpush(*args, **kwargs)


def test_p1_si_el_lpush_falla_el_hash_no_queda_pendiente_sin_estar_en_la_lista(
    entorno: Entorno,
) -> None:
    e = entorno
    ruta = _en("clip.mp4", e)
    redis = _RedisQueFallaEnLpush()
    redis.fallos = 1
    cola = ColaTrabajos(redis)
    atencion = AtencionDePedidos(e.motor, cola, e.entrada)
    trabajador = Trabajador(
        e.motor,
        cola,
        e.trabajador._fabrica_detector,
        Configuracion(carpeta_evidencia=e.tmp / "evidencia", carpeta_entrada=e.entrada),
    )
    hash_ = sha256_de_archivo(ruta)
    pedido_id = _pedir(e, "clip.mp4")

    try:
        assert atencion.iniciar()
        assert atencion.atender_uno()
    finally:
        atencion.cerrar()

    assert _pedido(e, pedido_id).estado == "registrado"
    assert cola.estado(hash_) is None and cola.pendientes() == 0  # sin estado huérfano
    assert trabajador.reencolar_pedidos() == 1  # la base lo recupera
    assert cola.estado(hash_) is EstadoTrabajo.PENDIENTE and cola.pendientes() == 1


def test_p1_encolar_con_exito_deja_estado_y_lista_juntos() -> None:
    cola = ColaTrabajos(fakeredis.FakeRedis())
    assert cola.encolar(Trabajo("/x/a.mp4", "h" * 64, 10, 1))
    assert cola.estado("h" * 64) is EstadoTrabajo.PENDIENTE and cola.pendientes() == 1
    assert not cola.encolar(Trabajo("/x/a.mp4", "h" * 64, 10, 1))  # el segundo no duplica
    assert cola.pendientes() == 1


def _cae_una_vez(real: Any) -> Any:
    fallos = [1]

    def envuelta(*args: Any, **kwargs: Any) -> Any:
        if fallos[0]:
            fallos[0] -= 1
            raise ConnectionError("la base cayó")
        return real(*args, **kwargs)

    return envuelta


def test_p2_si_falla_el_cierre_el_pedido_se_cierra_en_la_vuelta_siguiente(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = entorno
    _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    monkeypatch.setattr(pedidos, "registrar", _cae_una_vez(pedidos.registrar))
    assert e.atencion.iniciar()
    assert e.atencion.atender_uno()  # no lanza
    assert _pedido(e, pedido_id).estado == "tomado"  # el cierre cayó...
    assert e.atencion.atender_uno() is False  # ...no hay otro pedido, pero reintenta el cierre
    (video,) = _filas_video(e)
    cerrado = _pedido(e, pedido_id)
    assert (cerrado.estado, cerrado.video_id) == ("registrado", video.id)


def test_p2_si_falla_el_cierre_de_un_rechazo_tambien_se_reintenta(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = entorno
    pedido_id = _pedir(e, "clip.txt")
    monkeypatch.setattr(pedidos, "rechazar", _cae_una_vez(pedidos.rechazar))
    assert e.atencion.iniciar()
    assert e.atencion.atender_uno()
    assert _pedido(e, pedido_id).estado == "tomado"
    e.atencion.atender_uno()
    assert _pedido(e, pedido_id).estado == "rechazado"


def test_p3_si_falla_el_inicio_se_reintenta_en_las_vueltas_siguientes(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = entorno
    _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    # Postgres no responde al pedir la conexión del candado: `_conexion` nunca llega a existir.
    monkeypatch.setattr(e.motor, "connect", _cae_una_vez(e.motor.connect))

    e.trabajador.correr(seguir=_vueltas(2), espera_s=0)

    assert _pedido(e, pedido_id).estado == "registrado"


def test_p3_un_inicio_fallido_no_deja_el_candado_tomado(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = entorno
    monkeypatch.setattr(pedidos, "recuperar_tomados", _cae_una_vez(pedidos.recuperar_tomados))
    with pytest.raises(ConnectionError):
        e.atencion.iniciar()
    assert not e.atencion.activa
    otra = AtencionDePedidos(e.motor, e.cola, e.entrada)
    try:
        assert otra.iniciar()  # el candado quedó libre
    finally:
        otra.cerrar()


def test_p4_una_fifo_puesta_entre_la_validacion_y_la_apertura_no_bloquea(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    e = entorno
    ruta = _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")

    def cambiar() -> None:
        ruta.unlink()
        os.mkfifo(ruta)

    monkeypatch.setattr(modulo, "os", _OsConAccion(cambiar))
    hilo = threading.Thread(target=lambda: _atender(e), daemon=True)
    hilo.start()
    hilo.join(timeout=5)
    bloqueado = hilo.is_alive()
    if bloqueado:  # soltar el open bloqueado para no dejar el hilo colgado
        fd = os.open(ruta, os.O_WRONLY)
        os.close(fd)
        hilo.join(timeout=5)
    assert not bloqueado, "abrir una FIFO bloqueó al trabajador"
    assert _rechazado(e, pedido_id) == REEMPLAZADO


def test_p5_un_archivo_truncado_a_cero_despues_de_validar_se_rechaza(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = entorno
    ruta = _en("clip.mp4", e)
    pedido_id = _pedir(e, "clip.mp4")
    monkeypatch.setattr(modulo, "os", _OsConAccion(lambda: os.truncate(ruta, 0)))
    _atender(e)
    assert "vacío" in _rechazado(e, pedido_id)


def test_p5_un_archivo_de_un_byte_si_se_registra(entorno: Entorno) -> None:
    """El extremo válido del umbral: 1 byte pasa el chequeo de tamaño."""
    e = entorno
    (e.entrada / "uno.mp4").write_bytes(b"x")
    pedido_id = _pedir(e, "uno.mp4")
    _atender(e)
    assert _pedido(e, pedido_id).estado == "registrado"


def test_p6_un_segundo_pedido_del_mismo_archivo_y_camara_se_rechaza(entorno: Entorno) -> None:
    e = entorno
    _en("clip.mp4", e)
    primero = _pedir(e, "clip.mp4", CAMARA_2)
    _atender(e)
    assert _pedido(e, primero).estado == "registrado"
    segundo = _pedir(e, "clip.mp4", CAMARA_2)  # el primero ya cerró: se puede volver a pedir

    assert e.atencion.atender_uno()

    assert "ya registrado como cámara" in _rechazado_con_fila(e, segundo)
    (video,) = _filas_video(e)
    assert _pedido(e, primero).video_id == video.id  # la fila sigue siendo del primero
