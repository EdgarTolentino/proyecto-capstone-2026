"""Repositorios contra PostgreSQL real: idempotencia, recálculo, versiones y outbox."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Hallazgo as FilaHallazgo
from gepp_bd.modelos import Notificacion, Regla
from gepp_bd.repositorios import detecciones, hallazgos, notificaciones, reglas, videos
from gepp_bd.semilla import PerfilInvalido, cargar, leer
from gepp_core import Severidad, TipoEPP, agregar
from sqlalchemy import Engine, func, select

from ..conftest import T0, cuadro

pytestmark = pytest.mark.integration

PERFIL = Path(__file__).resolve().parents[2] / "perfiles" / "construccion.yaml"


@pytest.fixture
def sembrada(bd: Engine) -> Engine:
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
    return bd


def _video(hash_: str = "a" * 64) -> videos.NuevoVideo:
    return videos.NuevoVideo(
        fuente_id=1,
        ruta="/datos/videos/entrada/camara_01/clip.mp4",
        hash_sha256=hash_,
        bytes=1024,
        capture_ts_inicio=T0,
        origen_capture_ts="metadatos",
        duracion_s=10.0,
        fps_declarado=25.0,
    )


def test_la_semilla_es_idempotente_y_trae_la_gobernanza(sembrada: Engine) -> None:
    with transaccion(sembrada) as s:
        cargar(s, leer(PERFIL))
        filas = list(s.execute(select(Regla).order_by(Regla.id)).scalars())
    assert len(filas) == 2
    assert all(r.norma_fundante == "DS 594 art. 53" for r in filas)
    assert all(sorted(r.epp_exigido) == ["casco", "chaleco"] for r in filas)


def test_la_semilla_rechaza_un_area_que_no_existe(bd: Engine) -> None:
    perfil = leer(PERFIL)
    perfil["faena"] = {"nombre": "Otra"}
    perfil["reglas"][0]["area"] = "Área inventada"
    with pytest.raises(PerfilInvalido, match="Área inventada"), transaccion(bd) as s:
        cargar(s, perfil)


def test_registrar_el_mismo_video_dos_veces_no_lo_duplica(sembrada: Engine) -> None:
    with transaccion(sembrada) as s:
        primero, creado1 = videos.registrar(s, _video())
        segundo, creado2 = videos.registrar(s, _video())
    assert (creado1, creado2) == (True, False)
    assert primero.id == segundo.id


def test_un_video_sin_zona_horaria_no_se_registra() -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        videos.NuevoVideo(
            fuente_id=1,
            ruta="/x.mp4",
            hash_sha256="a" * 64,
            bytes=1,
            capture_ts_inicio=T0.replace(tzinfo=None),
            origen_capture_ts="mtime",
        )


def test_las_detecciones_crudas_permiten_recalcular_sin_gpu(sembrada: Engine) -> None:
    """Lo que se guarda y se relee produce el mismo hallazgo que el cálculo en memoria."""
    fps = 5.0
    cuadros = [cuadro(t=i / fps, idx=i, con_casco=not (1.0 <= i / fps < 5.0)) for i in range(40)]
    with transaccion(sembrada) as s:
        video, _ = videos.registrar(s, _video())
        escritas = detecciones.insertar(
            s, video.id, (d for c in cuadros for d in c), modelo_version="falso-0"
        )
        regla = reglas.a_dominio(reglas.activas(s, area_id=1)[0])
        releidos = list(detecciones.por_cuadro(s, video.id))

    assert escritas == sum(len(c) for c in cuadros)
    # REAL es float4: las coordenadas vuelven con ~7 cifras. Sobra para cajas normalizadas.
    assert len(releidos) == len(cuadros)
    for leido, original in zip(releidos, cuadros, strict=True):
        assert [(d.cuadro_idx, d.capture_ts, d.clase, d.track_id) for d in leido] == [
            (d.cuadro_idx, d.capture_ts, d.clase, d.track_id) for d in original
        ]
        for a, b in zip(leido, original, strict=True):
            assert (a.caja.x1, a.caja.y1, a.caja.x2, a.caja.y2) == pytest.approx(
                (b.caja.x1, b.caja.y1, b.caja.x2, b.caja.y2), abs=1e-6
            )
    (en_memoria,) = agregar(regla, cuadros)
    (desde_bd,) = agregar(regla, releidos)
    assert (desde_bd.ts_inicio, desde_bd.ts_fin, desde_bd.cuadros_confirmados) == (
        en_memoria.ts_inicio,
        en_memoria.ts_fin,
        en_memoria.cuadros_confirmados,
    )
    assert desde_bd.confianza_media == pytest.approx(en_memoria.confianza_media, abs=1e-6)
    assert desde_bd.epp_faltante == frozenset({TipoEPP.CASCO})


def test_versionar_una_regla_crea_fila_nueva_y_desactiva_la_anterior(sembrada: Engine) -> None:
    with transaccion(sembrada) as s:
        v2 = reglas.nueva_version(s, 1, confirmacion_segundos=4.0)
        with pytest.raises(ValueError, match="ya fue reemplazada"):
            reglas.nueva_version(s, 1, confirmacion_segundos=5.0)
        v1 = s.get(Regla, 1)
    assert v1 is not None
    assert (v1.version, v1.activa, v1.confirmacion_segundos) == (1, False, 2.0)
    assert (v2.version, v2.activa, v2.confirmacion_segundos) == (2, True, 4.0)
    assert v2.nombre == v1.nombre


def test_el_nombre_de_una_regla_no_se_versiona(sembrada: Engine) -> None:
    with pytest.raises(ValueError, match="identifican"), transaccion(sembrada) as s:
        reglas.nueva_version(s, 1, nombre="Otra")


def _un_hallazgo(sembrada: Engine):  # type: ignore[no-untyped-def]
    with transaccion(sembrada) as s:
        regla = reglas.a_dominio(reglas.activas(s, area_id=1)[0])
    cuadros = [cuadro(t=i / 5, idx=i, con_casco=False) for i in range(20)]
    (hallazgo,) = agregar(regla, cuadros)
    return hallazgo


def test_el_hallazgo_y_su_aviso_caen_juntos_o_no_cae_ninguno(sembrada: Engine) -> None:
    h = _un_hallazgo(sembrada)
    aviso = hallazgos.NuevaNotificacion(canal="telegram", destinatario="canal-de-prueba")
    contexto = hallazgos.Contexto(fuente_id=1, area_id=1)

    class Falla(Exception):
        pass

    with pytest.raises(Falla), transaccion(sembrada) as s:
        hallazgos.guardar(s, h, contexto, [aviso])
        raise Falla
    with transaccion(sembrada) as s:
        assert s.scalar(select(func.count()).select_from(FilaHallazgo)) == 0
        assert s.scalar(select(func.count()).select_from(Notificacion)) == 0

    with transaccion(sembrada) as s:
        fila = hallazgos.guardar(s, h, contexto, [aviso])
    with transaccion(sembrada) as s:
        guardado = s.get(FilaHallazgo, fila.id)
        assert guardado is not None
        assert guardado.duracion_s == pytest.approx(h.duracion_segundos)
        assert guardado.regla_version == 1
        assert guardado.severidad == Severidad.ALTA
        (n,) = s.execute(select(Notificacion)).scalars()
        assert (n.hallazgo_id, n.estado) == (fila.id, "pendiente")


def test_el_despachador_envia_reintenta_y_acusa(sembrada: Engine) -> None:
    h = _un_hallazgo(sembrada)
    avisos = [
        hallazgos.NuevaNotificacion(canal="correo", destinatario=f"destino-{i}") for i in range(2)
    ]
    with transaccion(sembrada) as s:
        hallazgos.guardar(s, h, hallazgos.Contexto(fuente_id=1, area_id=1), avisos)

    with transaccion(sembrada) as s:
        a, b = notificaciones.tomar_pendientes(s)
        notificaciones.marcar_enviada(s, a.id)
        with pytest.raises(ValueError, match="no está enviada"):
            notificaciones.acusar(s, b.id, None)
        estados = [
            notificaciones.marcar_fallo(s, b.id) for _ in range(notificaciones.MAXIMO_INTENTOS)
        ]
        notificaciones.acusar(s, a.id, None)

    assert estados[:-1] == ["pendiente"] * (notificaciones.MAXIMO_INTENTOS - 1)
    assert estados[-1] == "fallida"
    with transaccion(sembrada) as s:
        assert s.get(Notificacion, a.id).estado == "acusada"  # type: ignore[union-attr]
        assert notificaciones.tomar_pendientes(s) == []


def test_el_reloj_del_hallazgo_es_el_de_captura(sembrada: Engine) -> None:
    h = _un_hallazgo(sembrada)
    with transaccion(sembrada) as s:
        fila = hallazgos.guardar(s, h, hallazgos.Contexto(fuente_id=1, area_id=1))
    assert fila.ts_inicio == h.ts_inicio
    assert fila.ts_inicio - T0 < timedelta(seconds=5)


@pytest.mark.parametrize("cantidad", [5, 6, 7])
def test_la_insercion_por_lotes_no_pierde_ni_repite_filas(
    sembrada: Engine, monkeypatch: pytest.MonkeyPatch, cantidad: int
) -> None:
    """Lote de 3: un lote justo (6), uno incompleto al final (7) y uno bajo el corte (5)."""
    from gepp_bd.modelos import Deteccion as FilaDeteccion

    monkeypatch.setattr(detecciones, "TAMANO_LOTE", 3)
    dets = [
        d
        for i in range(cantidad)
        for d in cuadro(t=i / 5, idx=i, con_chaleco=False, con_casco=False)
    ]
    with transaccion(sembrada) as s:
        video, _ = videos.registrar(s, _video())
        escritas = detecciones.insertar(s, video.id, dets, modelo_version="falso-0")
    with transaccion(sembrada) as s:
        filas = s.scalar(select(func.count()).select_from(FilaDeteccion))
        indices = sorted(s.execute(select(FilaDeteccion.cuadro_idx)).scalars())
    assert escritas == filas == cantidad
    assert indices == list(range(cantidad))
