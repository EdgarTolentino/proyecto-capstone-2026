"""Implementaciones del puerto `Seguidor`. `SeguidorByteTrack` es el de producción;
`SeguidorIoU` queda como referencia simple y pasa la misma batería."""

from gepp_vision.seguimiento.bytetrack import SeguidorByteTrack
from gepp_vision.seguimiento.iou import SeguidorIoU

__all__ = ["SeguidorByteTrack", "SeguidorIoU"]
