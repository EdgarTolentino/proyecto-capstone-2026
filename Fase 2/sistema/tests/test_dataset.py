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


def _leer_manifiesto(manifiesto: Path) -> list[Imagen]:
    with manifiesto.open(encoding="utf-8") as f:
        return [
            Imagen(r["archivo"], r["video"], Particion(r["particion"]), int(r["dhash"], 16))
            for r in csv.DictReader(f)
        ]


def _verificar_manifiestos(carpeta: Path) -> int:
    """Verifica cada `lote*.csv` y la unión de todos. Devuelve cuántos manifiestos vio."""
    manifiestos = sorted(carpeta.glob("lote*.csv"))
    unidos: list[Imagen] = []
    for manifiesto in manifiestos:
        filas = _leer_manifiesto(manifiesto)
        verificar_particion(filas)
        unidos += filas
    # Un video no puede estar en entrenamiento en un lote y en prueba en otro.
    verificar_particion(unidos)
    return len(manifiestos)


def test_los_manifiestos_versionados_respetan_la_particion() -> None:
    """CI verifica en cada empuje todos los `datos/lote*.csv`, cada uno y juntos."""
    if _verificar_manifiestos(RAIZ / "datos") == 0:
        pytest.skip("todavía no hay manifiestos de lote (llegan con la grabación, #10)")


def _escribir_manifiesto(ruta: Path, filas: list[tuple[str, str, str, int]]) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["archivo", "video", "particion", "dhash", "doble_etiquetado"])
        for archivo, video, particion, h in filas:
            w.writerow([archivo, video, particion, f"{h:016x}", "0"])


def test_los_manifiestos_se_buscan_todos_no_solo_lote0(tmp_path: Path) -> None:
    _escribir_manifiesto(tmp_path / "lote0.csv", [("a.jpg", "v1.mp4", "entrenamiento", 0)])
    _escribir_manifiesto(tmp_path / "lote-celular.csv", [("b.jpg", "v2.mp4", "prueba", 2**64 - 1)])
    assert _verificar_manifiestos(tmp_path) == 2


def test_un_video_en_dos_manifiestos_con_distinta_particion_se_rechaza(tmp_path: Path) -> None:
    _escribir_manifiesto(tmp_path / "lote0.csv", [("a.jpg", "v1.mp4", "entrenamiento", 0)])
    _escribir_manifiesto(tmp_path / "lote-celular.csv", [("b.jpg", "v1.mp4", "prueba", 2**64 - 1)])
    with pytest.raises(ParticionInvalida, match="unidad de partición es el video"):
        _verificar_manifiestos(tmp_path)


def test_un_manifiesto_ajeno_a_lote0_con_defecto_se_rechaza(tmp_path: Path) -> None:
    _escribir_manifiesto(tmp_path / "lote0.csv", [("a.jpg", "v1.mp4", "entrenamiento", 0)])
    _escribir_manifiesto(
        tmp_path / "lote-celular.csv",
        [("b.jpg", "v2.mp4", "entrenamiento", 2**64 - 1), ("c.jpg", "v2.mp4", "prueba", 0b101)],
    )
    with pytest.raises(ParticionInvalida):
        _verificar_manifiestos(tmp_path)


def test_sin_manifiestos_no_se_verifica_nada(tmp_path: Path) -> None:
    assert _verificar_manifiestos(tmp_path) == 0


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


def _video_camara_fija(ruta: Path, segundos: int = 10, fps: int = 5) -> None:
    """Fondo quieto con textura y un cuadrado chico que se mueve: así se ve un CCTV fijo."""
    import cv2

    fondo = np.random.default_rng(7).integers(0, 256, (120, 160, 3), dtype=np.uint8)
    escritor = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), fps, (160, 120))
    for i in range(segundos * fps):
        cuadro = fondo.copy()
        x = (i * 3) % 140
        cuadro[50:60, x : x + 10] = 255
        escritor.write(cuadro)
    escritor.release()


def _correr_lote0(tmp_path: Path, particion: str, *extra: str) -> list[dict[str, str]]:
    from scripts.lote0 import main  # type: ignore[import-not-found]

    (tmp_path / "particion.yaml").write_text(particion, encoding="utf-8")
    manifiesto = tmp_path / "lote.csv"
    main(
        [
            str(tmp_path / "videos"),
            str(tmp_path / "salida"),
            "--particion",
            str(tmp_path / "particion.yaml"),
            "--cada-s",
            "1",
            "--manifiesto",
            str(manifiesto),
            *extra,
        ]
    )
    return list(csv.DictReader(manifiesto.open(encoding="utf-8")))


@pytest.mark.integration
@pytest.mark.parametrize(
    ("extra", "minimo", "maximo"), [((), 0, 2), (("--sin-deduplicar",), 10, 10)]
)
def test_con_camara_fija_la_deduplicacion_vacia_el_lote(
    tmp_path: Path, extra: tuple[str, ...], minimo: int, maximo: int
) -> None:
    """En un CCTV fijo el fondo domina el dHash: 150 cuadros del video de prueba quedaron en 1
    (2026-10-01). Para un video que va entero a prueba, `--sin-deduplicar` conserva todos."""
    (tmp_path / "videos").mkdir()
    _video_camara_fija(tmp_path / "videos" / "fija.mp4")
    filas = _correr_lote0(tmp_path, "prueba: [fija.mp4]\n", *extra)
    # 10 s a 1 cuadro por segundo: sin deduplicar quedan los 10; con, se colapsa.
    assert minimo <= len(filas) <= maximo


@pytest.mark.integration
def test_sin_deduplicar_igual_impide_la_fuga_entre_particiones(tmp_path: Path) -> None:
    (tmp_path / "videos").mkdir()
    _video_camara_fija(tmp_path / "videos" / "a.mp4")
    _video_camara_fija(tmp_path / "videos" / "b.mp4")  # la misma escena
    with pytest.raises(ParticionInvalida):
        _correr_lote0(tmp_path, "entrenamiento: [a.mp4]\nprueba: [b.mp4]\n", "--sin-deduplicar")
