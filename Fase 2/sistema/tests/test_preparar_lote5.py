"""Lote 5 (epp-v4): export COCO de CVAT como fuente, con el video entero en una partición."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
import yaml
from gepp_core import Caja, ClaseDetectada
from gepp_vision.dataset import Particion
from gepp_vision.entrenamiento import (
    Anotada,
    CategoriaDesconocida,
    Fuente,
    cargar_fuentes,
    completar_clases,
    desde_coco,
    es_del_video_de_prueba,
    grupo,
    particion_de_video,
    particion_estable,
)

from scripts import descargar_datasets, preparar_dataset  # type: ignore[import-not-found]

FUENTES = Path(__file__).resolve().parents[1] / "scripts/fuentes.yaml"
P, C, V = ClaseDetectada.PERSONA, ClaseDetectada.CASCO, ClaseDetectada.CHALECO
CABEZA, SIN_CHALECO = ClaseDetectada.CABEZA, ClaseDetectada.SIN_CHALECO
# CVAT numera las etiquetas a su manera y no en el orden de CLASES_V3.
CATEGORIAS_CVAT = {10: "sin_chaleco", 11: "cabeza", 12: "chaleco", 13: "casco", 14: "persona"}


def _lote5() -> Fuente:
    return next(f for f in cargar_fuentes(FUENTES) if f.nombre == "lote5-cctv-cc")


# --- el lote 5 en fuentes.yaml ---------------------------------------------------------


def test_el_lote5_no_se_completa_con_modelos() -> None:
    fuente = _lote5()
    assert fuente.exhaustivas == {P, C, V, CABEZA, SIN_CHALECO}
    img = Anotada("a_00001.jpg", 100, 100, [])
    propuestas = [(P, Caja(0.1, 0.1, 0.2, 0.2)), (C, Caja(0.5, 0.5, 0.6, 0.6))]
    assert completar_clases(img, propuestas, fuente.exhaustivas) == []


def test_el_lote5_fija_un_video_a_validacion_y_el_resto_a_entrenamiento() -> None:
    fuente = _lote5()
    assert fuente.validacion == {"nllyukzkhko"}
    assert particion_de_video("nllyukzkhko", fuente) is Particion.VALIDACION
    for otro in ("enfcsvwyhy4", "v2cczj7g2ba", "unvideo_cualquiera"):
        assert particion_de_video(otro, fuente) is Particion.ENTRENAMIENTO


def test_la_extension_en_mayusculas_no_saca_el_cuadro_de_su_video() -> None:
    assert grupo("NLlyuKZKHKo_00002.JPG", _lote5()) == grupo("NLlyuKZKHKo_00001.jpg", _lote5())


def test_el_id_del_video_conserva_guiones_bajos() -> None:
    assert grupo("SfQxyGXQ_I0_00071.jpg", _lote5()) == "sfqxygxq_i0"


def test_sin_particion_fijada_se_reparte_por_hash() -> None:
    fuente = Fuente("x", "CC0", {}, frozenset())
    assert particion_de_video("v", fuente) is particion_estable("x/v")


def _yaml(tmp_path: Path, particion: object, grupos: object = ("^(.+)_\\d+$",)) -> Path:
    ruta = tmp_path / "f.yaml"
    fuente = {
        "nombre": "x",
        "licencia": "CC0",
        "origen": {},
        "clases": {},
        "exhaustivas": [],
        "grupos": list(grupos),  # type: ignore[call-overload]
        "particion": particion,
    }
    ruta.write_text(yaml.safe_dump({"fuentes": [fuente]}))
    return ruta


@pytest.mark.parametrize(
    "particion",
    [
        {"por_defecto": "test"},  # la prueba no sale de una fuente de entrenamiento
        {"por_defecto": "train", "test": ["v"]},
        {"valid": ["v"]},  # sin `por_defecto`, el resto quedaría sin partición
    ],
)
def test_una_particion_invalida_falla_al_cargar(tmp_path: Path, particion: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="x: `particion`"):
        cargar_fuentes(_yaml(tmp_path, particion))


def test_fijar_videos_sin_grupos_falla_al_cargar(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no declara `grupos`"):
        cargar_fuentes(_yaml(tmp_path, {"por_defecto": "train"}, grupos=()))


@pytest.mark.parametrize(
    ("nombre", "es"),
    [
        ("GPCHfE_-XQE_00001.jpg", True),
        ("yt_GPCHfE_min020_000150.jpg", True),
        ("NLlyuKZKHKo_00001.jpg", False),
    ],
)
def test_el_video_de_prueba_se_reconoce(nombre: str, es: bool) -> None:
    assert es_del_video_de_prueba(nombre) is es


# --- el COCO de CVAT -------------------------------------------------------------------


def _coco_cvat(archivo: str = "A_00001.jpg") -> dict[str, Any]:
    cajas = [
        (14, [0, 0, 20, 50]),
        (13, [0, 0, 10, 10]),
        (11, [30, 0, 10, 10]),
        (10, [60, 0, 20, 50]),
    ]
    categorias = [{"id": i, "name": n, "supercategory": ""} for i, n in CATEGORIAS_CVAT.items()]
    return {
        # `tiene_pequenos` es una etiqueta de imagen: puede figurar sin ninguna caja.
        "categories": [*categorias, {"id": 15, "name": "tiene_pequenos", "supercategory": ""}],
        "images": [{"id": 1, "file_name": archivo, "width": 100, "height": 100}],
        "annotations": [
            {
                "id": k,
                "image_id": 1,
                "category_id": c,
                "bbox": b,
                "attributes": {"origen": "manual", "ocluida": "no"},
            }
            for k, (c, b) in enumerate(cajas, start=1)
        ],
    }


def test_las_cinco_clases_de_cvat_se_traducen_por_nombre_y_no_por_id() -> None:
    (img,) = desde_coco(_coco_cvat(), _lote5())
    assert [c for c, _ in img.cajas] == [P, C, CABEZA, SIN_CHALECO]
    assert img.cajas[2][1] == Caja(0.3, 0.0, 0.4, 0.1)


def test_una_categoria_desconocida_con_cajas_detiene_todo() -> None:
    coco = _coco_cvat()
    coco["categories"].append({"id": 16, "name": "guantes", "supercategory": ""})
    coco["annotations"][0]["category_id"] = 16
    with pytest.raises(CategoriaDesconocida, match="guantes"):
        desde_coco(coco, _lote5())


def test_una_categoria_ajena_sin_cajas_tambien_detiene_un_export_de_cvat() -> None:
    coco = _coco_cvat()
    coco["categories"].append({"id": 16, "name": "guantes", "supercategory": ""})
    with pytest.raises(CategoriaDesconocida, match="guantes"):
        desde_coco(coco, _lote5())


# --- de punta a punta: el script --------------------------------------------------------


def _montar(
    tmp_path: Path, videos: list[str], valid: list[str], permitidos: list[str] | None = None
) -> tuple[Path, Path]:
    """Crudos con 3 cuadros por video (un zip por tarea, como en CVAT) y su fuentes.yaml."""
    lote = tmp_path / "crudos" / "lote5-cctv-cc"
    (lote / "exportes").mkdir(parents=True)
    rng = np.random.default_rng(7)  # ruido distinto por cuadro: ningún par es la misma escena
    for v in videos:
        (lote / "cuadros" / v).mkdir(parents=True)
        nombres = [f"{v}_{n:05d}.jpg" for n in (1, 2, 3)]
        for nombre in nombres:
            ruido = rng.integers(0, 255, (100, 100, 3), np.uint8)
            cv2.imwrite(str(lote / "cuadros" / v / nombre), ruido)
        coco = _coco_cvat()
        coco["images"] = [
            {"id": i, "file_name": n, "width": 100, "height": 100} for i, n in enumerate(nombres, 1)
        ]
        # las mismas 4 cajas en cada uno de los 3 cuadros
        coco["annotations"] = [
            {**a, "id": 4 * i + j, "image_id": i}
            for i in (1, 2, 3)
            for j, a in enumerate(_coco_cvat()["annotations"], 1)
        ]
        # CVAT pone las anotaciones en `annotations/instances_default.json` dentro del zip.
        with zipfile.ZipFile(lote / "exportes" / f"{v}.zip", "w") as z:
            z.writestr("annotations/instances_default.json", json.dumps(coco))
    todas = yaml.safe_load(FUENTES.read_text())["fuentes"]
    fuente = next(f for f in todas if f["nombre"] == "lote5-cctv-cc")
    fuente["particion"]["valid"] = valid
    fuente["videos"] = videos if permitidos is None else permitidos
    ruta = tmp_path / "fuentes.yaml"
    ruta.write_text(yaml.safe_dump({"fuentes": [fuente]}))
    return tmp_path / "crudos", ruta


def _correr(tmp_path: Path, crudos: Path, ruta: Path, *extra: str) -> Path:
    salida = tmp_path / "salida"
    args = [str(crudos), str(salida), "--fuentes", str(ruta), "--sin-completar", *extra]
    assert preparar_dataset.main(args) == 0
    return salida


def _imagenes(salida: Path, particion: str) -> list[str]:
    coco = json.loads((salida / particion / "_annotations.coco.json").read_text())
    return sorted(i["file_name"] for i in coco["images"])


def test_cada_video_va_entero_a_una_particion(tmp_path: Path) -> None:
    crudos, ruta = _montar(tmp_path, ["vidA", "vid_B", "vidC"], valid=["vid_B"])
    salida = _correr(tmp_path, crudos, ruta)
    assert _imagenes(salida, "valid") == [f"lote5-cctv-cc__vid_B_{n:05d}.jpg" for n in (1, 2, 3)]
    assert len(_imagenes(salida, "train")) == 6
    assert _imagenes(salida, "test") == []
    conteo = json.loads((salida / "resumen.json").read_text())["conteo"]
    assert conteo["lote5-cctv-cc/validacion/cabeza"] == 3
    assert conteo["lote5-cctv-cc/entrenamiento/sin_chaleco"] == 6
    assert not any(k.endswith("_automatica") for k in conteo)  # sin completar


def test_un_cuadro_del_video_de_prueba_detiene_la_preparacion(tmp_path: Path) -> None:
    crudos, ruta = _montar(tmp_path, ["vidA", "GPCHfE_-XQE"], valid=["vidA"])
    with pytest.raises(SystemExit, match="video de prueba"):
        _correr(tmp_path, crudos, ruta)


def test_un_video_de_valid_que_no_esta_en_el_export_detiene_la_preparacion(tmp_path: Path) -> None:
    todos = ["vidA", "vidC", "vid_B"]
    crudos, ruta = _montar(tmp_path, ["vidA", "vidC"], valid=["vid_B"], permitidos=todos)
    with pytest.raises(SystemExit, match="sin ellos no hay validación"):
        _correr(tmp_path, crudos, ruta)


def test_un_cuadro_que_falta_en_disco_detiene_la_preparacion(tmp_path: Path) -> None:
    crudos, ruta = _montar(tmp_path, ["vidA", "vidC"], valid=["vidA"])
    (crudos / "lote5-cctv-cc/cuadros/vidC/vidC_00002.jpg").unlink()
    with pytest.raises(SystemExit, match="falta el cuadro"):
        _correr(tmp_path, crudos, ruta)


def test_una_categoria_desconocida_en_el_export_detiene_el_script(tmp_path: Path) -> None:
    crudos, ruta = _montar(tmp_path, ["vidA", "vidC"], valid=["vidA"])
    zip_ = crudos / "lote5-cctv-cc/exportes/vidC.zip"
    with zipfile.ZipFile(zip_) as z:
        coco = json.loads(z.read("annotations/instances_default.json"))
    coco["categories"][0]["name"] = "guantes"
    with zipfile.ZipFile(zip_, "w") as z:
        z.writestr("annotations/instances_default.json", json.dumps(coco))
    with pytest.raises(CategoriaDesconocida, match="guantes"):
        _correr(tmp_path, crudos, ruta)


def test_un_video_fuera_de_la_lista_de_procedencia_detiene_la_preparacion(tmp_path: Path) -> None:
    crudos, ruta = _montar(tmp_path, ["vidA", "foso"], valid=["vidA"], permitidos=["vidA"])
    with pytest.raises(SystemExit, match="no está en `videos`"):
        _correr(tmp_path, crudos, ruta)


def test_si_las_fugas_vacian_valid_no_se_prepara_en_silencio(tmp_path: Path) -> None:
    crudos, ruta = _montar(tmp_path, ["vidA", "vid_B"], valid=["vid_B"])
    # Otra fuente trae en su `test` los mismos cuadros del video de valid.
    test = crudos / "otra" / "test"
    test.mkdir(parents=True)
    imagenes = []
    for n in (1, 2, 3):
        origen = crudos / f"lote5-cctv-cc/cuadros/vid_B/vid_B_{n:05d}.jpg"
        (test / f"t{n}.jpg").write_bytes(origen.read_bytes())
        imagenes.append({"id": n, "file_name": f"t{n}.jpg", "width": 100, "height": 100})
    coco = {"categories": [{"id": 1, "name": "p"}], "images": imagenes, "annotations": []}
    (test / "_annotations.coco.json").write_text(json.dumps(coco))
    fuentes = yaml.safe_load(ruta.read_text())["fuentes"]
    fuentes.append(
        {
            "nombre": "otra",
            "licencia": "CC0",
            "origen": {},
            "clases": {"p": "persona"},
            "exhaustivas": ["persona", "casco", "chaleco"],
        }
    )
    ruta.write_text(yaml.safe_dump({"fuentes": fuentes}))
    with pytest.raises(SystemExit, match="sin ellos no hay validación"):
        _correr(tmp_path, crudos, ruta)


def test_con_limite_el_resumen_lo_marca_incompleto(tmp_path: Path) -> None:
    crudos, ruta = _montar(tmp_path, ["vidA", "vid_B"], valid=["vid_B"])
    salida = _correr(tmp_path, crudos, ruta, "--limite", "2")
    assert json.loads((salida / "resumen.json").read_text())["limite"] == 2


def test_el_descargador_salta_una_fuente_de_entrega_manual(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        descargar_datasets.main(
            [str(tmp_path), "--fuentes", str(FUENTES), "--solo", "lote5-cctv-cc"]
        )
        == 0
    )
    assert "entrega manual" in capsys.readouterr().out
