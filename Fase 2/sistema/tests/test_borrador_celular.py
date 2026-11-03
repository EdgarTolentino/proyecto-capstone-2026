"""El borrador de segmentos del celular (`despliegue/celular/borrador.py`).

Es la garantía de privacidad de la cámara en la sala (D4, condición 4): el video del celular vive
en memoria y se borra al terminar su análisis o, a más tardar, al vencer el TTL, **aunque PostgreSQL
esté caído o trabado**. Umbrales: justo en el TTL, a cada lado y con entradas inválidas.
"""

from __future__ import annotations

import importlib.util
import math
import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

RUTA = Path(__file__).resolve().parents[1] / "despliegue" / "celular" / "borrador.py"
_spec = importlib.util.spec_from_file_location("borrador_celular", RUTA)
assert _spec is not None and _spec.loader is not None
borrador = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(borrador)

TTL = 60.0
AHORA = 1_000.0  # segundos exactos: las diferencias de la prueba son exactas en coma flotante


@pytest.fixture(autouse=True)
def _sin_consulta_pendiente() -> Iterator[None]:
    borrador._consulta = None
    yield
    borrador._consulta = None


def _segmento(carpeta: Path, nombre: str, edad_s: float) -> Path:
    ruta = carpeta / nombre
    ruta.write_bytes(b"x")
    os.utime(ruta, (AHORA - edad_s, AHORA - edad_s))
    return ruta


def _barrer(
    carpeta: Path,
    estado_de: Callable[[Path], str | None],
    avisados: set[Path] | None = None,
    **opciones: float,
) -> list[Path]:
    """Un barrido con la hora fija en AHORA (los tests de tiempo usan su propio reloj)."""
    return borrador.barrido(
        carpeta, estado_de, TTL, lambda: AHORA, set() if avisados is None else avisados, **opciones
    )


class _Reloj:
    """Hora y tiempo monotónico simulados: cada consulta lenta los adelanta."""

    def __init__(self) -> None:
        self.t = 0.0

    def hora(self) -> float:
        return AHORA + self.t

    def monotonico(self) -> float:
        return self.t


def _nombre(i: int, prefijo: str = "camara") -> str:
    return f"{prefijo}-2026-11-03_10-00-{i:02d}-000001.mp4"


# ── El umbral ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("edad", [0.0, 59.75, 60.0])
def test_hasta_el_ttl_inclusive_no_vence(edad: float) -> None:
    assert borrador.vencido(edad, TTL) is False


@pytest.mark.parametrize("edad", [60.25, 61.0, 5000.0])
def test_pasado_el_ttl_vence(edad: float) -> None:
    assert borrador.vencido(edad, TTL) is True


@pytest.mark.parametrize("ttl", [0.0, -1.0, math.nan, math.inf])
def test_un_ttl_invalido_no_deja_de_borrar_en_silencio(ttl: float) -> None:
    with pytest.raises(ValueError, match="TTL"):
        borrador.vencido(10.0, ttl)


def test_una_edad_invalida_se_rechaza() -> None:
    with pytest.raises(ValueError, match="edad"):
        borrador.vencido(math.nan, TTL)


# ── Qué nombre se reconoce ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("camara-2026-11-03_10-00-00-123456.mp4", True),
        ("camara-2024-02-29_23-59-59-1.mp4", True),  # año bisiesto
        ("respaldo-2026-11-03_10-00-00-123456.mp4", False),  # otra ruta
        ("respaldo-2026-13-99_10-00-00-123456.mp4", False),  # otra ruta y fecha imposible
        ("camara-2026-13-99_10-00-00-123456.mp4", False),  # mes 13, día 99
        ("camara-2026-02-30_10-00-00-1.mp4", False),  # 30 de febrero
        ("camara-2025-02-29_10-00-00-1.mp4", False),  # no bisiesto
        ("camara-2026-11-03_24-00-00-1.mp4", False),  # hora 24
        ("camara-2026-11-03_10-60-00-1.mp4", False),  # minuto 60
        ("camara-2026-11-03_10-00-00-123456.mp4.part", False),
        ("camara-2026-11-03.mp4", False),
        ("camara-2026-11-03_10-00-00-.mp4", False),
    ],
)
def test_solo_se_reconoce_la_ruta_camara_con_fecha_real(
    tmp_path: Path, nombre: str, esperado: bool
) -> None:
    ruta = tmp_path / nombre
    ruta.write_bytes(b"x")
    assert borrador.reconocido(ruta) is esperado


