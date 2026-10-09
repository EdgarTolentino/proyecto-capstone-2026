"""Avance del análisis en la fila del video (`video.avance_*`), mientras se procesa.

PostgreSQL real; el reloj de ritmo es inyectable (el de un cuadro "tarda" lo que diga el test) y
el avance se lee SIEMPRE desde otra conexión, que es como lo ve la API.
"""

from __future__ import annotations

import os
import shutil
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cv2
import fakeredis
import numpy as np
import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Hallazgo, Video
from gepp_bd.repositorios import videos
from gepp_bd.semilla import cargar, leer
from gepp_vision.detectores import DetectorFalso, Guion
from gepp_worker import trabajador as modulo_trabajador
from gepp_worker.avance import PublicadorDeAvance, contar
from gepp_worker.cola import ColaTrabajos
from gepp_worker.trabajador import Configuracion, Trabajador
from gepp_worker.vigilante import Vigilante
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.exc import IntegrityError

from .test_ingesta import GUION, MTIME, PERFIL, SEGUNDOS, escribir_video_ruido

pytestmark = pytest.mark.integration

HASH = "ab" * 32


class Reloj:
    """El reloj de ritmo del avance: avanza lo que el test diga."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class Observado:
    """El detector falso con un gancho antes de cada cuadro (para mirar la base a mitad)."""

    def __init__(self, interno: DetectorFalso, antes: Callable[[int], None]) -> None:
        self._interno = interno
        self._antes = antes
        self.version = interno.version

    def detectar(self, imagen: Any, *, cuadro_idx: int, capture_ts: Any) -> Any:
        self._antes(cuadro_idx)
        return self._interno.detectar(imagen, cuadro_idx=cuadro_idx, capture_ts=capture_ts)


def leer_avance(motor: Engine, video_id: int = 1) -> dict[str, Any]:
    """Lo que ve otra conexión: una conexión nueva, sin la sesión del trabajador."""
    with motor.connect() as c:
        fila = c.execute(
            text(
                "SELECT estado, avance_fase, avance_s, avance_total_s, avance_velocidad,"
                " avance_ultimo, avance_actualizado FROM video WHERE id = :i"
            ),
            {"i": video_id},
        ).one()
        hallazgos = c.execute(text("SELECT count(*) FROM hallazgo")).scalar_one()
    return {**fila._mapping, "hallazgos": hallazgos}


class Entorno(SimpleNamespace):
    motor: Engine
    entrada: Path
    cola: ColaTrabajos
    vigilante: Vigilante
    reloj: Reloj
    tmp: Path
    fabricar: Callable[..., Trabajador]


@pytest.fixture
def entorno(bd: Engine, tmp_path: Path) -> Iterator[Entorno]:
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
    entrada = tmp_path / "entrada"
    entrada.mkdir()
    cola = ColaTrabajos(fakeredis.FakeRedis())
    reloj = Reloj()
    guion = Guion.desde_json(GUION)

    def fabricar(
        antes: Callable[[int], None] = lambda _i: None,
        cada_s: float = 2.0,
        motor: Engine | None = None,
    ) -> Trabajador:
        config = Configuracion(carpeta_evidencia=tmp_path / "evidencia", avance_cada_s=cada_s)
        return Trabajador(
            motor or bd,
            cola,
            lambda: Observado(DetectorFalso(guion), antes),  # type: ignore[arg-type,return-value]
            config,
            reloj=reloj,
        )

    yield Entorno(
        motor=bd,
        entrada=entrada,
        cola=cola,
        vigilante=Vigilante(entrada, cola, fuente_id=1),
        reloj=reloj,
        tmp=tmp_path,
        fabricar=fabricar,
    )


def encolar_video(e: Entorno, ruta: Path | None = None) -> None:
    """Un video de ruido en la carpeta vigilada, ya estable y encolado."""
    if ruta is None:
        escribir_video_ruido(e.entrada / "clip.mp4")
    else:
        shutil.copy2(ruta, e.entrada / ruta.name)
    e.vigilante.sondear()
    assert len(e.vigilante.sondear()) == 1


def escribir_video(ruta: Path, fps: int, segundos: int) -> Path:
    escritor = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    rng = np.random.default_rng(5)
    for _ in range(fps * segundos):
        escritor.write(rng.integers(0, 256, (48, 64, 3), dtype=np.uint8))
    escritor.release()
    marca = MTIME.timestamp()
    os.utime(ruta, (marca, marca))
    return ruta


# ── A mitad del análisis, desde otra conexión ──────────────────────────────────────────


def test_a_mitad_del_analisis_se_ve_el_avance_y_todavia_no_hay_hallazgos(
    entorno: Entorno,
) -> None:
    e = entorno
    vistas: dict[int, dict[str, Any]] = {}

    def antes(indice: int) -> None:
        e.reloj.t += 0.5  # cada cuadro "tarda" medio segundo
        if indice in (20, 40):
            vistas[indice] = leer_avance(e.motor)

    encolar_video(e)
    resultado = e.fabricar(antes).atender_uno()
    assert resultado is not None and resultado.hallazgos == 1

    mitad = vistas[20]
    assert mitad["estado"] == "procesando" and mitad["avance_fase"] == "analizando"
    assert mitad["avance_total_s"] == SEGUNDOS
    assert 0 < mitad["avance_s"] < SEGUNDOS  # ni vacío ni terminado
    assert mitad["hallazgos"] == 0  # los hallazgos se escriben todos al final
    assert mitad["avance_velocidad"] > 0 and mitad["avance_actualizado"] is not None
    # El KPI es el del último cuadro, no un acumulado: una persona, no una por cuadro visto.
    assert mitad["avance_ultimo"] == {"persona": 1, "casco": 0, "chaleco": 1}
    assert vistas[40]["avance_s"] > mitad["avance_s"]  # y avanza


def test_la_unidad_es_video_de_origen_no_cuadros_inferidos(entorno: Entorno) -> None:
    """25 fps muestreado a 5: contar cuadros contra los fps del video daría 20 % al terminar."""
    e = entorno
    ruta = escribir_video(e.tmp / "veinticinco.mp4", fps=25, segundos=5)
    ultimo_analizando: dict[str, Any] = {}

    def antes(indice: int) -> None:
        if indice == 120:  # el último cuadro muestreado a 5 fps (120 / 25 = 4,8 s)
            ultimo_analizando.update(leer_avance(e.motor))

    encolar_video(e, ruta)
    assert e.fabricar(antes, cada_s=0).atender_uno() is not None

    assert ultimo_analizando["avance_fase"] == "analizando"
    assert 4.0 < ultimo_analizando["avance_s"] <= 5  # 4,6 s ya analizados; no 1,0 (20 %)
    final = leer_avance(e.motor)
    assert (final["estado"], final["avance_fase"]) == ("listo", "guardando")
    assert final["avance_s"] == final["avance_total_s"] == 5


def test_al_terminar_el_avance_es_el_total_y_la_fase_guardando(entorno: Entorno) -> None:
    e = entorno
    encolar_video(e)
    e.fabricar().atender_uno()
    final = leer_avance(e.motor)
    assert (final["avance_fase"], final["avance_s"]) == ("guardando", final["avance_total_s"])
    assert final["avance_total_s"] == SEGUNDOS


# ── Frecuencia: como mucho cada 2 s ───────────────────────────────────────────────────


@pytest.fixture
def video_id(bd: Engine) -> int:
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
        video, _ = videos.registrar(
            s,
            videos.NuevoVideo(
                fuente_id=1,
                ruta="/x/clip.mp4",
                hash_sha256=HASH,
                bytes=1,
                capture_ts_inicio=MTIME,
                origen_capture_ts="mtime",
            ),
        )
        return video.id


@pytest.mark.parametrize(("pausa_s", "publica"), [(1.75, False), (2.0, True), (2.25, True)])
def test_se_publica_desde_los_2_segundos_de_reloj(
    bd: Engine, video_id: int, pausa_s: float, publica: bool
) -> None:
    reloj = Reloj()
    p = PublicadorDeAvance(bd, video_id, 10.0, reloj=reloj)
    p.cuadro(1.0, [])  # el primero siempre se publica
    assert leer_avance(bd, video_id)["avance_s"] == 1.0
    reloj.t += pausa_s
    p.cuadro(2.0, [])
    assert (leer_avance(bd, video_id)["avance_s"] == 2.0) is publica


def test_un_video_corto_igual_publica_el_final(bd: Engine, video_id: int) -> None:
    p = PublicadorDeAvance(bd, video_id, 1.0, reloj=Reloj())
    p.final()  # ningún cuadro alcanzó a publicar
    fila = leer_avance(bd, video_id)
    assert (fila["avance_fase"], fila["avance_s"], fila["avance_total_s"]) == ("guardando", 1, 1)


def test_el_primer_cuadro_en_cero_publica_avance_y_kpi_en_cero(bd: Engine, video_id: int) -> None:
    PublicadorDeAvance(bd, video_id, 10.0, reloj=Reloj()).cuadro(0.0, [])
    fila = leer_avance(bd, video_id)
    assert fila["avance_s"] == 0
    assert fila["avance_ultimo"] == {"persona": 0, "casco": 0, "chaleco": 0}
    assert fila["avance_velocidad"] is None  # sin tiempo transcurrido no hay velocidad


@pytest.mark.parametrize("duracion", [None, 0.0, -1.0])
def test_sin_duracion_conocida_no_hay_total(
    bd: Engine, video_id: int, duracion: float | None
) -> None:
    reloj = Reloj()
    p = PublicadorDeAvance(bd, video_id, duracion, reloj=reloj)
    reloj.t = 1.0
    p.cuadro(3.5, [])
    assert leer_avance(bd, video_id)["avance_total_s"] is None
    p.final()  # sin total, el final es la última posición vista
    fila = leer_avance(bd, video_id)
    esperado = ("guardando", 3.5, None)
    assert (fila["avance_fase"], fila["avance_s"], fila["avance_total_s"]) == esperado


def test_la_posicion_se_acota_al_total_y_nunca_es_negativa(bd: Engine, video_id: int) -> None:
    p = PublicadorDeAvance(bd, video_id, 10.0, reloj=Reloj(), cada_s=0)
    p.cuadro(12.0, [])
    assert leer_avance(bd, video_id)["avance_s"] == 10
    p.cuadro(-1.0, [])
    assert leer_avance(bd, video_id)["avance_s"] == 0


@pytest.mark.parametrize(
    ("posicion", "guardado"),
    [(-0.25, 0.0), (0.0, 0.0), (0.25, 0.25), (9.75, 9.75), (10.0, 10.0), (10.25, 10.0)],
)
def test_la_posicion_justo_en_los_topes_y_a_cada_lado(
    bd: Engine, video_id: int, posicion: float, guardado: float
) -> None:
    """Topes 0 y total (10 s): valores diádicos, resultados exactos."""
    PublicadorDeAvance(bd, video_id, 10.0, reloj=Reloj(), cada_s=0).cuadro(posicion, [])
    assert leer_avance(bd, video_id)["avance_s"] == guardado


def test_la_velocidad_es_video_por_segundo_de_reloj(bd: Engine, video_id: int) -> None:
    reloj = Reloj()
    p = PublicadorDeAvance(bd, video_id, 100.0, reloj=reloj)
    reloj.t = 4.0
    p.cuadro(8.0, [])  # 8 s de video en 4 s de reloj
    assert leer_avance(bd, video_id)["avance_velocidad"] == 2.0


def test_sin_avance_no_hay_velocidad_aunque_haya_tiempo_transcurrido(
    bd: Engine, video_id: int
) -> None:
    """La primera publicación (posición 0) con tiempo de reloj ya corrido daba 0,0x."""
    reloj = Reloj()
    p = PublicadorDeAvance(bd, video_id, 100.0, reloj=reloj)
    reloj.t = 4.0
    p.cuadro(0.0, [])
    assert leer_avance(bd, video_id)["avance_velocidad"] is None


def test_con_el_avance_mas_pequeno_posible_ya_hay_velocidad(bd: Engine, video_id: int) -> None:
    reloj = Reloj()
    p = PublicadorDeAvance(bd, video_id, 100.0, reloj=reloj)
    reloj.t = 4.0
    p.cuadro(0.5, [])  # justo del otro lado de 0
    assert leer_avance(bd, video_id)["avance_velocidad"] == 0.125


def test_el_kpi_cuenta_solo_las_clases_del_avance_en_ese_cuadro() -> None:
    from gepp_core import ClaseDetectada

    def d(clase: ClaseDetectada) -> Any:
        return SimpleNamespace(clase=clase)

    cuadro = [d(ClaseDetectada.PERSONA)] * 2 + [d(ClaseDetectada.CASCO), d(ClaseDetectada.ARNES)]
    assert contar(cuadro) == {"persona": 2, "casco": 1, "chaleco": 0}
    assert contar([]) == {"persona": 0, "casco": 0, "chaleco": 0}


# ── Un reintento parte de cero ─────────────────────────────────────────────────────────


def test_un_reintento_no_muestra_el_avance_del_intento_anterior(entorno: Entorno) -> None:
    e = entorno
    intento = {"n": 1}
    al_empezar_el_segundo: dict[str, Any] = {}

    def antes(indice: int) -> None:
        if intento["n"] == 1 and indice == 40:  # 80 % del video
            raise RuntimeError("falló al 80 %")
        if intento["n"] == 2 and indice == 0:
            al_empezar_el_segundo.update(leer_avance(e.motor))

    encolar_video(e)
    trabajador = e.fabricar(antes, cada_s=0)
    assert trabajador.atender_uno() is None
    tras_fallar = leer_avance(e.motor)
    assert tras_fallar["estado"] == "reintentando" and tras_fallar["avance_s"] >= 3.8  # ~80 %

    intento["n"] = 2
    assert trabajador.atender_uno() is not None

    assert al_empezar_el_segundo["estado"] == "procesando"
    assert {
        k: al_empezar_el_segundo[k]
        for k in ("avance_fase", "avance_s", "avance_total_s", "avance_velocidad", "avance_ultimo")
    } == dict.fromkeys(
        ("avance_fase", "avance_s", "avance_total_s", "avance_velocidad", "avance_ultimo")
    )
    assert al_empezar_el_segundo["avance_actualizado"] is None


# ── Las transacciones no se bloquean entre sí ───────────────────────────────────────────


def _motor_con_espera_corta(motor: Engine) -> Engine:
    """Un motor que no espera más de 3 s un bloqueo: un interbloqueo se ve como error, no como
    una prueba colgada."""
    return create_engine(motor.url, connect_args={"options": "-c lock_timeout=3000"})


def test_si_el_resultado_falla_el_avance_publicado_no_se_revierte(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = entorno

    def falla(*_a: Any, **_k: Any) -> int:
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(modulo_trabajador.detecciones, "insertar", falla)
    corto = _motor_con_espera_corta(e.motor)
    encolar_video(e)
    resultado: list[Any] = []
    hilo = threading.Thread(target=lambda: resultado.append(e.fabricar(motor=corto).atender_uno()))
    hilo.start()
    hilo.join(timeout=30)
    corto.dispose()

    assert not hilo.is_alive(), "el trabajador se quedó esperando un bloqueo"
    fila = leer_avance(e.motor)
    assert fila["estado"] == "reintentando"  # el resultado se revirtió entero
    assert (fila["avance_fase"], fila["avance_s"]) == ("guardando", SEGUNDOS)  # el avance, no
    assert fila["hallazgos"] == 0


def test_publicar_el_avance_no_espera_a_la_transaccion_del_resultado(entorno: Entorno) -> None:
    """Con la fila del video bloqueada por otra transacción, el trabajador no se cuelga ni falla:
    publicar espera su turno corto y, si no puede, dice que no pudo y sigue."""
    e = entorno
    encolar_video(e)
    corto = _motor_con_espera_corta(e.motor)
    liberar = threading.Event()
    bloqueada = threading.Event()

    def sostener() -> None:
        with e.motor.begin() as c:
            c.execute(text("SELECT id FROM video WHERE id = 1 FOR UPDATE"))
            bloqueada.set()
            liberar.wait(timeout=30)

    # La fila del video todavía no existe: se crea al registrarla el trabajador. Se bloquea
    # recién cuando ya está `procesando`, desde el gancho del primer cuadro.
    hilo = threading.Thread(target=sostener)

    def antes(indice: int) -> None:
        if indice == 0:
            hilo.start()
            assert bloqueada.wait(timeout=10)

    trabajador = e.fabricar(antes, cada_s=0, motor=corto)
    resultado: list[Any] = []
    corre = threading.Thread(target=lambda: resultado.append(trabajador.atender_uno()))
    corre.start()
    corre.join(timeout=2)
    liberar.set()  # suelta la fila: el resto del análisis sigue
    corre.join(timeout=60)
    hilo.join(timeout=10)
    corto.dispose()
    assert not corre.is_alive()


def test_con_la_fila_bloqueada_el_analisis_avanza_antes_de_que_se_libere(entorno: Entorno) -> None:
    """Motor de producción (`crear_motor` no fija `lock_timeout`): otra transacción sostiene la
    fila del video y el análisis NO espera en cada publicación; los cuadros siguen pasando
    mientras el bloqueo está puesto."""
    e = entorno
    encolar_video(e)
    liberar = threading.Event()
    bloqueada = threading.Event()
    vistos: list[int] = []
    todos = SEGUNDOS * 5  # cuadros muestreados (a 5 fps)

    def sostener() -> None:
        with e.motor.begin() as c:
            c.execute(text("SELECT id FROM video WHERE id = 1 FOR UPDATE"))
            bloqueada.set()
            liberar.wait(timeout=60)

    sostenedor = threading.Thread(target=sostener)

    def antes(indice: int) -> None:
        if indice == 0:
            sostenedor.start()
            assert bloqueada.wait(timeout=10)
        vistos.append(indice)

    corre = threading.Thread(target=e.fabricar(antes, cada_s=0).atender_uno)
    corre.start()
    try:
        for _ in range(300):  # hasta 30 s, con el bloqueo puesto todo el tiempo
            if len(vistos) >= todos or not corre.is_alive():
                break
            corre.join(timeout=0.1)
        avanzo = len(vistos)
    finally:
        liberar.set()
        corre.join(timeout=60)
        sostenedor.join(timeout=10)
    assert avanzo == todos, f"el análisis se detuvo en el cuadro {avanzo} de {todos}"
    assert not corre.is_alive()


def test_si_publicar_falla_el_analisis_sigue_y_lo_dice_por_stderr(
    entorno: Entorno, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    e = entorno

    def roto(*_a: Any, **_k: Any) -> None:
        raise ConnectionError("sin base")

    monkeypatch.setattr(videos, "publicar_avance", roto)
    encolar_video(e)
    resultado = e.fabricar().atender_uno()

    assert resultado is not None and resultado.hallazgos == 1  # se procesó igual
    assert leer_avance(e.motor)["estado"] == "listo"
    assert "no se pudo publicar el avance" in capsys.readouterr().err


def test_el_avance_no_fecha_detecciones_ni_hallazgos(entorno: Entorno) -> None:
    """Telemetría: `avance_actualizado` es la hora de la base; los tiempos del video no cambian."""
    e = entorno
    encolar_video(e)
    e.fabricar().atender_uno()
    with transaccion(e.motor) as s:
        video = s.scalars(select(Video)).one()
        hallazgo = s.scalars(select(Hallazgo)).one()
        ahora = s.scalar(select(func.now()))
    assert (
        video.capture_ts_inicio
        <= hallazgo.ts_inicio
        <= video.capture_ts_inicio.replace(year=video.capture_ts_inicio.year + 1)
    )
    assert video.avance_actualizado is not None and ahora is not None
    assert hallazgo.ts_inicio < video.avance_actualizado  # el hallazgo es de 2026-01, no de hoy


# ── El repositorio ──────────────────────────────────────────────────────────────────────


def test_una_fase_invalida_se_rechaza_en_el_repositorio_y_en_la_base(
    bd: Engine, video_id: int
) -> None:
    with transaccion(bd) as s, pytest.raises(ValueError, match="fase de avance"):
        videos.publicar_avance(
            s, video_id, fase="terminando", avance_s=0, total_s=None, velocidad=None, ultimo={}
        )
    with pytest.raises(IntegrityError), bd.begin() as c:
        sentencia = text("UPDATE video SET avance_fase = 'terminando' WHERE id = :i")
        c.execute(sentencia, {"i": video_id})


def test_reiniciar_deja_todo_el_avance_en_nulo(bd: Engine, video_id: int) -> None:
    PublicadorDeAvance(bd, video_id, 10.0, reloj=Reloj()).cuadro(1.0, [])
    with transaccion(bd) as s:
        videos.reiniciar_avance(s, video_id)
    fila = leer_avance(bd, video_id)
    assert all(fila[k] is None for k in fila if k.startswith("avance_"))
