"""Vigilante de la carpeta de entrada, por sondeo (ADR-005, ADR-009).

Por sondeo y no con inotify: en WSL2 inotify no entrega eventos sobre `/mnt/` y falla en
silencio. Por eso además la carpeta bajo `/mnt/` se rechaza al construir el vigilante.

Un archivo se encola cuando está **estable**: su tamaño y su fecha de modificación no
cambiaron entre dos sondeos consecutivos. Así un video a medio copiar no se lee. Solo se
miran las extensiones de video: un `clip.mp4.part` (la convención de "todavía copiando") tiene
extensión `.part` y queda fuera hasta que se renombra. Los ocultos se ignoran siempre.

La estabilidad se mide comparando sondeos, no leyendo el reloj: el vigilante no fecha nada.
`time.monotonic` y `time.sleep` solo marcan el ritmo del bucle.

La clave de idempotencia es el SHA-256 del contenido: el mismo video copiado dos veces, con
el mismo nombre o con otro, es un solo trabajo.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gepp_worker.cola import ColaTrabajos, Trabajo
from gepp_worker.fuente_archivo import validar_ruta

EXTENSIONES_VIDEO = frozenset({".mp4", ".mov", ".mkv", ".avi"})
BLOQUE_HASH = 1024 * 1024


def sha256_de_archivo(ruta: Path, bloque: int = BLOQUE_HASH) -> str:
    """Hash por bloques: un video de varios GB no entra entero en memoria."""
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        while trozo := f.read(bloque):
            h.update(trozo)
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class _Firma:
    bytes: int
    mtime_ns: int


def _es_candidato(ruta: Path) -> bool:
    return (
        ruta.is_file()
        and not ruta.name.startswith(".")
        and ruta.suffix.lower() in EXTENSIONES_VIDEO
    )


class Vigilante:
    """Sondea una carpeta y encola los videos estables de UNA fuente."""

    def __init__(self, carpeta: Path | str, cola: ColaTrabajos, fuente_id: int) -> None:
        self._carpeta = validar_ruta(Path(carpeta))
        self._cola = cola
        self._fuente_id = fuente_id
        self._anterior: dict[Path, _Firma] = {}
        self._encolados: dict[Path, _Firma] = {}

    @property
    def carpeta(self) -> Path:
        return self._carpeta

    def sondear(self) -> list[Trabajo]:
        """Un sondeo. Devuelve los trabajos que encoló en esta pasada."""
        actual: dict[Path, _Firma] = {}
        for ruta in sorted(self._carpeta.iterdir()):
            if not _es_candidato(ruta):
                continue
            estado = ruta.stat()
            actual[ruta] = _Firma(estado.st_size, estado.st_mtime_ns)

        nuevos: list[Trabajo] = []
        for ruta, firma in actual.items():
            estable = firma.bytes > 0 and self._anterior.get(ruta) == firma
            if not estable or self._encolados.get(ruta) == firma:
                continue
            trabajo = Trabajo(
                ruta=str(ruta),
                hash_sha256=sha256_de_archivo(ruta),
                bytes=firma.bytes,
                fuente_id=self._fuente_id,
            )
            self._encolados[ruta] = firma
            if self._cola.encolar(trabajo):
                nuevos.append(trabajo)
        self._anterior = actual
        self._encolados = {r: f for r, f in self._encolados.items() if r in actual}
        return nuevos

    def correr(self, intervalo_s: float = 2.0, seguir: Callable[[], bool] = lambda: True) -> None:
        """Bucle de sondeo. `seguir` permite detenerlo desde fuera (señal o prueba)."""
        while seguir():
            inicio = time.monotonic()
            self.sondear()
            time.sleep(max(0.0, intervalo_s - (time.monotonic() - inicio)))
