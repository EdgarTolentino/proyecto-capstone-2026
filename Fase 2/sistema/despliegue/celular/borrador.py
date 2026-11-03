"""Borra los segmentos de video del celular: al vencer su plazo o al terminar su video.

    GEPP_BD_URL=... GEPP_CARPETA_GRABACION=/grabaciones python borrador.py

Cada barrido (2 s), en este orden: (1) **vencimiento, sin base**: se borra todo segmento
reconocido con más de GEPP_TTL_SEGMENTO_S (60) segundos; la base caída o trabada no puede retener
video, y el atraso es descarte (D4, condición 4); (2) **terminados**: lo que no venció se busca
por SHA-256 (`gepp_bd.repositorios.videos.por_hash`, ADR-012) y se borra si está `listo`/`error`,
con un límite duro de GEPP_CONSULTA_LIMITE_S (3) segundos: pasado, se abandona la consulta. Solo
se reconoce `camara-AAAA-MM-DD_HH-MM-SS-micros.mp4` con fecha real; lo demás se deja y se avisa
una vez. Tope de video retenido: README de `despliegue/celular/` (nominal, no una garantía).
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

TERMINADOS = ("listo", "error")
#: Un solo hilo de consulta a la vez: si uno queda trabado no se apilan más.
_consulta: threading.Thread | None = None


def reconocido(ruta: Path, prefijo: str = "camara") -> bool:
    """El nombre de `recordPath` de mediamtx.yml, solo de la ruta `prefijo` y con fecha real."""
    if not ruta.is_file():
        return False
    m = re.fullmatch(
        re.escape(prefijo) + r"-(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})-\d+\.mp4",
        ruta.name,
    )
    if m is None:
        return False
    try:
        datetime(*(int(g) for g in m.groups()[:6]))  # noqa: DTZ001 — solo valida el calendario
    except ValueError:
        return False
    return True


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        while bloque := f.read(1 << 20):
            h.update(bloque)
    return h.hexdigest()


def vencido(edad_s: float, ttl_s: float) -> bool:
    """Justo en el TTL NO vence; un instante después, sí. TTL no positivo o no finito: ValueError.

    Un TTL inválido no puede dejar de borrar en silencio: el proceso cae a la vista.
    """
    if not math.isfinite(ttl_s) or ttl_s <= 0:
        raise ValueError(f"TTL inválido: {ttl_s!r}")
    if math.isnan(edad_s):
        raise ValueError("edad inválida: NaN")
    return edad_s > ttl_s


def con_limite[T](fn: Callable[[], T], limite_s: float) -> T:
    """Corre `fn` en un hilo y espera como mucho `limite_s`; si no responde, TimeoutError.

    El hilo abandonado es daemon y sigue vivo hasta que su llamada vuelva: mientras tanto no se
    lanza otra consulta (TimeoutError inmediato), para que una base trabada no acumule hilos.
    """
    global _consulta
    if _consulta is not None and _consulta.is_alive():
        raise TimeoutError("la consulta anterior sigue sin responder")
    resultado: list[T] = []
    error: list[BaseException] = []

    def correr() -> None:
        try:
            resultado.append(fn())
        except BaseException as e:  # se re-lanza en el hilo principal
            error.append(e)

    _consulta = threading.Thread(target=correr, daemon=True)
    _consulta.start()
    _consulta.join(limite_s)
    if _consulta.is_alive():
        raise TimeoutError(f"la consulta no respondió en {limite_s:g} s")
    if error:
        raise error[0]
    return resultado[0]


def barrido(
    carpeta: Path,
    estado_de: Callable[[Path], str | None],
    ttl_s: float,
    ahora: float,
    avisados: set[Path],
    *,
    limite_s: float = 3.0,
    prefijo: str = "camara",
) -> list[Path]:
    """Un barrido: primero el vencimiento (sin base) y después, con límite duro, los terminados."""
    borrados: list[Path] = []
    candidatos: list[Path] = []
    for ruta in sorted(carpeta.iterdir()):
        if ruta.is_dir():  # `en-curso`: lo cierra y limpia MediaMTX
            continue
        if not reconocido(ruta, prefijo):
            if ruta not in avisados:
                print(f"[borrador] no reconozco {ruta.name}: se deja", flush=True)
                avisados.add(ruta)
            continue
        candidatos.append(ruta)

    # Paso 1: vencimiento. NO toca la base.
    restantes: list[Path] = []
    for ruta in candidatos:
        edad = ahora - ruta.stat().st_mtime
        if vencido(edad, ttl_s):
            ruta.unlink(missing_ok=True)
            borrados.append(ruta)
            print(f"[borrador] borrado {ruta.name}: vencido ({edad:.0f} s)", flush=True)
        else:
            restantes.append(ruta)

    # Paso 2: terminados. Una falla o un límite vencido corta el paso: ya se cumplió el TTL.
    for ruta in restantes:
        try:
            estado = con_limite(lambda r=ruta: estado_de(r), limite_s)
        except Exception as e:  # la base caída o trabada no puede impedir nada más
            print(f"[borrador] sin base ({type(e).__name__}): rige solo el TTL", flush=True)
            break
        if estado in TERMINADOS:
            ruta.unlink(missing_ok=True)
            borrados.append(ruta)
            print(f"[borrador] borrado {ruta.name}: {estado}", flush=True)
    return borrados


def main() -> int:
    from gepp_bd.repositorios import videos
    from gepp_bd.sesion import crear_motor, fabrica_de_sesiones

    carpeta = Path(os.environ["GEPP_CARPETA_GRABACION"])
    ttl_s = float(os.environ.get("GEPP_TTL_SEGMENTO_S", "60"))
    limite_s = float(os.environ.get("GEPP_CONSULTA_LIMITE_S", "3"))
    prefijo = os.environ.get("GEPP_RUTA_CAMARA", "camara")
    vencido(0.0, ttl_s)  # valida el TTL al arrancar: inválido => cae, no borra a medias
    carpeta.mkdir(parents=True, exist_ok=True)
    fabrica = fabrica_de_sesiones(crear_motor())
    hashes: dict[tuple[str, int, int], str] = {}
    avisados: set[Path] = set()

    def estado_de(ruta: Path) -> str | None:
        st = ruta.stat()
        clave = (ruta.name, st.st_size, st.st_mtime_ns)
        if clave not in hashes:
            hashes[clave] = sha256(ruta)
        with fabrica() as s:
            v = videos.por_hash(s, hashes[clave])
        return v.estado if v else None

    print(
        f"[borrador] vigilando {carpeta} (TTL {ttl_s:g} s, consulta ≤ {limite_s:g} s)", flush=True
    )
    while True:
        barrido(
            carpeta, estado_de, ttl_s, time.time(), avisados, limite_s=limite_s, prefijo=prefijo
        )
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