def test_el_prefijo_de_la_ruta_se_puede_cambiar(tmp_path: Path) -> None:
    ruta = _segmento(tmp_path, _nombre(0, "sala2"), 0.0)
    assert borrador.reconocido(ruta, "sala2") is True
    assert borrador.reconocido(ruta) is False


def test_un_directorio_con_nombre_valido_no_se_reconoce(tmp_path: Path) -> None:
    carpeta = tmp_path / _nombre(0)
    carpeta.mkdir()
    assert borrador.reconocido(carpeta) is False


# ── El barrido ───────────────────────────────────────────────────────────────


def test_con_la_base_caida_lo_vencido_se_borra_igual(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vencido = _segmento(tmp_path, _nombre(0), TTL + 0.25)
    justo = _segmento(tmp_path, _nombre(1), TTL)
    nuevo = _segmento(tmp_path, _nombre(2), 1.0)

    def base_caida(_: Path) -> str | None:
        raise ConnectionError("PostgreSQL no responde")

    borrados = _barrer(tmp_path, base_caida)

    assert borrados == [vencido]
    assert not vencido.exists()
    assert justo.exists() and nuevo.exists()
    assert "rige solo el TTL" in capsys.readouterr().out


def test_el_vencimiento_se_cumple_antes_de_consultar_la_base(tmp_path: Path) -> None:
    """Si la consulta se traba, lo vencido ya tiene que estar borrado."""
    _segmento(tmp_path, _nombre(0), 1.0)  # el primero en consultarse
    vencido = _segmento(tmp_path, _nombre(1), TTL + 5.0)  # va DESPUÉS en el orden
    visto: list[bool] = []

    def consulta(_: Path) -> str | None:
        visto.append(vencido.exists())
        return None

    _barrer(tmp_path, consulta)

    assert visto == [False]


def test_una_consulta_trabada_no_detiene_los_borrados(tmp_path: Path) -> None:
    """Conexión viva y sin respuesta: el límite duro la abandona y el barrido termina."""
    vencido = _segmento(tmp_path, _nombre(0), TTL + 5.0)
    nuevo = _segmento(tmp_path, _nombre(1), 1.0)
    soltar = threading.Event()

    def trabada(_: Path) -> str | None:
        soltar.wait(5.0)  # una base que no responde
        return "listo"

    inicio = time.monotonic()
    try:
        borrados = _barrer(tmp_path, trabada, limite_s=0.2)
        demora = time.monotonic() - inicio
    finally:
        soltar.set()
        if borrador._consulta is not None:
            borrador._consulta.join(2.0)

    assert demora < 2.0
    assert borrados == [vencido]
    assert nuevo.exists()  # la consulta no respondió: no se asume «listo»


def test_con_la_base_caida_se_consulta_una_sola_vez_por_barrido(tmp_path: Path) -> None:
    """Cada intento contra una base caída puede tardar: no se repite por cada archivo."""
    for i in range(3):
        _segmento(tmp_path, _nombre(i), 1.0)
    llamadas: list[Path] = []

    def base_caida(ruta: Path) -> str | None:
        llamadas.append(ruta)
        raise ConnectionError("PostgreSQL no responde")

    assert _barrer(tmp_path, base_caida) == []
    assert len(llamadas) == 1


@pytest.mark.parametrize("estado", ["listo", "error"])
def test_un_video_terminado_se_borra_aunque_sea_reciente(tmp_path: Path, estado: str) -> None:
    reciente = _segmento(tmp_path, _nombre(0), 1.0)
    assert _barrer(tmp_path, lambda _: estado) == [reciente]


@pytest.mark.parametrize("estado", [None, "en_cola", "procesando", "reintentando"])
def test_un_video_sin_terminar_se_conserva_dentro_del_ttl(
    tmp_path: Path, estado: str | None
) -> None:
    reciente = _segmento(tmp_path, _nombre(0), 1.0)
    assert _barrer(tmp_path, lambda _: estado) == []
    assert reciente.exists()


def test_lo_que_no_es_de_la_ruta_camara_no_se_toca_y_se_avisa_una_vez(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ajeno = _segmento(tmp_path, "notas.txt", 10 * TTL)
    demo = _segmento(tmp_path, "demo.mp4", 10 * TTL)
    otra_ruta = _segmento(tmp_path, "respaldo-2026-13-99_10-00-00-1.mp4", 10 * TTL)
    (tmp_path / "en-curso").mkdir()
    avisados: set[Path] = set()

    for _ in range(2):
        assert _barrer(tmp_path, lambda _: "listo", avisados) == []

    assert ajeno.exists() and demo.exists() and otra_ruta.exists()
    salida = capsys.readouterr().out
    assert salida.count("no reconozco notas.txt") == 1
    assert salida.count("no reconozco respaldo-2026-13-99") == 1
    assert "en-curso" not in salida


# ── El límite duro de la consulta ────────────────────────────────────────────


def test_con_limite_devuelve_el_valor_y_relanza_el_error() -> None:
    assert borrador.con_limite(lambda: 42, 1.0) == 42
    with pytest.raises(KeyError, match="x"):
        borrador.con_limite(lambda: {}["x"], 1.0)


def test_con_limite_no_apila_hilos_si_la_anterior_sigue_trabada() -> None:
    soltar = threading.Event()
    try:
        with pytest.raises(TimeoutError, match="no respondió"):
            borrador.con_limite(lambda: soltar.wait(5.0), 0.1)
        inicio = time.monotonic()
        with pytest.raises(TimeoutError, match="anterior"):
            borrador.con_limite(lambda: 1, 5.0)
        assert time.monotonic() - inicio < 0.5  # inmediato: no esperó otra consulta
    finally:
        soltar.set()
        if borrador._consulta is not None:
            borrador._consulta.join(2.0)


# ── El presupuesto total del paso 2 y la reevaluación del vencimiento ────────


def test_las_consultas_comparten_un_presupuesto_total_por_barrido(tmp_path: Path) -> None:
    """Seis consultas de 0,8 s y 3 s de presupuesto: paran al agotarse, no una por archivo."""
    for i in range(6):
        _segmento(tmp_path, _nombre(i), 10.0)
    reloj = _Reloj()
    llamadas: list[Path] = []

    def lenta(ruta: Path) -> str | None:
        llamadas.append(ruta)
        reloj.t += 0.8
        return None

    borrador.barrido(
        tmp_path,
        lenta,
        TTL,
        reloj.hora,
        set(),
        limite_s=3.0,
        presupuesto_s=3.0,
        monotonico=reloj.monotonico,
    )

    assert len(llamadas) == 4  # 0,0 · 0,8 · 1,6 · 2,4 → a los 3,2 s ya no queda presupuesto
    assert reloj.t < 3.0 + 0.8


def test_lo_que_vence_mientras_se_consulta_se_borra_en_el_mismo_barrido(tmp_path: Path) -> None:
    """Archivos de 57,5 s (TTL 60): vencen durante las consultas, no esperan al próximo barrido."""
    rutas = [_segmento(tmp_path, _nombre(i), 57.5) for i in range(6)]
    reloj = _Reloj()

    def lenta(_: Path) -> str | None:
        reloj.t += 0.8
        return None  # el video aún no termina

    borrados = borrador.barrido(
        tmp_path,
        lenta,
        TTL,
        reloj.hora,
        set(),
        limite_s=3.0,
        presupuesto_s=3.0,
        monotonico=reloj.monotonico,
    )

    assert sorted(borrados) == rutas
    assert not any(r.exists() for r in rutas)


def test_cada_consulta_respeta_lo_que_queda_del_presupuesto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(2):
        _segmento(tmp_path, _nombre(i), 1.0)
    reloj = _Reloj()
    limites: list[float] = []
    real = borrador.con_limite

    def espia(fn: Callable[[], str | None], limite_s: float) -> str | None:
        limites.append(limite_s)
        return real(fn, limite_s)

    monkeypatch.setattr(borrador, "con_limite", espia)

    def lenta(_: Path) -> str | None:
        reloj.t += 2.5
        return None

    borrador.barrido(
        tmp_path,
        lenta,
        TTL,
        reloj.hora,
        set(),
        limite_s=3.0,
        presupuesto_s=3.0,
        monotonico=reloj.monotonico,
    )

    assert limites == [3.0, 0.5]  # la segunda solo puede usar lo que queda del presupuesto


def test_lo_que_ya_venció_no_gasta_una_consulta(tmp_path: Path) -> None:
    primero = _segmento(tmp_path, _nombre(0), 59.5)
    segundo = _segmento(tmp_path, _nombre(1), 59.5)
    reloj = _Reloj()
    llamadas: list[Path] = []

    def lenta(ruta: Path) -> str | None:
        llamadas.append(ruta)
        reloj.t += 0.8  # al terminar, el segundo ya pasó de los 60 s
        return None

    borrados = borrador.barrido(
        tmp_path, lenta, TTL, reloj.hora, set(), monotonico=reloj.monotonico
    )

    assert llamadas == [primero]  # el segundo venció antes de su turno: se borra sin consultar
    assert segundo in borrados
