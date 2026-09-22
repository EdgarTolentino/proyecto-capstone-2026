"""Cobertura: **el hueco tiene que verse** (contrato, esquema `Cobertura`).

Si una cámara no está entregando video, el prevencionista debe saberlo: es la mitigación del
falso negativo con complacencia ("no hay hallazgos" ≠ "no hay incumplimientos").
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from gepp_bd.modelos import Fuente, Video
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gepp_api.servicios.hallazgos import iso

#: Una fuente activa sin un video `listo` creado en esta ventana se muestra sin cobertura.
VENTANA_SIN_INGESTA = timedelta(hours=24)


def cobertura(bd: Session, tz: ZoneInfo) -> dict[str, Any]:
    fuentes = list(bd.execute(select(Fuente).order_by(Fuente.id)).scalars())
    ultimo = (
        select(Video.fuente_id, Video.estado, Video.creado_en)
        .distinct(Video.fuente_id)
        .order_by(Video.fuente_id, Video.creado_en.desc(), Video.id.desc())
        .subquery()
    )
    ultimos = {f.fuente_id: f for f in bd.execute(select(ultimo)).all()}
    ultimo_listo = dict(
        bd.execute(
            select(Video.fuente_id, func.max(Video.creado_en))
            .where(Video.estado == "listo")
            .group_by(Video.fuente_id)
        )
        .tuples()
        .all()
    )
    ahora = bd.scalar(select(func.now()))  # reloj de la BASE: esto es estado del servicio,
    # no instante de captura, y así la API no lee el reloj del proceso (ADR-005).
    sin_cobertura = []
    for f in fuentes:
        if not f.activa:
            continue
        referencia = {"id": f.id, "nombre": f.nombre}
        u = ultimos.get(f.id)
        if u is not None and u.estado == "error":
            sin_cobertura.append(
                {"fuente": referencia, "motivo": "error", "desde": iso(u.creado_en, tz)}
            )
            continue
        listo = ultimo_listo.get(f.id)
        if listo is None or (ahora is not None and ahora - listo > VENTANA_SIN_INGESTA):
            entrada: dict[str, Any] = {"fuente": referencia, "motivo": "sin_ingesta"}
            if listo is not None:
                entrada["desde"] = iso(listo, tz)
            sin_cobertura.append(entrada)
    return {
        "fuentes_activas": sum(1 for f in fuentes if f.activa),
        "fuentes_totales": len(fuentes),
        "sin_cobertura": sin_cobertura,
    }
