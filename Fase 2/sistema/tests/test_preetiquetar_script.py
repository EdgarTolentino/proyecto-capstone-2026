"""`scripts/preetiquetar.py`: el modo `--cuadro-entero` corre el modelo sin mosaico."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion

from scripts import preetiquetar  # type: ignore[import-not-found]

ANCHO, ALTO = 576, 1024
PERSONA = Caja(0.25, 0.25, 0.75, 0.75)


class _Base:
    """Reemplaza a DetectorRFDETR: una persona por cuadro y cuenta las llamadas."""

    llamadas = 0
    version = "rfdetr-falso:m:h"

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    def detectar(self, _cuadro: Any, *, cuadro_idx: int, capture_ts: Any) -> list[Deteccion]:
        type(self).llamadas += 1
        return [Deteccion(capture_ts, cuadro_idx, ClaseDetectada.PERSONA, PERSONA, 0.9)]


class _Mosaico:
    """Reemplaza a DetectorMosaico: si se usa, deja huella en `usos`."""

    usos = 0

    def __init__(self, interno: Any, _mosaico: Any) -> None:
        self.version = "mosaico[falso]:" + interno.version

    def validar(self, _ancho: int, _alto: int) -> None:
        pass

    def detectar(self, _cuadro: Any, *, cuadro_idx: int, capture_ts: Any) -> list[Deteccion]:
        type(self).usos += 1
        return [Deteccion(capture_ts, cuadro_idx, ClaseDetectada.PERSONA, PERSONA, 0.8)]


@pytest.fixture
def lote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    _Base.llamadas = _Mosaico.usos = 0
    monkeypatch.setattr(preetiquetar, "DetectorRFDETR", _Base)
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


def _descripcion(tmp_path: Path) -> str:
    return str(json.loads((tmp_path / "salida.json").read_text())["info"]["description"])


def test_cuadro_entero_no_usa_el_mosaico(tmp_path: Path, lote: list[str]) -> None:
    assert _correr(tmp_path, "--cuadro-entero") == 0
    assert _Mosaico.usos == 0
    assert _Base.llamadas == len(lote)
    coco = json.loads((tmp_path / "salida.json").read_text())
    assert len(coco["annotations"]) == len(lote)  # una persona por cuadro, sin duplicar
    assert _descripcion(tmp_path) == "pre-etiquetas rfdetr-falso:m:h / cuadro-entero"


def test_con_recorte_sigue_usando_el_mosaico(tmp_path: Path, lote: list[str]) -> None:
    assert _correr(tmp_path, "--recorte", "100,100,500,900") == 0
    assert _Mosaico.usos == len(lote)
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
