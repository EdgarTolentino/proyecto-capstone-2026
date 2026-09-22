"""Implementaciones del puerto `Detector`.

`falso` corre en CI y en los portátiles sin modelo. `rfdetr` (PyTorch, GPU) y `onnx`
(ONNX Runtime, CPU) llegan con el primer modelo (PT-08) y deben pasar la misma batería
de pruebas: `tests/contrato_detector.py`.
"""

from gepp_vision.detectores.falso import DetectorFalso, Guion, Segmento

__all__ = ["DetectorFalso", "Guion", "Segmento"]
