"""El motor del modelo del trabajador: ONNX en CPU o el `.pth` en la GPU (#203)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def modelo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ruta = tmp_path / "modelo.pth"
    ruta.write_bytes(b"")
    monkeypatch.delenv("GEPP_GUION_FALSO", raising=False)
    monkeypatch.delenv("GEPP_UMBRAL_CONFIANZA", raising=False)
    monkeypatch.setenv("GEPP_MODELO_RUTA", str(ruta))
    return ruta


def test_el_motor_rfdetr_usa_la_variante_y_el_umbral(
    modelo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gepp_vision.detectores import rfdetr
    from gepp_worker.__main__ import _fabrica_detector

    construidos: list[dict[str, Any]] = []

    class Falso:
        version = "rfdetr-falso"

        def __init__(self, pesos: Path, **kw: Any) -> None:
            construidos.append({"pesos": pesos, **kw})

    monkeypatch.setattr(rfdetr, "DetectorRFDETR", Falso)
    monkeypatch.setenv("GEPP_MODELO_MOTOR", "rfdetr")
    monkeypatch.setenv("GEPP_MODELO_VARIANTE", "small")
    monkeypatch.setenv("GEPP_UMBRAL_CONFIANZA", "0.5")
    detector = _fabrica_detector()
    assert isinstance(detector(), Falso) and detector() is detector()  # uno para todos los videos
    assert construidos == [{"pesos": modelo, "variante": "small", "umbral": 0.5}]

    monkeypatch.delenv("GEPP_MODELO_VARIANTE")
    construidos.clear()
    _fabrica_detector()
    assert construidos[0]["variante"] == "nano"


@pytest.mark.usefixtures("modelo")
def test_un_motor_o_una_variante_desconocidos_detienen(monkeypatch: pytest.MonkeyPatch) -> None:
    from gepp_worker.__main__ import _fabrica_detector

    monkeypatch.setenv("GEPP_MODELO_MOTOR", "tensorrt")
    with pytest.raises(SystemExit, match="GEPP_MODELO_MOTOR"):
        _fabrica_detector()
    monkeypatch.setenv("GEPP_MODELO_MOTOR", "rfdetr")
    monkeypatch.setenv("GEPP_MODELO_VARIANTE", "enorme")
    with pytest.raises(SystemExit, match="GEPP_MODELO_VARIANTE"):
        _fabrica_detector()
