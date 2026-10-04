"""`scripts/evaluar.py deteccion`: de dos COCO a un JSON y una tabla."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.evaluar import main  # type: ignore[import-not-found]


def _coco(
    score: float | None,
    archivos: tuple[str, ...] = ("a.jpg",),
    descripcion: str = "pre-etiquetas rfdetr-n-epp-v1",
) -> dict[str, Any]:
    """Una persona por imagen; en las predicciones, la de la imagen k tiene `score / k`."""
    anotaciones: list[dict[str, Any]] = []
    for k in range(1, len(archivos) + 1):
        anotacion: dict[str, Any] = {
            "id": k,
            "image_id": k,
            "category_id": 1,
            "bbox": [700, 300, 50, 100],
            "area": 5000,
            "iscrowd": 0,
        }
        if score is not None:
            anotacion["score"] = score / k
        anotaciones.append(anotacion)
    return {
        "info": {"description": descripcion},
        "categories": [{"id": 1, "name": "persona"}, {"id": 2, "name": "tiene_pequenos"}],
        "images": [
            {"id": k, "file_name": a, "width": 1920, "height": 1080}
            for k, a in enumerate(archivos, start=1)
        ],
        "annotations": anotaciones,
    }


@pytest.fixture
def archivos(tmp_path: Path) -> tuple[Path, Path]:
    verdad, predichas = tmp_path / "verdad.json", tmp_path / "pred.json"
    verdad.write_text(json.dumps(_coco(None)), encoding="utf-8")
    predichas.write_text(json.dumps(_coco(0.9)), encoding="utf-8")
    return verdad, predichas


def _args(verdad: Path, predichas: Path, salida: Path, recorte: str) -> list[str]:
    return [
        "deteccion",
        str(verdad),
        str(predichas),
        "--recorte",
        recorte,
        "--origen-verdad",
        "con-preetiquetas",
        "--salida",
        str(salida),
    ]


def test_de_punta_a_punta(
    archivos: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    salida = tmp_path / "metricas.json"
    assert main(_args(*archivos, salida, "600,220,1400,730")) == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["modelo"] == "pre-etiquetas rfdetr-n-epp-v1"
    assert datos["parametros"]["umbral_confianza"] == 0.45
    assert datos["parametros"]["score_minimo"] == 0.9
    assert datos["regiones"]["dentro"]["map50"] == pytest.approx(1.0)
    salida_estandar = capsys.readouterr()
    assert "| dentro | persona | 1 | 1 | 1,000 |" in salida_estandar.out
    assert salida_estandar.err == ""


def test_umbral_cambia_el_de_las_tres_clases(archivos: tuple[Path, Path], tmp_path: Path) -> None:
    # La predicción de persona tiene score 0,9: con --umbral 0.9375 ya no cuenta.
    salida = tmp_path / "metricas.json"
    assert main([*_args(*archivos, salida, "600,220,1400,730"), "--umbral", "0.9375"]) == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["parametros"]["umbral_confianza"] == 0.9375
    persona = datos["regiones"]["dentro"]["clases"][0]
    assert (persona["clase"], persona["n_predichas"]) == ("persona", 0)


def test_imagenes_de_limita_la_evaluacion_y_el_score_minimo(tmp_path: Path) -> None:
    # Verdad y predicciones con a.jpg y b.jpg; --imagenes-de solo con a.jpg. La predicción de
    # b.jpg (score 0,25) queda fuera, así que el score mínimo es el de a.jpg (0,5).
    verdad, predichas, solo = (tmp_path / n for n in ("verdad.json", "pred.json", "a.json"))
    verdad.write_text(json.dumps(_coco(None, ("a.jpg", "b.jpg"))), encoding="utf-8")
    predichas.write_text(json.dumps(_coco(0.5, ("a.jpg", "b.jpg"))), encoding="utf-8")
    solo.write_text(json.dumps(_coco(None, ("a.jpg",))), encoding="utf-8")
    salida = tmp_path / "metricas.json"
    args = [*_args(verdad, predichas, salida, "600,220,1400,730"), "--imagenes-de", str(solo)]
    assert main(args) == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["parametros"]["imagenes"] == 1
    assert datos["imagenes"] == ["a.jpg"]
    assert datos["parametros"]["score_minimo"] == 0.5
    assert "imagenes_de" in datos["entradas"]


# El recorte del mosaico como lo escribe DetectorMosaico.version: 0,3125 x 1920 = 600 px, etc.
MOSAICO = "pre-etiquetas m / mosaico[0.3125,0.2500,0.7500,0.6250x2/384/100px]:m"


@pytest.mark.parametrize(
    ("recorte", "avisa"),
    [
        ("600,270,1440,675", False),  # el mismo, en px de 1920x1080
        ("601,270,1440,675", False),  # 1 px: dentro de la tolerancia
        ("601.5,270,1440,675", True),  # 1,5 px
        ("600,270,1440,673.5", True),
        ("500,220,1400,730", True),
    ],
)
def test_avisa_si_el_recorte_del_mosaico_no_es_el_pedido(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], recorte: str, avisa: bool
) -> None:
    verdad, predichas = tmp_path / "verdad.json", tmp_path / "pred.json"
    verdad.write_text(json.dumps(_coco(None)), encoding="utf-8")
    predichas.write_text(json.dumps(_coco(0.9, descripcion=MOSAICO)), encoding="utf-8")
    assert main(_args(verdad, predichas, tmp_path / "m.json", recorte)) == 0  # no detiene
    err = capsys.readouterr().err
    assert ("mosaico en 600,270,1440,675 px" in err) is avisa


@pytest.mark.parametrize(
    "descripcion", ["pre-etiquetas m", "pre-etiquetas m / mosaico[a,b,c,dx2/384/100px]:m"]
)
def test_sin_recorte_legible_no_avisa(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], descripcion: str
) -> None:
    verdad, predichas = tmp_path / "verdad.json", tmp_path / "pred.json"
    verdad.write_text(json.dumps(_coco(None)), encoding="utf-8")
    predichas.write_text(json.dumps(_coco(0.9, descripcion=descripcion)), encoding="utf-8")
    assert main(_args(verdad, predichas, tmp_path / "m.json", "500,220,1400,730")) == 0
    assert capsys.readouterr().err == ""


def test_verdad_y_predicciones_al_reves_detiene(
    archivos: tuple[Path, Path], tmp_path: Path
) -> None:
    verdad, predichas = archivos
    with pytest.raises(SystemExit, match="score"):
        main(_args(predichas, verdad, tmp_path / "m.json", "600,220,1400,730"))


@pytest.mark.parametrize("recorte", ["600,220,1400", "1400,220,600,730", "a,b,c,d"])
def test_recorte_mal_escrito_detiene(
    archivos: tuple[Path, Path], tmp_path: Path, recorte: str
) -> None:
    with pytest.raises(SystemExit, match="recorte"):
        main(_args(*archivos, tmp_path / "m.json", recorte))


@pytest.mark.parametrize("quitar", ["annotations", "categories", "images"])
def test_coco_incompleto_detiene_con_el_nombre_del_archivo(
    archivos: tuple[Path, Path], tmp_path: Path, quitar: str
) -> None:
    verdad, predichas = archivos
    datos = _coco(None)
    del datos[quitar]
    verdad.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(SystemExit, match=r"verdad\.json") as e:
        main(_args(verdad, predichas, tmp_path / "m.json", "600,220,1400,730"))
    assert quitar in str(e.value)


def test_caja_con_tres_valores_detiene_con_el_nombre_del_archivo(
    archivos: tuple[Path, Path], tmp_path: Path
) -> None:
    verdad, predichas = archivos
    datos = _coco(0.9)
    datos["annotations"][0]["bbox"] = [1, 2, 3]
    predichas.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(SystemExit, match=r"pred\.json"):
        main(_args(verdad, predichas, tmp_path / "m.json", "600,220,1400,730"))
