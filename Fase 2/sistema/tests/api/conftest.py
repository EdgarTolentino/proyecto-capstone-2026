"""API real contra PostgreSQL real, con datos sembrados por los mismos repositorios del sistema."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from gepp_api.app import crear_app
from gepp_bd import transaccion
from gepp_bd.modelos import Evidencia
from gepp_bd.repositorios import detecciones, hallazgos, reglas, videos
from gepp_bd.semilla import cargar, leer
from gepp_core import agregar
from sqlalchemy import Engine

from ..bd.conftest import bd, motor, url_bd  # noqa: F401 — fixtures compartidos
from ..conftest import T0, cuadro
from .contrato import validar

PERFIL = Path(__file__).resolve().parents[2] / "perfiles" / "construccion.yaml"
DEMO = {"Authorization": "Bearer demo"}


class Cliente:
    """TestClient que valida cada respuesta JSON contra el contrato."""

    def __init__(self, cliente: TestClient) -> None:
        self.http = cliente

    def llamar(
        self, operation_id: str, metodo: str, ruta: str, *, esperado: int = 200, **kw: Any
    ) -> Any:
        kw.setdefault("headers", DEMO)
        r = self.http.request(metodo, "/api/v1" + ruta, **kw)
        assert r.status_code == esperado, f"{metodo} {ruta}: {r.status_code} {r.text[:300]}"
        if r.headers.get("content-type", "").startswith("application/json"):
            validar(operation_id, r.status_code, r.json())
            return r.json()
        return r


def _sembrar_video(s: Any, tmp: Path, *, hash_: str, t0_s: float, sin_casco: bool) -> list[int]:
    video, _ = videos.registrar(
        s,
        videos.NuevoVideo(
            fuente_id=1,
            ruta=f"/datos/{hash_[:6]}.mp4",
            hash_sha256=hash_,
            bytes=10,
            capture_ts_inicio=T0 + timedelta(seconds=t0_s),
            origen_capture_ts="metadatos",
            duracion_s=8.0,
            fps_declarado=24.0,
        ),
    )
    videos.cambiar_estado(s, video.id, "listo", cuadros_analizados=40, proceso_ms=900)
    cuadros = [cuadro(t=t0_s + i / 5, idx=i, con_casco=not sin_casco) for i in range(40)]
    detecciones.insertar(s, video.id, (d for c in cuadros for d in c), modelo_version="falso-0")
    regla = reglas.a_dominio(reglas.activas(s, area_id=1)[0])
    ids = []
    for h in agregar(regla, cuadros):
        fila = hallazgos.guardar(
            s, h, hallazgos.Contexto(fuente_id=1, area_id=1, video_id=video.id)
        )
        imagen = tmp / f"h{fila.id}.jpg"
        imagen.write_bytes(b"\xff\xd8\xff\xe0 recorte-sintetico")
        s.add(
            Evidencia(
                hallazgo_id=fila.id,
                ruta=str(imagen),
                hash_sha256="b" * 64,
                cuadro_idx=10,
                capture_ts=h.ts_inicio,
                purgar_el=date(2026, 10, 2),
            )
        )
        ids.append(fila.id)
    return ids


@pytest.fixture
def datos(bd: Engine, tmp_path: Path) -> dict[str, Any]:  # noqa: F811
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
        a = _sembrar_video(s, tmp_path, hash_="a" * 64, t0_s=0, sin_casco=True)
        b = _sembrar_video(s, tmp_path, hash_="c" * 64, t0_s=3600, sin_casco=True)
        _sembrar_video(s, tmp_path, hash_="d" * 64, t0_s=7200, sin_casco=False)
    return {"hallazgos": a + b}


@pytest.fixture
def api(bd: Engine, datos: dict[str, Any]) -> Iterator[Cliente]:  # noqa: F811
    del datos
    with TestClient(crear_app(motor=bd)) as c:
        yield Cliente(c)
