"""Comprueba el flujo que usa React contra el servidor simulado real."""

import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx


def test_mock_bandeja_evidencia_y_triage():
    ruta = Path(__file__).parents[1] / "apps" / "mock" / "server.py"
    spec = importlib.util.spec_from_file_location("mock_prueba", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    # El puerto cero elige uno libre y no toca el mock que está usando la persona.
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), modulo.MockHandler)
    hilo = Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{servidor.server_port}") as cliente:
            assert cliente.get("/health").status_code == 200
            assert cliente.get("/api/v1/hallazgos").status_code == 401
            cliente.headers["Authorization"] = "Bearer demo"
            lista = cliente.get("/api/v1/hallazgos").json()
            assert len(lista["items"]) == 16
            criticos = cliente.get("/api/v1/hallazgos?severidad=4").json()
            assert criticos["items"]
            assert all(item["severidad"] == 4 for item in criticos["items"])
            detalle = cliente.get("/api/v1/hallazgos/2418").json()
            assert detalle["por_que_se_disparo"]["regla_nombre"]
            assert all(item["anonimizado"] for item in detalle["evidencias"])
            assert cliente.get("/api/v1/evidencias/24181").status_code == 200
            respuesta = cliente.post("/api/v1/hallazgos/2418/triage", json={"estado": "confirmado"})
            assert respuesta.status_code == 200
            assert cliente.get("/api/v1/hallazgos/2418").json()["estado"] == "confirmado"
            lote = cliente.post(
                "/api/v1/hallazgos/triage-lote",
                json={
                    "ids": [2417, 2416],
                    "decision": {"estado": "falso_positivo", "motivo": "Prueba"},
                },
            )
            assert lote.status_code == 200
            assert lote.json()["aplicados"] == 2
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=2)
