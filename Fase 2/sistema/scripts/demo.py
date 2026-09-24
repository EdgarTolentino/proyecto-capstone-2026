"""Demostración de punta a punta: un video entra y salen hallazgos con evidencia.

    make demo VIDEO=~/videos/cam03.mp4 [GUION=demo/guion_cam03.json]    detector simulado
    make demo VIDEO=~/videos/obra.mp4 MODELO=modelos/rfdetr-nano.onnx    modelo real (ONNX)

Usa el sistema real —vigilante, cola Redis, trabajador, reglas en segundos, PostgreSQL,
evidencia pixelada y aviso en el outbox—. Sin `MODELO`, el detector es simulado: sus
detecciones salen de un guion JSON escrito a mano mirando el video
(`gepp_vision.detectores.falso`), y hay que decirlo así al mostrarlo. Con `MODELO`, es
RF-DETR exportado a ONNX (`docs/operacion/modelo-onnx.md`).

Trabaja en una base aparte (`<base>_demo`) que se recrea en cada corrida: no toca los datos de
desarrollo. Necesita `make up` (PostgreSQL y Redis).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from gepp_bd.migrar import subir
from gepp_bd.semilla import cargar, leer
from gepp_bd.sesion import transaccion
from sqlalchemy import create_engine, make_url, text

RAIZ = Path(__file__).resolve().parents[1]
URL_POR_DEFECTO = "postgresql+psycopg://gepp:gepp_dev@localhost:5432/gepp"


def recrear_base(url_base: str) -> str:
    url = make_url(url_base)
    demo = url.set(database=f"{url.database}_demo")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{demo.database}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{demo.database}"'))
    admin.dispose()
    texto = demo.render_as_string(hide_password=False)
    subir(texto)
    with transaccion(create_engine(texto)) as s:
        cargar(s, leer(RAIZ / "perfiles" / "construccion.yaml"))
    return texto


def esperar_listo(url: str, segundos: float) -> str:
    motor = create_engine(url)
    limite = time.monotonic() + segundos
    estado = "sin registrar"
    while time.monotonic() < limite:
        with motor.connect() as c:
            fila = c.execute(text("SELECT estado FROM video ORDER BY id LIMIT 1")).first()
        if fila is not None:
            estado = fila.estado
            if estado in ("listo", "error"):
                break
        time.sleep(0.5)
    motor.dispose()
    return estado


def resumen(url: str) -> None:
    consultas = {
        "Video": "SELECT estado, intentos, error_motivo, origen_capture_ts AS reloj,"
        " cuadros_analizados AS cuadros, proceso_ms FROM video",
        "Detecciones": "SELECT count(*) AS detecciones, count(DISTINCT track_id) AS personas"
        " FROM deteccion",
        "Hallazgos": "SELECT h.id, h.track_id AS persona, array_to_string(h.epp_faltante, ', ')"
        " AS falta, h.severidad, round(h.duracion_s::numeric, 1) AS segundos, r.nombre AS regla,"
        " h.estado FROM hallazgo h JOIN regla r ON r.id = h.regla_id ORDER BY h.id",
        "Evidencia": "SELECT hallazgo_id, ruta, purgar_el FROM evidencia ORDER BY id",
        "Avisos (outbox)": "SELECT hallazgo_id, canal, destinatario, estado FROM notificacion",
    }
    motor = create_engine(url)
    with motor.connect() as c:
        for titulo, sql in consultas.items():
            resultado = c.execute(text(sql))
            filas = resultado.all()
            print(f"\n== {titulo} ({len(filas)})")
            print("  " + " | ".join(resultado.keys()))
            for f in filas:
                print("  " + " | ".join(str(v) for v in f))
    motor.dispose()


def entorno_del_trabajador(
    base: dict[str, str],
    *,
    url: str,
    entrada: Path,
    evidencia: Path,
    fuente: int,
    guion: Path,
    modelo: Path | None,
) -> dict[str, str]:
    """El entorno de `python -m gepp_worker`. Con modelo, SIN `GEPP_GUION_FALSO`: el Makefile
    carga el .env, que puede traerlo, y el trabajador usaría el guion sin avisar."""
    entorno = base | {
        "GEPP_BD_URL": url,
        "GEPP_REDIS_URL": base.get("GEPP_REDIS_URL", "redis://localhost:6379/15"),
        "GEPP_CARPETA_VIGILADA": str(entrada),
        "GEPP_CARPETA_EVIDENCIA": str(evidencia),
        "GEPP_FUENTE_ID": str(fuente),
        "GEPP_AVISO_CANAL": "telegram",
        # Con el chat real en el .env, el aviso llega al teléfono al correr `make despachador`.
        "GEPP_AVISO_DESTINATARIO": base.get("GEPP_AVISO_DESTINATARIO") or "prevencionista-demo",
    }
    if modelo is None:
        entorno["GEPP_GUION_FALSO"] = str(guion.resolve())
        entorno.pop("GEPP_MODELO_RUTA", None)
    else:
        entorno.pop("GEPP_GUION_FALSO", None)
        entorno["GEPP_MODELO_RUTA"] = str(modelo.resolve())
    return entorno


def validar_modelo(modelo: Path) -> None:
    from gepp_vision.detectores.rfdetr_comun import MapaDeClases

    if not modelo.is_file():
        sys.exit(f"no existe el modelo: {modelo}")
    clases = MapaDeClases.junto_a(modelo)
    if not clases.is_file():
        sys.exit(
            f"falta el mapa de clases junto al modelo: {clases} (docs/operacion/modelo-onnx.md)"
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("video", type=Path)
    p.add_argument("--guion", type=Path, default=RAIZ / "demo" / "guion_cam03.json")
    p.add_argument("--modelo", type=Path, help="RF-DETR en ONNX: reemplaza al detector simulado")
    p.add_argument(
        "--espera",
        type=float,
        help="segundos máximos de espera (120 con guion; 900 con modelo, que analiza de verdad)",
    )
    p.add_argument(
        "--fuente",
        type=int,
        default=1,
        help="1 = acceso (regla alta: va al resumen) · 2 = obra gruesa (crítica: avisa ya)",
    )
    args = p.parse_args(argv)
    if not args.video.is_file():
        sys.exit(f"no existe el video: {args.video}")
    if args.modelo is not None:
        validar_modelo(args.modelo)
    espera = args.espera or (900.0 if args.modelo else 120.0)

    url = recrear_base(os.environ.get("GEPP_BD_URL", URL_POR_DEFECTO))
    trabajo = Path(tempfile.mkdtemp(prefix="gepp-demo-"))
    entrada, evidencia = trabajo / "entrada", trabajo / "evidencia"
    entrada.mkdir()
    entorno = entorno_del_trabajador(
        dict(os.environ),
        url=url,
        entrada=entrada,
        evidencia=evidencia,
        fuente=args.fuente,
        guion=args.guion,
        modelo=args.modelo,
    )
    import redis  # solo para vaciar la base de Redis de la demo

    redis.Redis.from_url(entorno["GEPP_REDIS_URL"]).flushdb()
    if args.modelo is None:
        print(f"Detector SIMULADO con el guion {args.guion.name} · base {make_url(url).database}")
    else:
        print(f"Detector REAL: {args.modelo.name} (ONNX) · base {make_url(url).database}")
    proceso = subprocess.Popen([sys.executable, "-m", "gepp_worker"], env=entorno)
    try:
        time.sleep(2)
        shutil.copy2(args.video, entrada / args.video.name)
        estado = esperar_listo(url, espera)
        shutil.copy2(args.video, entrada / f"copia_{args.video.name}")
        time.sleep(4)  # la copia tiene que llegar y no duplicar nada
    finally:
        proceso.terminate()
        proceso.wait(timeout=15)
    print(f"\nEstado del video: {estado}")
    resumen(url)
    print(f"\nRecortes de evidencia en: {evidencia}")
    return 0 if estado == "listo" else 1


if __name__ == "__main__":
    raise SystemExit(main())
