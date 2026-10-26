"""`python -m gepp_worker`: vigilante y trabajador en procesos separados (ADR-009).

En procesos separados para que un detector lento no detenga la captura: el vigilante sigue
encolando mientras el trabajador procesa. Se comunican solo por Redis.

Configuración desde el entorno (ver `.env.example`):

    GEPP_BD_URL · GEPP_REDIS_URL · GEPP_CARPETA_VIGILADA · GEPP_CARPETA_EVIDENCIA
    GEPP_FPS_OBJETIVO · GEPP_FUENTE_ID (fuente a la que pertenece la carpeta, 1 por defecto)
    GEPP_CARPETA_ENTRADA   opcional: carpeta de los videos que se piden desde la web. Sin ella el
                           trabajador no atiende pedidos. Debe existir, no estar bajo /mnt/ ni
                           coincidir o anidarse con GEPP_CARPETA_VIGILADA
    GEPP_GUION_FALSO   ruta a un guion JSON: usa el detector falso (demostración sin modelo)
    GEPP_MODELO_RUTA   si no hay guion: el modelo, con su `.clases.json` al lado
    GEPP_MODELO_MOTOR  `onnx` (por defecto: el `.onnx` en CPU) o `rfdetr` (el `.pth` en la GPU;
                       requiere `make setup-gpu`). Con `rfdetr`, GEPP_MODELO_VARIANTE (`nano`
                       por defecto, `small`...)
    GEPP_UMBRAL_CONFIANZA  corte del detector (0.25 por defecto; ver `rfdetr_comun`)
    GEPP_MOSAICO_FACTOR · GEPP_MOSAICO_LADO · GEPP_MOSAICO_OBJETO_MAX_PX: cómo se parte la zona
                       `mosaico` de una cámara (2 · entrada del modelo · 100 por defecto; un LADO
                       distinto de la entrada detiene el arranque). Sin esa zona, cuadro entero
    GEPP_AVISO_CANAL + GEPP_AVISO_DESTINATARIO: si están, cada hallazgo escribe su aviso
    GEPP_MAXIMO_INTENTOS: intentos antes de dejar un video en `error` (3 por defecto)
    GEPP_VISTA_EN_VIVO=1 + GEPP_CARPETA_VIVO + GEPP_VIVO_FPS (25 por defecto): vista en
    vivo del procesamiento (apagada por defecto; ver `gepp_worker.vivo` y la excepción en
    02-privacidad-y-cumplimiento.md)

Sin `GEPP_GUION_FALSO`, el detector es RF-DETR (`docs/operacion/modelo-onnx.md`). Sin mosaico,
en el CCTV de prueba no ve ningún casco (#203): lo que se mide y se muestra corre con `rfdetr` en
la GPU y con la zona `mosaico` de la cámara. En CPU, el mosaico tarda segundos por cuadro.
"""

from __future__ import annotations

import math
import multiprocessing as mp
import os
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from gepp_vision import Detector

    from gepp_worker.cola import ColaTrabajos
    from gepp_worker.trabajador import ParametrosMosaico

VARIABLES_OBLIGATORIAS = ("GEPP_BD_URL", "GEPP_REDIS_URL", "GEPP_CARPETA_VIGILADA")


def _cola() -> ColaTrabajos:
    import redis

    from gepp_worker.cola import MAXIMO_INTENTOS, ColaTrabajos

    return ColaTrabajos(
        redis.Redis.from_url(os.environ["GEPP_REDIS_URL"]),
        maximo_intentos=int(os.environ.get("GEPP_MAXIMO_INTENTOS", MAXIMO_INTENTOS)),
    )


def _detenible() -> mp.synchronize.Event:
    parar = mp.Event()
    signal.signal(signal.SIGTERM, lambda *_: parar.set())
    signal.signal(signal.SIGINT, lambda *_: parar.set())
    return parar


def correr_vigilante() -> None:
    from gepp_worker.vigilante import Vigilante

    parar = _detenible()
    vigilante = Vigilante(
        os.environ["GEPP_CARPETA_VIGILADA"], _cola(), int(os.environ.get("GEPP_FUENTE_ID", "1"))
    )
    print(f"[vigilante] sondeando {vigilante.carpeta}", flush=True)
    vigilante.correr(seguir=lambda: not parar.is_set())


def _fabrica_detector() -> Callable[[], Detector]:
    """El guion simulado si hay uno (demostración, CI); si no, el modelo en el motor elegido."""
    from gepp_vision.detectores import DetectorFalso, DetectorOnnx, Guion
    from gepp_vision.detectores.rfdetr_comun import UMBRAL_CONFIANZA

    if guion := os.environ.get("GEPP_GUION_FALSO"):
        cargado = Guion.desde_json(Path(guion))
        return lambda: DetectorFalso(cargado)
    modelo = os.environ.get("GEPP_MODELO_RUTA")
    if not modelo or not Path(modelo).is_file():
        sys.exit(f"Falta el modelo: GEPP_MODELO_RUTA={modelo!r} no existe (o use GEPP_GUION_FALSO)")
    texto = os.environ.get("GEPP_UMBRAL_CONFIANZA", str(UMBRAL_CONFIANZA))
    try:
        umbral = float(texto)
    except ValueError:
        sys.exit(f"GEPP_UMBRAL_CONFIANZA={texto!r} no es un número (use punto: 0.25)")
    motor = os.environ.get("GEPP_MODELO_MOTOR", "onnx")
    if motor == "rfdetr":
        from gepp_vision.detectores.rfdetr import VARIANTES, DetectorRFDETR

        variante = os.environ.get("GEPP_MODELO_VARIANTE", "nano")
        if variante not in VARIANTES:
            sys.exit(f"GEPP_MODELO_VARIANTE={variante!r}: use una de {sorted(VARIANTES)}")
        base: Detector = DetectorRFDETR(Path(modelo), variante=variante, umbral=umbral)
    elif motor == "onnx":
        base = DetectorOnnx(Path(modelo), umbral=umbral)
    else:
        sys.exit(f"GEPP_MODELO_MOTOR={motor!r}: use onnx o rfdetr")
    # Un solo modelo cargado para todos los videos: cargarlo cuesta segundos.
    return lambda: base


