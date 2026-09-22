"""H2 (#33): el video entra por un extremo y el hallazgo sale por la API por el otro.

Recorrido real completo salvo el modelo, que es el detector falso: carpeta vigilada ->
vigilante -> cola -> trabajador a 5 fps -> PostgreSQL -> API -> bandeja y visor. Sin GPU.
"""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient
from gepp_api.app import crear_app

from ..bd.test_ingesta import entorno, escribir_video_ruido  # noqa: F401 — fixture compartido
from .conftest import Cliente

pytestmark = pytest.mark.integration


def test_del_video_a_la_bandeja_y_el_visor(entorno) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    motor, entrada, _, vigilante, trabajador, tmp = entorno

    # 1-2. Se copia un .mp4; el vigilante lo encola al verlo estable y el trabajador lo procesa.
    shutil.copy(escribir_video_ruido(tmp / "camara.mp4"), entrada / "camara.mp4")
    assert vigilante.sondear() == []
    (trabajo,) = vigilante.sondear()
    resultado = trabajador.atender_uno()
    assert resultado is not None and resultado.hallazgos == 1

    with TestClient(crear_app(motor=motor)) as http:
        api = Cliente(http)
        # 3. La cola de ingesta lo muestra listo, con su reloj de origen visible.
        (video,) = api.llamar("listarVideos", "GET", "/videos")["items"]
        assert (video["estado"], video["origen_capture_ts"], video["hallazgos_generados"]) == (
            "listo",
            "mtime",
            1,
        )
        assert video["hash_abreviado"] == trabajo.hash_sha256[:8]

        # 4. La bandeja lo lista...
        pagina = api.llamar("listarHallazgos", "GET", "/hallazgos")
        (h,) = pagina["items"]
        assert pagina["contadores"]["por_revisar"] == 1
        assert h["epp_faltante"] == ["casco"]
        # Terminado significa (#33): cuadros_confirmados ~ duracion_s * 5 en hallazgos reales.
        assert abs(h["cuadros_confirmados"] - h["duracion_s"] * 5) <= 5

        # ... el visor explica por qué se disparó y la evidencia se sirve difuminada.
        d = api.llamar("obtenerHallazgo", "GET", f"/hallazgos/{h['id']}")
        assert d["por_que_se_disparo"]["regla_nombre"] == "Casco y chaleco en acceso"
        assert d["tecnicos"]["video_archivo"] == "camara.mp4"
        (ev,) = d["evidencias"]
        imagen = http.get(ev["url"], headers={"Authorization": "Bearer demo"})
        assert imagen.status_code == 200 and imagen.content[:2] == b"\xff\xd8"  # JPEG

        # 5. Y el prevencionista lo resuelve, con la decisión en la auditoría.
        api.llamar(
            "triarHallazgo", "POST", f"/hallazgos/{h['id']}/triage", json={"estado": "confirmado"}
        )
        assert api.llamar("obtenerEstado", "GET", "/estado")["pendientes_por_revisar"] == 0
