"""Implementaciones del puerto `Detector`.

`falso` corre en CI y en los portátiles sin modelo. `onnx` es RF-DETR exportado, sobre ONNX
Runtime en CPU. `rfdetr` es RF-DETR con PyTorch en la máquina con GPU; necesita el extra
`gpu` y por eso no se importa aquí (`from gepp_vision.detectores.rfdetr import ...`). Los
tres pasan la misma batería: `tests/contrato_detector.py`.
"""

from gepp_vision.detectores.falso import DetectorFalso, Guion, Segmento
from gepp_vision.detectores.onnx import DetectorOnnx

__all__ = ["DetectorFalso", "DetectorOnnx", "Guion", "Segmento"]
