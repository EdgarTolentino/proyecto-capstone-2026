"""`scripts/preetiquetar.py`: el modo `--cuadro-entero` corre el modelo sin mosaico."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, ClassVar

import cv2
import numpy as np
import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion

from scripts import preetiquetar  # type: ignore[import-not-found]

ANCHO, ALTO = 576, 1024
RECORTE = "100,100,500,900"  # px: centro (0,5; 0,5) adentro, (0,075; 0,95) afuera
PERSONA = Caja(0.25, 0.25, 0.75, 0.75)
JUNTO_A_LA_CAMARA = Caja(0.0, 0.9, 0.15, 1.0)
# El score distingue de dónde salió cada caja en el COCO.
BASE_ADENTRO, BASE_AFUERA, MOSAICO = 0.9, 0.7, 0.8


class _Base:
    """Reemplaza a DetectorRFDETR: una persona dentro del recorte y otra junto a la cámara."""

    llamadas = 0
    version = "rfdetr-falso:m:h"
    construido: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).construido.append({"args": args, **kwargs})

    def detectar(self, _cuadro: Any, *, cuadro_idx: int, capture_ts: Any) -> list[Deteccion]:
        type(self).llamadas += 1
        return [
            Deteccion(capture_ts, cuadro_idx, ClaseDetectada.PERSONA, PERSONA, BASE_ADENTRO),
            Deteccion(
                capture_ts, cuadro_idx, ClaseDetectada.PERSONA, JUNTO_A_LA_CAMARA, BASE_AFUERA
            ),
        ]


class _Onnx(_Base):
    """Reemplaza a DetectorOnnx: mismas detecciones, otra versión y otro registro."""

    version = "onnx:c:abc123"
    construido: ClassVar[list[dict[str, Any]]] = []


class _Mosaico:
    """Reemplaza a DetectorMosaico: si se usa, deja huella en `usos`."""

    usos = 0

    def __init__(self, interno: Any, _mosaico: Any) -> None:
        self.version = "mosaico[falso]:" + interno.version

    def validar(self, _ancho: int, _alto: int) -> None:
        pass

    def detectar(self, _cuadro: Any, *, cuadro_idx: int, capture_ts: Any) -> list[Deteccion]:
        type(self).usos += 1
        return [Deteccion(capture_ts, cuadro_idx, ClaseDetectada.PERSONA, PERSONA, MOSAICO)]


@pytest.fixture
def lote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    _Base.llamadas = _Mosaico.usos = 0
    _Onnx.construido = []
    _Base.construido = []
    monkeypatch.setattr(preetiquetar, "DetectorRFDETR", _Base)
    monkeypatch.setattr(preetiquetar, "DetectorOnnx", _Onnx)
    monkeypatch.setattr(preetiquetar, "DetectorMosaico", _Mosaico)
    carpeta = tmp_path / "lote"
    carpeta.mkdir()
    for nombre in ("a.jpg", "b.jpg"):
        cv2.imwrite(str(carpeta / nombre), np.zeros((ALTO, ANCHO, 3), np.uint8))
    (tmp_path / "m.csv").write_text("archivo,video\na.jpg,v\nb.jpg,v\n", encoding="utf-8")
    (tmp_path / "c.json").write_text(
        json.dumps({"version": "c", "clases": {"0": "persona"}}), encoding="utf-8"
    )
    return ["a.jpg", "b.jpg"]


def _correr(tmp_path: Path, *extra: str) -> int:
    return preetiquetar.main(
        [
            str(tmp_path / "lote"),
            str(tmp_path / "m.csv"),
            str(tmp_path / "pesos.pth"),
            str(tmp_path / "salida.json"),
            "--clases",
            str(tmp_path / "c.json"),
            *extra,
        ]
    )


def _scores_por_imagen(tmp_path: Path) -> list[list[float]]:
    coco = json.loads((tmp_path / "salida.json").read_text())
    return [
        sorted(a["score"] for a in coco["annotations"] if a["image_id"] == img["id"])
        for img in coco["images"]
    ]


def _descripcion(tmp_path: Path) -> str:
    return str(json.loads((tmp_path / "salida.json").read_text())["info"]["description"])


def test_cuadro_entero_no_usa_el_mosaico(tmp_path: Path, lote: list[str]) -> None:
    assert _correr(tmp_path, "--cuadro-entero") == 0
    assert _Mosaico.usos == 0
    assert _Base.llamadas == len(lote)
    # Las dos personas del modelo, adentro y afuera, y nada del mosaico.
    assert _scores_por_imagen(tmp_path) == [[BASE_AFUERA, BASE_ADENTRO]] * len(lote)
    assert _descripcion(tmp_path) == "pre-etiquetas rfdetr-falso:m:h / cuadro-entero"


def test_con_recorte_sigue_usando_el_mosaico(tmp_path: Path, lote: list[str]) -> None:
    assert _correr(tmp_path, "--recorte", RECORTE) == 0
    assert _Mosaico.usos == len(lote)
    # Adentro manda el mosaico; del modelo solo queda la persona junto a la cámara.
    assert _scores_por_imagen(tmp_path) == [[BASE_AFUERA, MOSAICO]] * len(lote)
    assert _descripcion(tmp_path).endswith("/ mosaico[falso]:rfdetr-falso:m:h")


@pytest.mark.parametrize(
    "extra",
    [
        (),  # ni uno ni otro: falla como antes
        ("--cuadro-entero", "--recorte", "0,0,576,1024"),  # los dos a la vez
    ],
)
@pytest.mark.usefixtures("lote")
def test_exige_exactamente_un_modo(
    tmp_path: Path, extra: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as salida:
        _correr(tmp_path, *extra)
    assert salida.value.code == 2
    assert "recorte" in capsys.readouterr().err
    assert not (tmp_path / "salida.json").exists()


@pytest.mark.usefixtures("lote")
def test_por_defecto_el_motor_es_rfdetr_nano(tmp_path: Path) -> None:
    assert _correr(tmp_path, "--cuadro-entero") == 0
    assert _Onnx.construido == []
    assert len(_Base.construido) == 1
    assert _Base.construido[0]["variante"] == "nano"
    assert _Base.construido[0]["umbral"] == 0.4


@pytest.mark.usefixtures("lote")
def test_variante_explicita_con_rfdetr_se_respeta(tmp_path: Path) -> None:
    assert _correr(tmp_path, "--cuadro-entero", "--variante", "small") == 0
    assert _Base.construido[0]["variante"] == "small"


@pytest.mark.usefixtures("lote")
def test_motor_onnx_usa_detector_onnx_sin_variante(tmp_path: Path) -> None:
    assert _correr(tmp_path, "--motor", "onnx", "--umbral", "0.05", "--cuadro-entero") == 0
    assert _Base.construido == []
    assert len(_Onnx.construido) == 1
    construido = _Onnx.construido[0]
    assert construido["args"] == (tmp_path / "pesos.pth",)
    assert construido["umbral"] == 0.05
    assert "variante" not in construido
    assert construido["mapa"].version == "c"
    assert _descripcion(tmp_path) == "pre-etiquetas onnx:c:abc123 / cuadro-entero"


def test_motor_onnx_con_recorte_usa_el_mosaico(tmp_path: Path, lote: list[str]) -> None:
    assert _correr(tmp_path, "--motor", "onnx", "--recorte", RECORTE) == 0
    assert _Mosaico.usos == len(lote)
    assert _scores_por_imagen(tmp_path) == [[BASE_AFUERA, MOSAICO]] * len(lote)
    assert _descripcion(tmp_path).startswith("pre-etiquetas onnx:")
    assert _descripcion(tmp_path).endswith("/ mosaico[falso]:onnx:c:abc123")


@pytest.mark.parametrize("variante", ["nano", "small"])  # también la que coincide con el defecto
@pytest.mark.usefixtures("lote")
def test_variante_con_motor_onnx_es_error(
    tmp_path: Path, variante: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as salida:
        _correr(tmp_path, "--motor", "onnx", "--cuadro-entero", "--variante", variante)
    assert salida.value.code == 2
    assert "--variante no aplica con --motor onnx" in capsys.readouterr().err
    assert _Onnx.construido == []
    assert not (tmp_path / "salida.json").exists()


CABEZA = Caja(0.4, 0.25, 0.5, 0.3)


class _BaseV3(_Base):
    """Un modelo v3: además de las personas, ve una cabeza."""

    def detectar(self, _cuadro: Any, *, cuadro_idx: int, capture_ts: Any) -> list[Deteccion]:
        return [
            *super().detectar(_cuadro, cuadro_idx=cuadro_idx, capture_ts=capture_ts),
            Deteccion(capture_ts, cuadro_idx, ClaseDetectada.CABEZA, CABEZA, 0.6),
        ]


def _mapa(tmp_path: Path, clases: list[str]) -> None:
    (tmp_path / "c.json").write_text(
        json.dumps({"version": "c", "clases": {str(i): c for i, c in enumerate(clases)}}),
        encoding="utf-8",
    )


V3 = ["persona", "casco", "chaleco", "cabeza", "sin_chaleco"]


def _categorias_y_cabezas(tmp_path: Path) -> tuple[list[str], int]:
    coco = json.loads((tmp_path / "salida.json").read_text())
    nombres = {c["id"]: c["name"] for c in coco["categories"]}
    cabezas = sum(nombres[a["category_id"]] == "cabeza" for a in coco["annotations"])
    return list(nombres.values()), cabezas


@pytest.mark.usefixtures("lote")
def test_sin_con_evidencia_un_modelo_v3_escribe_solo_las_clases_de_cvat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preetiquetar, "DetectorRFDETR", _BaseV3)
    _mapa(tmp_path, V3)
    assert _correr(tmp_path, "--cuadro-entero") == 0
    assert _categorias_y_cabezas(tmp_path) == (["persona", "casco", "chaleco"], 0)


def test_con_evidencia_un_modelo_v3_escribe_la_cabeza(
    tmp_path: Path, lote: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preetiquetar, "DetectorRFDETR", _BaseV3)
    _mapa(tmp_path, V3)
    assert _correr(tmp_path, "--cuadro-entero", "--con-evidencia") == 0
    assert _categorias_y_cabezas(tmp_path) == (V3, len(lote))


@pytest.mark.parametrize(
    ("clases", "faltan"),
    [
        (["persona", "casco", "chaleco"], "['cabeza', 'sin_chaleco']"),
        (["persona", "casco", "chaleco", "cabeza"], "['sin_chaleco']"),  # le falta una sola
    ],
)
@pytest.mark.usefixtures("lote")
def test_con_evidencia_y_un_modelo_sin_esas_clases_falla_sin_escribir(
    tmp_path: Path, clases: list[str], faltan: str
) -> None:
    """Un archivo sin cabezas daría recall 0 en `evaluar.py`: se para antes de detectar."""
    _mapa(tmp_path, clases)
    with pytest.raises(SystemExit, match=f"no tiene {re.escape(faltan)}"):
        _correr(tmp_path, "--cuadro-entero", "--con-evidencia")
    assert not (tmp_path / "salida.json").exists()
    assert _Base.llamadas == 0