def _numero_positivo(variable: str, defecto: float, tipo: type[float] | type[int]) -> float:
    """El valor de `variable`, o `defecto` si no está o está vacía; uno inválido detiene el
    arranque."""
    texto = os.environ.get(variable)
    if not texto:
        return defecto
    try:
        valor = tipo(texto)
    except ValueError:
        sys.exit(f"{variable}={texto!r} no es un número válido (use punto: 2.5)")
    if not math.isfinite(valor) or valor <= 0:
        sys.exit(f"{variable}={texto!r} debe ser un número positivo y finito")
    return valor


def _parametros_mosaico(entrada: int | None = None) -> ParametrosMosaico:
    """Los de `GEPP_MOSAICO_*`, con los de `ParametrosMosaico` por defecto. `entrada` es el lado
    de entrada del modelo, si se sabe: es el `lado` por defecto, y uno distinto detiene el
    arranque, porque el modelo reescalaría cada mosaico sin avisar (revisión de #205)."""
    from gepp_worker.trabajador import ParametrosMosaico

    d = ParametrosMosaico()
    lado = int(_numero_positivo("GEPP_MOSAICO_LADO", entrada or d.lado, int))
    if entrada is not None and lado != entrada:
        sys.exit(f"GEPP_MOSAICO_LADO={lado} no coincide con la entrada del modelo ({entrada})")
    return ParametrosMosaico(
        factor=_numero_positivo("GEPP_MOSAICO_FACTOR", d.factor, float),
        lado=lado,
        objeto_max_px=int(_numero_positivo("GEPP_MOSAICO_OBJETO_MAX_PX", d.objeto_max_px, int)),
    )


def _carpeta_entrada() -> Path | None:
    """La carpeta de los pedidos desde la web, validada; None si no está configurada."""
    from gepp_worker.pedidos import validar_carpeta_entrada

    texto = os.environ.get("GEPP_CARPETA_ENTRADA")
    if not texto:
        return None
    try:
        return validar_carpeta_entrada(texto, os.environ["GEPP_CARPETA_VIGILADA"])
    except ValueError as e:
        sys.exit(str(e))


def _fps_vivo() -> float:
    """Cuadros por segundo de video de la vista en vivo; un valor inválido detiene el arranque."""
    from gepp_worker.vivo import fps_configurado

    try:
        return fps_configurado()
    except ValueError as e:
        sys.exit(str(e))


def correr_trabajador() -> None:
    from gepp_bd.sesion import crear_motor

    from gepp_worker.muestreo import fps_objetivo_configurado
    from gepp_worker.trabajador import Aviso, Configuracion, Trabajador
    from gepp_worker.vivo import carpeta_configurada as carpeta_vivo_configurada
    from gepp_worker.vivo import carpeta_de_residuos

    carpeta_entrada = _carpeta_entrada()  # antes del modelo: un error de carpeta se ve primero
    fabrica_detector = _fabrica_detector()
    canal, destino = os.environ.get("GEPP_AVISO_CANAL"), os.environ.get("GEPP_AVISO_DESTINATARIO")
    config = Configuracion(
        carpeta_evidencia=Path(os.environ.get("GEPP_CARPETA_EVIDENCIA", "/datos/evidencia")),
        fps_objetivo=fps_objetivo_configurado(),
        aviso=Aviso(canal, destino) if canal and destino else None,
        carpeta_entrada=carpeta_entrada,
        carpeta_vivo=carpeta_vivo_configurada(),
        vivo_fps=_fps_vivo(),
        carpeta_vivo_residuos=carpeta_de_residuos(),
        # El detector falso no tiene entrada fija: ahí manda GEPP_MOSAICO_LADO.
        mosaico=_parametros_mosaico(getattr(fabrica_detector(), "lado_entrada", None)),
    )
    parar = _detenible()
    trabajador = Trabajador(crear_motor(), _cola(), fabrica_detector, config)
    print("[trabajador] esperando videos", flush=True)
    trabajador.correr(seguir=lambda: not parar.is_set())


def main() -> int:
    faltan = [v for v in VARIABLES_OBLIGATORIAS if not os.environ.get(v)]
    if faltan:
        print(f"Faltan variables de entorno: {', '.join(faltan)}", file=sys.stderr)
        return 2
    procesos = [
        mp.Process(target=correr_vigilante, name="vigilante"),
        mp.Process(target=correr_trabajador, name="trabajador"),
    ]
    for p in procesos:
        p.start()

    def reenviar(*_: object) -> None:
        # Cada hijo termina su vuelta actual al recibir SIGTERM: ningún video queda a medias
        # en la base (la transacción del resultado es todo o nada).
        for p in procesos:
            if p.is_alive():
                p.terminate()

    signal.signal(signal.SIGTERM, reenviar)
    signal.signal(signal.SIGINT, reenviar)
    for p in procesos:
        p.join()
    return max((p.exitcode or 0) for p in procesos)


if __name__ == "__main__":
    raise SystemExit(main())
