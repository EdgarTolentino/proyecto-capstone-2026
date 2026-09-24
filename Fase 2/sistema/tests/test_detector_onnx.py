"""Detector ONNX (PT-08) sobre un modelo mínimo con las salidas de RF-DETR.

El modelo se arma aquí con `onnx.helper`: devuelve siempre las mismas consultas, así que se
sabe exactamente qué tiene que salir. Eso prueba el adaptador (nombres de salidas, sigmoide,
columna "sin objeto", mapa de clases, recorte a la imagen) sin pesos reales, y corre en CI.
El modelo real se prueba en la máquina con GPU (`test_detector_rfdetr.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import onnx
import pytest
from gepp_core import ClaseDetectada
from gepp_vision import Detector
from gepp_vision.detectores import DetectorOnnx
from gepp_vision.detectores.rfdetr_comun import DESVIACION, MEDIA, MapaDeClases, preprocesar
from onnx import TensorProto, helper, numpy_helper

from .conftest import T0
from .contrato_detector import IMAGEN, ContratoDetector

LADO = 64
#: (cx, cy, w, h) normalizados y logits por clase; la última columna es "sin objeto".
#: Columnas: 0 fondo · 1 persona · 2 casco · 3 otra (fuera del mapa) · 4 sin objeto.
CONSULTAS = [
    ([0.46, 0.50, 0.12, 0.60], [-9, 3.0, -9, -9, -9]),  # persona 0,95
    ([0.46, 0.24, 0.04, 0.06], [-9, -9, 2.0, -9, -9]),  # casco 0,88
    ([0.20, 0.20, 0.10, 0.10], [-9, -9, -9, 5.0, -9]),  # clase 3: no está en el mapa
    ([0.80, 0.50, 0.10, 0.50], [-9, -3.0, -9, -9, -9]),  # persona 0,05: bajo el umbral
    ([0.98, 0.50, 0.10, 0.40], [-9, 2.0, -9, -9, -9]),  # persona en el borde: se recorta
    # "Sin objeto" alto no cuenta: RF-DETR la descarta antes de la sigmoide. Persona 0,73.
    ([0.30, 0.50, 0.10, 0.50], [-9, 1.0, -9, -9, 6.0]),
    # Persona 0,30: bajo el 0,45 de la regla, pero sale: ByteTrack la usa para no perderla.
    ([0.60, 0.50, 0.10, 0.50], [-9, -0.847, -9, -9, -9]),
    # Una consulta que supera el umbral en dos clases da las dos (top-k de RF-DETR), y una
    # clase fuera del mapa más probable no tapa a la mapeada.
    ([0.70, 0.50, 0.10, 0.50], [-9, 2.0, 1.0, 4.0, -9]),
]


def escribir_modelo(ruta: Path, *, nombres: tuple[str, str] = ("dets", "labels")) -> Path:
    cajas = np.array([[c for c, _ in CONSULTAS]], dtype=np.float32)
    logits = np.array([[lg for _, lg in CONSULTAS]], dtype=np.float32)
    nodos = [
        helper.make_node("Constant", [], ["c"], value=numpy_helper.from_array(cajas)),
        helper.make_node("Constant", [], ["l"], value=numpy_helper.from_array(logits)),
        helper.make_node("Identity", ["c"], [nombres[0]]),
        helper.make_node("Identity", ["l"], [nombres[1]]),
    ]
    grafo = helper.make_graph(
        nodos,
        "rfdetr_simulado",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, LADO, LADO])],
        # `labels` primero: el adaptador tiene que buscar por nombre, no por posición.
        [
            helper.make_tensor_value_info(nombres[1], TensorProto.FLOAT, list(logits.shape)),
            helper.make_tensor_value_info(nombres[0], TensorProto.FLOAT, list(cajas.shape)),
        ],
    )
    modelo = helper.make_model(grafo, opset_imports=[helper.make_opsetid("", 17)])
    modelo.ir_version = 8
    onnx.save(modelo, ruta)
    mapa = {"version": "prueba-1", "clases": {"1": "persona", "2": "casco"}}
    MapaDeClases.junto_a(ruta).write_text(json.dumps(mapa), encoding="utf-8")
    return ruta


@pytest.fixture
def modelo(tmp_path: Path) -> Path:
    return escribir_modelo(tmp_path / "rfdetr-prueba.onnx")


class TestDetectorOnnx(ContratoDetector):
    @pytest.fixture
    def detector(self, modelo: Path) -> Detector:
        return DetectorOnnx(modelo)


def test_decodifica_las_salidas_de_rfdetr(modelo: Path) -> None:
    dets = DetectorOnnx(modelo).detectar(IMAGEN, cuadro_idx=7, capture_ts=T0)
    clases = [d.clase for d in dets]
    persona, casco, borde, sin_objeto_alto, debil, doble_p, doble_c = dets
    assert clases == [
        ClaseDetectada.PERSONA,
        ClaseDetectada.CASCO,
        *[ClaseDetectada.PERSONA] * 4,
        ClaseDetectada.CASCO,
    ]
    assert debil.confianza == pytest.approx(0.30, abs=1e-3)
    assert doble_p.caja == doble_c.caja
    assert persona.confianza == pytest.approx(1 / (1 + np.exp(-3.0)))
    assert (persona.caja.x1, persona.caja.y1) == pytest.approx((0.40, 0.20))
    assert (persona.caja.x2, persona.caja.y2) == pytest.approx((0.52, 0.80))
    assert casco.confianza == pytest.approx(1 / (1 + np.exp(-2.0)))
    assert borde.caja.x2 == 1.0  # 0,98 + 0,05 se sale: recortada al borde
    assert sin_objeto_alto.confianza == pytest.approx(1 / (1 + np.exp(-1.0)))


def test_el_umbral_se_puede_ajustar(modelo: Path) -> None:
    dets = DetectorOnnx(modelo, umbral=0.9).detectar(IMAGEN, cuadro_idx=0, capture_ts=T0)
    assert [d.clase for d in dets] == [ClaseDetectada.PERSONA]
    assert DetectorOnnx(modelo).detectar(IMAGEN, cuadro_idx=0, capture_ts=T0)[4].confianza < 0.45


def test_la_version_cambia_si_cambia_el_modelo(tmp_path: Path) -> None:
    a = DetectorOnnx(escribir_modelo(tmp_path / "a.onnx")).version
    assert a.startswith("onnx:prueba-1:")
    ruta_b = escribir_modelo(tmp_path / "b.onnx")
    otro = onnx.load(ruta_b)
    otro.doc_string = "reentrenado"  # otros bytes, mismo mapa
    onnx.save(otro, ruta_b)
    assert DetectorOnnx(ruta_b).version != a


def test_sin_salidas_de_rfdetr_no_arranca(tmp_path: Path) -> None:
    ruta = escribir_modelo(tmp_path / "otro.onnx", nombres=("boxes", "scores"))
    with pytest.raises(ValueError, match="'dets' y 'labels'"):
        DetectorOnnx(ruta)


def test_sin_mapa_de_clases_no_arranca(modelo: Path) -> None:
    MapaDeClases.junto_a(modelo).unlink()
    with pytest.raises(FileNotFoundError):
        DetectorOnnx(modelo)


def test_preprocesar_redimensiona_en_flotante_como_rfdetr() -> None:
    """RF-DETR redimensiona el tensor ya en flotante. Redimensionar los uint8 y convertir
    después redondea distinto y mueve la confianza hasta 0,045 (revisión del #76)."""
    rng = np.random.default_rng(1)
    imagen = rng.integers(0, 256, (37, 53, 3), dtype=np.uint8)
    rgb = imagen[..., ::-1].astype(np.float32) / 255.0
    esperado = (cv2.resize(rgb, (16, 16), interpolation=cv2.INTER_LINEAR) - MEDIA) / DESVIACION
    np.testing.assert_allclose(
        preprocesar(imagen, 16, 16)[0].transpose(1, 2, 0), esperado, atol=1e-5
    )


def test_preprocesar_pasa_de_bgr_a_rgb_y_normaliza() -> None:
    azul_bgr = np.zeros((10, 20, 3), dtype=np.uint8)
    azul_bgr[..., 0] = 255  # canal 0 de OpenCV = azul
    tensor = preprocesar(azul_bgr, 8, 8)
    assert tensor.shape == (1, 3, 8, 8) and tensor.dtype == np.float32
    rojo, _verde, azul = tensor[0, :, 0, 0]
    assert azul == pytest.approx((1 - 0.406) / 0.225)  # el azul queda en el canal 2 (RGB)
    assert rojo == pytest.approx((0 - 0.485) / 0.229)


def test_el_trabajador_elige_el_detector_por_el_entorno(
    modelo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gepp_vision.detectores import DetectorFalso
    from gepp_worker.__main__ import _fabrica_detector

    guion = Path(__file__).parent / "fixtures" / "guion_sin_casco.json"
    monkeypatch.setenv("GEPP_GUION_FALSO", str(guion))
    monkeypatch.setenv("GEPP_MODELO_RUTA", str(modelo))
    assert isinstance(_fabrica_detector()(), DetectorFalso)  # el guion manda

    monkeypatch.delenv("GEPP_GUION_FALSO")
    monkeypatch.setenv("GEPP_UMBRAL_CONFIANZA", "0.9")
    detector = _fabrica_detector()()
    assert isinstance(detector, DetectorOnnx)
    dets = detector.detectar(IMAGEN, cuadro_idx=0, capture_ts=T0)
    assert [d.clase for d in dets] == [ClaseDetectada.PERSONA]  # tomó el umbral 0,9

    monkeypatch.setenv("GEPP_UMBRAL_CONFIANZA", "0,5")  # coma decimal: mensaje claro
    with pytest.raises(SystemExit, match="GEPP_UMBRAL_CONFIANZA"):
        _fabrica_detector()

    monkeypatch.setenv("GEPP_MODELO_RUTA", str(modelo.with_name("no-existe.onnx")))
    with pytest.raises(SystemExit, match="Falta el modelo"):
        _fabrica_detector()
