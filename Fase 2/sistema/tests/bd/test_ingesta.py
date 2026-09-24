"""Ingesta de punta a punta (PT-06): carpeta vigilada -> cola -> trabajador -> PostgreSQL.

Recorrido real salvo el modelo: el detector es el falso con un guion de "persona sin casco
durante 3 s". Video de ruido, sin personas reales, para poder medir el pixelado.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import fakeredis
import numpy as np
import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Deteccion, Evidencia, Hallazgo, Notificacion, Video
from gepp_bd.modelos import Regla as FilaRegla
from gepp_bd.repositorios import evidencias, videos
from gepp_bd.semilla import cargar, leer
from gepp_vision.detectores import DetectorFalso, Guion
from gepp_worker import trabajador as modulo_trabajador
from gepp_worker.cola import MAXIMO_INTENTOS, ColaTrabajos, EstadoTrabajo
from gepp_worker.trabajador import Aviso, Configuracion, Trabajador
from gepp_worker.vigilante import Vigilante
from sqlalchemy import Engine, func, select, update

from ..test_evidencia import rugosidad

pytestmark = pytest.mark.integration

RAIZ = Path(__file__).resolve().parents[2]
PERFIL = RAIZ / "perfiles" / "construccion.yaml"
GUION = RAIZ / "tests" / "fixtures" / "guion_sin_casco.json"
#: Fecha de modificación fija del video: el reloj sale de `mtime - duración`, así que la
#: captura queda en esta fecha y no en la de hoy.
MTIME = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
ANCHO, ALTO, FPS, SEGUNDOS = 320, 240, 10, 5


def escribir_video_ruido(ruta: Path) -> Path:
    escritor = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (ANCHO, ALTO))
    rng = np.random.default_rng(3)
    for _ in range(FPS * SEGUNDOS):
        escritor.write(rng.integers(0, 256, (ALTO, ANCHO, 3), dtype=np.uint8))
    escritor.release()
    marca = MTIME.timestamp()
    os.utime(ruta, (marca, marca))
    return ruta


def contar(motor: Engine, modelo: type) -> int:
    with transaccion(motor) as s:
        return int(s.scalar(select(func.count()).select_from(modelo)) or 0)


@pytest.fixture
def entorno(bd: Engine, tmp_path: Path):  # type: ignore[no-untyped-def]
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    cola = ColaTrabajos(fakeredis.FakeRedis())
    guion = Guion.desde_json(GUION)
    trabajador = Trabajador(
        bd,
        cola,
        lambda: DetectorFalso(guion),
        Configuracion(
            carpeta_evidencia=tmp_path / "evidencia",
            aviso=Aviso(canal="telegram", destinatario="canal-de-prueba"),
        ),
    )
    return bd, entrada, cola, Vigilante(entrada, cola, fuente_id=1), trabajador, tmp_path


def test_un_video_copiado_termina_como_filas_en_la_base(entorno) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, cola, vigilante, trabajador, tmp = entorno

    # 1. A medio copiar: `.part`, no se lee.
    shutil.move(escribir_video_ruido(tmp / "clip.mp4"), entrada / "clip.mp4.part")
    assert vigilante.sondear() == [] and vigilante.sondear() == []

    # 2. Termina la copia: al segundo sondeo igual se encola.
    (entrada / "clip.mp4.part").rename(entrada / "clip.mp4")
    assert vigilante.sondear() == []
    (trabajo,) = vigilante.sondear()

    resultado = trabajador.atender_uno()
    assert resultado is not None and not resultado.omitido
    assert resultado.hallazgos == 1
    assert cola.estado(trabajo.hash_sha256) is EstadoTrabajo.LISTO

    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
        (hallazgo,) = s.execute(select(Hallazgo)).scalars()
        (ev,) = s.execute(select(Evidencia)).scalars()
        (aviso,) = s.execute(select(Notificacion)).scalars()
        n_det = s.scalar(select(func.count()).select_from(Deteccion))

    assert (video.estado, video.origen_capture_ts) == ("listo", "mtime")
    assert video.cuadros_analizados == SEGUNDOS * 5  # muestreado a 5 fps
    assert video.proceso_ms is not None and video.proceso_ms >= 0
    assert video.capture_ts_inicio == MTIME - timedelta(seconds=SEGUNDOS)
    assert n_det == resultado.detecciones > 0
    assert hallazgo.epp_faltante == ["casco"]
    assert hallazgo.video_id == video.id
    assert aviso.hallazgo_id == hallazgo.id and aviso.estado == "pendiente"
    assert ev.hallazgo_id == hallazgo.id and ev.anonimizado

    # Evidencia: existe, su hash coincide, se purga desde la captura y la cabeza va pixelada.
    ruta = Path(ev.ruta)
    datos = ruta.read_bytes()
    assert hashlib.sha256(datos).hexdigest() == ev.hash_sha256
    assert ev.purgar_el == ev.capture_ts.date() + timedelta(days=30)
    assert ev.capture_ts.date() == MTIME.date()
    assert [p.name for p in ruta.parent.iterdir()] == [ruta.name]
    recorte = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_COLOR)
    # Persona del guion: x 0,40-0,52, y 0,20-0,80. Margen 25 %: en el recorte la persona va
    # de y 36 a 180 (alto 144) y de x 10 a 48 (ancho 38). Cara: y 43-58, x 21-37.
    # Coronilla, donde va el casco: y 36-43, que tiene que quedar intacta.
    cara = recorte[45:56, 23:35]
    coronilla = recorte[36:42, 23:35]
    cuerpo = recorte[110:170, 12:46]
    assert rugosidad(cara) < rugosidad(cuerpo) / 3
    assert rugosidad(coronilla) > rugosidad(cuerpo) * 0.7


def test_el_mismo_video_dos_veces_no_duplica_nada(entorno) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, _cola, vigilante, trabajador, _tmp = entorno
    escribir_video_ruido(entrada / "clip.mp4")
    vigilante.sondear()
    (trabajo,) = vigilante.sondear()
    trabajador.atender_uno()
    antes = {m: contar(motor, m) for m in (Video, Deteccion, Hallazgo, Evidencia, Notificacion)}

    # Otra copia con otro nombre: la cola la reconoce por hash.
    shutil.copy2(entrada / "clip.mp4", entrada / "copia.mp4")
    vigilante.sondear()
    assert vigilante.sondear() == []

    # Y aunque llegara al trabajador, la base la reconoce por hash y la salta.
    repetido = trabajador.procesar(trabajo)
    assert repetido.omitido
    despues = {m: contar(motor, m) for m in antes}
    assert despues == antes
    assert antes[Hallazgo] == 1


def test_si_falla_la_evidencia_no_queda_ni_hallazgo_ni_aviso(
    entorno, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, cola, vigilante, trabajador, tmp = entorno

    def falla(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(evidencias, "insertar", falla)
    escribir_video_ruido(entrada / "clip.mp4")
    vigilante.sondear()
    (trabajo,) = vigilante.sondear()
    assert trabajador.atender_uno() is None

    assert contar(motor, Hallazgo) == 0
    assert contar(motor, Notificacion) == 0
    assert contar(motor, Deteccion) == 0
    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    # Vuelve a la cola, y la base lo dice: no es un error definitivo todavía.
    assert (video.estado, video.intentos) == ("reintentando", 1)
    assert "disco lleno" in (video.error_motivo or "")
    assert cola.estado(trabajo.hash_sha256) is EstadoTrabajo.PENDIENTE
    assert not list((tmp / "evidencia").glob("*.jpg"))  # sin recortes huérfanos

    # El reintento, ya sin la falla, procesa el video completo una sola vez.
    monkeypatch.undo()
    resultado = trabajador.atender_uno()
    assert resultado is not None and resultado.hallazgos == 1
    assert contar(motor, Hallazgo) == 1 and contar(motor, Evidencia) == 1
    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    assert (video.estado, video.intentos, video.error_motivo) == ("listo", 1, None)


def test_un_archivo_que_no_es_video_queda_visible_con_su_motivo(entorno) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, cola, vigilante, trabajador, _tmp = entorno
    roto = entrada / "roto.mp4"
    roto.write_bytes(b"esto no es un video" * 100)
    marca = MTIME.timestamp()
    os.utime(roto, (marca, marca))
    vigilante.sondear()
    (trabajo,) = vigilante.sondear()

    estados = []
    for _ in range(MAXIMO_INTENTOS):
        assert trabajador.atender_uno() is None
        with transaccion(motor) as s:
            (video,) = s.execute(select(Video)).scalars()
            estados.append((video.estado, video.intentos))

    # Sin leerlo no hay duración: el reloj es la fecha del archivo, marcado como de origen dudoso.
    assert estados == [("reintentando", 1), ("reintentando", 2), ("error", MAXIMO_INTENTOS)]
    assert video.error_motivo and video.error_motivo.startswith("No se pudo leer el video")
    assert (video.origen_capture_ts, video.capture_ts_inicio) == ("mtime", MTIME)
    assert video.duracion_s is None and video.bytes == roto.stat().st_size
    assert cola.estado(trabajo.hash_sha256) is EstadoTrabajo.ERROR
    assert contar(motor, Deteccion) == 0


def test_una_camara_sin_reglas_deja_el_video_visible_con_su_motivo(entorno) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, _cola, vigilante, trabajador, _tmp = entorno
    with transaccion(motor) as s:
        s.execute(update(FilaRegla).values(activa=False))
    escribir_video_ruido(entrada / "clip.mp4")
    vigilante.sondear()
    vigilante.sondear()
    assert trabajador.atender_uno() is None

    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    # El archivo sí se leyó: quedan sus datos reales, no los de respaldo.
    assert (video.estado, video.intentos) == ("reintentando", 1)
    assert "no tiene reglas activas" in (video.error_motivo or "")
    assert video.duracion_s == SEGUNDOS
    assert video.capture_ts_inicio == MTIME - timedelta(seconds=SEGUNDOS)


def test_si_el_archivo_se_lee_en_el_reintento_el_video_queda_con_sus_datos_reales(
    entorno, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, _cola, vigilante, trabajador, _tmp = entorno
    original = modulo_trabajador._propiedades
    fallas = iter([OSError("Input/output error")])

    def lee_a_la_segunda(ruta: Path):  # type: ignore[no-untyped-def]
        if (e := next(fallas, None)) is not None:
            raise modulo_trabajador.VideoIlegible(f"No se pudo leer el video: {e}")
        return original(ruta)

    monkeypatch.setattr(modulo_trabajador, "_propiedades", lee_a_la_segunda)
    escribir_video_ruido(entrada / "clip.mp4")
    vigilante.sondear()
    vigilante.sondear()
    assert trabajador.atender_uno() is None  # primer intento: registro de respaldo
    assert trabajador.atender_uno() is not None

    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    # Sin completar la lectura quedaría el reloj de respaldo (el FIN de la grabación).
    assert (video.estado, video.intentos) == ("listo", 1)
    assert video.capture_ts_inicio == MTIME - timedelta(seconds=SEGUNDOS)
    assert (video.duracion_s, video.fps_declarado, video.ancho) == (SEGUNDOS, FPS, ANCHO)


def test_si_no_se_puede_anotar_el_fallo_el_trabajador_sigue_vivo(entorno) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, cola, _vigilante, trabajador, _tmp = entorno
    # Una fuente que no existe: ni el registro ni la anotación pasan la FK.
    vigilante = Vigilante(entrada, cola, fuente_id=999)
    escribir_video_ruido(entrada / "clip.mp4")
    vigilante.sondear()
    (trabajo,) = vigilante.sondear()
    assert trabajador.atender_uno() is None  # no lanza: el bucle `correr` sigue
    assert cola.estado(trabajo.hash_sha256) is EstadoTrabajo.PENDIENTE
    assert contar(motor, Video) == 0


def _agotar_intentos(trabajador: Trabajador, motor: Engine) -> Video:
    for _ in range(MAXIMO_INTENTOS):
        assert trabajador.atender_uno() is None
    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    assert (video.estado, video.intentos) == ("error", MAXIMO_INTENTOS)
    return video


def test_un_video_en_error_se_reintenta_cuando_alguien_lo_pide(entorno) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, cola, vigilante, trabajador, _tmp = entorno
    with transaccion(motor) as s:
        s.execute(update(FilaRegla).values(activa=False))
    escribir_video_ruido(entrada / "clip.mp4")
    vigilante.sondear()
    (trabajo,) = vigilante.sondear()
    video = _agotar_intentos(trabajador, motor)
    assert trabajador.reencolar_pedidos() == 0  # nadie lo pidió: queda en error

    # Se corrige la causa y alguien pide reintentar (lo que hace la API).
    with transaccion(motor) as s:
        s.execute(update(FilaRegla).values(activa=True))
        assert videos.pedir_reintento(s, video.id)
    assert trabajador.reencolar_pedidos() == 1
    assert trabajador.reencolar_pedidos() == 0  # ya está en la cola: no se duplica
    assert cola.estado(trabajo.hash_sha256) is EstadoTrabajo.PENDIENTE

    resultado = trabajador.atender_uno()
    assert resultado is not None and resultado.hallazgos == 1
    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    assert (video.estado, video.intentos, video.error_motivo) == ("listo", 0, None)


def test_pedir_reintento_solo_vale_para_lo_que_fallo(entorno) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, _cola, vigilante, trabajador, _tmp = entorno
    escribir_video_ruido(entrada / "clip.mp4")
    vigilante.sondear()
    vigilante.sondear()
    trabajador.atender_uno()
    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
        assert not videos.pedir_reintento(s, video.id)  # listo: eso es reprocesar sin GPU
    assert trabajador.reencolar_pedidos() == 0


def test_si_redis_se_reinicia_los_intentos_no_pasan_del_maximo(entorno) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, cola, _vigilante, trabajador, _tmp = entorno
    roto = entrada / "roto.mp4"
    roto.write_bytes(b"esto no es un video" * 100)
    vigilante = Vigilante(entrada, cola, fuente_id=1)
    vigilante.sondear()
    vigilante.sondear()
    _agotar_intentos(trabajador, motor)

    # Redis corre sin volumen: al reiniciarse olvida todo y el vigilante vuelve a encolar.
    cola._r.flushall()
    otro = Vigilante(entrada, cola, fuente_id=1)
    otro.sondear()
    assert len(otro.sondear()) == 1
    resultado = trabajador.atender_uno()
    assert resultado is not None and resultado.omitido  # la base manda: ya estaba en error
    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    assert (video.estado, video.intentos) == ("error", MAXIMO_INTENTOS)


def test_si_redis_se_reinicia_a_mitad_la_base_corta_igual_en_el_maximo(entorno) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, cola, vigilante, trabajador, _tmp = entorno
    (entrada / "roto.mp4").write_bytes(b"esto no es un video" * 100)
    vigilante.sondear()
    vigilante.sondear()
    for _ in range(MAXIMO_INTENTOS - 1):
        trabajador.atender_uno()

    cola._r.flushall()  # Redis olvida la cuenta: para él, el próximo es el primer intento
    otro = Vigilante(entrada, cola, fuente_id=1)
    otro.sondear()
    otro.sondear()
    trabajador.atender_uno()
    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    assert (video.estado, video.intentos) == ("error", MAXIMO_INTENTOS)
