"""Partición del dataset: la regla metodológica número uno (`02-plan-de-evaluacion.md`)."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import pytest
from gepp_vision.dataset import (
    UMBRAL_DUPLICADO,
    Imagen,
    Particion,
    ParticionInvalida,
    deduplicar,
    dhash,
    distancia,
    verificar_particion,
)

from .video_sintetico import escribir_video

RAIZ = Path(__file__).resolve().parents[1]


def _escena(semilla: int) -> np.ndarray:
    return np.random.default_rng(semilla).integers(0, 256, (120, 160, 3), dtype=np.uint8)


def test_la_misma_escena_con_ruido_queda_bajo_el_umbral() -> None:
    base = _escena(1)
    ruido = np.random.default_rng(2).integers(-4, 5, base.shape)
    parecida = np.clip(base.astype(np.int16) + ruido, 0, 255).astype(np.uint8)
    assert distancia(dhash(base), dhash(parecida)) <= UMBRAL_DUPLICADO


def test_escenas_distintas_quedan_lejos() -> None:
    assert distancia(dhash(_escena(1)), dhash(_escena(3))) > UMBRAL_DUPLICADO


def test_deduplicar_conserva_la_primera_de_cada_escena() -> None:
    a, b = dhash(_escena(1)), dhash(_escena(3))
    assert deduplicar([a, a, b, a ^ 0b1, b]) == [0, 2]


@pytest.mark.parametrize("umbral", [0, 64])
def test_deduplicar_en_los_extremos_del_umbral(umbral: int) -> None:
    hashes = [0, 1, 3, 2**64 - 1]
    conservados = deduplicar(hashes, umbral=umbral)
    # 0: solo cae lo idéntico (no hay) · 64: todo se parece a todo, queda la primera
    assert conservados == ([0, 1, 2, 3] if umbral == 0 else [0])


def _img(archivo: str, video: str, p: Particion, h: int) -> Imagen:
    return Imagen(archivo, video, p, h)


def test_un_video_en_dos_particiones_se_rechaza() -> None:
    with pytest.raises(ParticionInvalida, match="unidad de partición es el video"):
        verificar_particion(
            [
                _img("a.jpg", "v1.mp4", Particion.ENTRENAMIENTO, 0),
                _img("b.jpg", "v1.mp4", Particion.PRUEBA, 2**64 - 1),
            ]
        )


def test_la_misma_escena_en_dos_particiones_se_rechaza() -> None:
    with pytest.raises(ParticionInvalida, match="misma escena"):
        verificar_particion(
            [
                _img("a.jpg", "v1.mp4", Particion.ENTRENAMIENTO, 0b1010),
                _img("b.jpg", "v2.mp4", Particion.PRUEBA, 0b1011),
            ]
        )


def test_escenas_parecidas_dentro_de_una_particion_se_admiten() -> None:
    verificar_particion(
        [
            _img("a.jpg", "v1.mp4", Particion.ENTRENAMIENTO, 0b1010),
            _img("b.jpg", "v2.mp4", Particion.ENTRENAMIENTO, 0b1011),
        ]
    )


def test_el_manifiesto_versionado_respeta_la_particion() -> None:
    """Cuando exista `datos/lote0.csv` en el repositorio, CI lo verifica en cada empuje."""
    manifiesto = RAIZ / "datos" / "lote0.csv"
    if not manifiesto.exists():
        pytest.skip("todavía no hay manifiesto del lote 0 (llega con la grabación, #10)")
    with manifiesto.open(encoding="utf-8") as f:
        filas = [
            Imagen(r["archivo"], r["video"], Particion(r["particion"]), int(r["dhash"], 16))
            for r in csv.DictReader(f)
        ]
    verificar_particion(filas)


@pytest.mark.integration
def test_el_script_arma_el_lote_desde_videos(tmp_path: Path) -> None:
    from scripts.lote0 import main  # type: ignore[import-not-found]

    videos = tmp_path / "videos"
    videos.mkdir()
    escribir_video(videos / "cam1.mp4", fps=10, segundos=6)
    escribir_video(videos / "cam2.mp4", fps=10, segundos=6)
    (tmp_path / "particion.yaml").write_text(
        "entrenamiento: [cam1.mp4]\nprueba: [cam2.mp4]\n", encoding="utf-8"
    )
    manifiesto = tmp_path / "lote0.csv"
    codigo = main(
        [
            str(videos),
            str(tmp_path / "salida"),
            "--particion",
            str(tmp_path / "particion.yaml"),
            "--cada-s",
            "1",
            "--manifiesto",
            str(manifiesto),
        ]
    )
    assert codigo == 0
    filas = list(csv.DictReader(manifiesto.open(encoding="utf-8")))
    # Los dos videos son idénticos: la escena de cam2 ya está en cam1 y se descarta,
    # así que la deduplicación impide la fuga antes de que llegue a la verificación.
    assert {f["video"] for f in filas} == {"cam1.mp4"}
    assert len(filas) == len(list((tmp_path / "salida").glob("*.jpg")))
    assert sum(int(f["doble_etiquetado"]) for f in filas) == math.ceil(len(filas) * 0.10)


@pytest.mark.parametrize(("n", "esperado"), [(0, 0), (1, 1), (10, 1), (11, 2), (100, 10)])
def test_el_doble_etiquetado_toma_el_diez_por_ciento_y_nunca_cero(n: int, esperado: int) -> None:
    from scripts.lote0 import elegir_doble  # type: ignore[import-not-found]

    elegidos = elegir_doble(n)
    assert len(elegidos) == esperado
    assert elegidos == elegir_doble(n)  # misma semilla, misma elección
    assert all(0 <= i < n for i in elegidos)
