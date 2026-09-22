"""Turnos de la faena. Viven aquí para que la API y el trabajador usen los mismos.

Dos turnos de 12 h, el mismo largo que el presupuesto de avisos (ADR-008). Provisional hasta
que el turno sea un dato de la faena en la base.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class Turno:
    codigo: str
    desde: time
    hasta: time

    @property
    def etiqueta(self) -> str:
        return f"Turno {self.codigo} ({self.desde:%H:%M}-{self.hasta:%H:%M})"

    def contiene(self, hora: time) -> bool:
        if self.desde <= self.hasta:
            return self.desde <= hora < self.hasta
        return hora >= self.desde or hora < self.hasta  # cruza la medianoche


TURNOS = (Turno("A", time(8), time(20)), Turno("B", time(20), time(8)))


def turno(codigo: str) -> Turno | None:
    return next((t for t in TURNOS if t.codigo == codigo), None)
