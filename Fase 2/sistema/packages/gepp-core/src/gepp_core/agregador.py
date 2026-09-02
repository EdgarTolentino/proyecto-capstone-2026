"""De detecciones sueltas a hallazgos con duración.

Es el corazón del sistema (ADR-004). Una hora de video a 5 fps son 18.000 cuadros;
sin esta pieza, un turno produce cientos de miles de filas y otras tantas alertas.
Con ella produce una docena de hallazgos.

La máquina de estados por cada persona seguida:

    LIMPIO ──falta EPP──▶ CANDIDATO ──persiste ≥ confirmacion_segundos──▶ ABIERTO
       ▲                      │                                             │
       └──deja de faltar──────┘                    sin faltar durante       │
                                                   ≥ cierre_segundos ───────┘
                                                            │
                                                            ▼
                                                        HALLAZGO

Las dos histéresis existen por razones distintas y las dos son necesarias:

- `confirmacion_segundos` evita que un cuadro mal detectado —un casco tapado medio
  segundo por un brazo— genere una alerta.
- `cierre_segundos` evita que una oclusión breve parta un incumplimiento continuo en
  tres hallazgos distintos, que es lo que infla el conteo y arruina la analítica.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime

from gepp_core.asociacion import epp_faltante
from gepp_core.dominio import ClaseDetectada, Deteccion, Hallazgo, Regla, TipoEPP


@dataclass(slots=True)
class _Racha:
    """Estado vivo de un track que está incumpliendo."""

    epp_faltante: set[TipoEPP]
    ts_inicio: datetime
    ts_ultimo_incumplimiento: datetime
    cuadros: int = 1
    confianzas: list[float] = field(default_factory=list)
    cuadros_evidencia: list[int] = field(default_factory=list)
    confirmado: bool = False

    @property
    def duracion(self) -> float:
        return (self.ts_ultimo_incumplimiento - self.ts_inicio).total_seconds()


class AgregadorDeHallazgos:
    """Convierte un flujo de cuadros en hallazgos.

    Se alimenta cuadro a cuadro con `procesar_cuadro` y emite hallazgos a medida que
    se cierran. `cerrar` vacía el estado al terminar la fuente.

    Funciona igual para un archivo completo (v1) que para un flujo en vivo (v2): el
    agregador no sabe de dónde vienen los cuadros, solo que traen `capture_ts`.
    """

    def __init__(self, regla: Regla) -> None:
        self._regla = regla
        self._rachas: dict[int, _Racha] = {}

    # ── API pública ────────────────────────────────────────────────────────────

    def procesar_cuadro(self, detecciones: list[Deteccion]) -> list[Hallazgo]:
        """Procesa las detecciones de UN cuadro y devuelve los hallazgos que cierran."""
        personas = [
            d
            for d in detecciones
            if d.clase is ClaseDetectada.PERSONA
            and d.track_id is not None
            and d.confianza >= self._regla.confianza_minima
        ]
        vistos: set[int] = set()
        cerrados: list[Hallazgo] = []

        for persona in personas:
            assert persona.track_id is not None
            vistos.add(persona.track_id)
            faltante = epp_faltante(
                persona, detecciones, self._regla.epp_exigido, self._regla.confianza_minima
            )
            if faltante:
                self._acumular(persona, faltante)
            else:
                hallazgo = self._quizas_cerrar(persona.track_id, persona.capture_ts)
                if hallazgo is not None:
                    cerrados.append(hallazgo)

        # Un track que desapareció del cuadro también puede cerrar por tiempo.
        ts = detecciones[0].capture_ts if detecciones else None
        if ts is not None:
            for track_id in list(self._rachas.keys() - vistos):
                hallazgo = self._quizas_cerrar(track_id, ts)
                if hallazgo is not None:
                    cerrados.append(hallazgo)

        return cerrados

    def cerrar(self) -> list[Hallazgo]:
        """Cierra todo lo pendiente. Se llama al terminar el video o el flujo."""
        hallazgos = [
            self._construir(track_id, racha)
            for track_id, racha in self._rachas.items()
            if racha.confirmado
        ]
        self._rachas.clear()
        return hallazgos

    # ── Interno ────────────────────────────────────────────────────────────────

    def _acumular(self, persona: Deteccion, faltante: set[TipoEPP]) -> None:
        assert persona.track_id is not None
        racha = self._rachas.get(persona.track_id)
        if racha is None:
            racha = _Racha(
                epp_faltante=set(faltante),
                ts_inicio=persona.capture_ts,
                ts_ultimo_incumplimiento=persona.capture_ts,
                confianzas=[persona.confianza],
                cuadros_evidencia=[persona.cuadro_idx],
            )
            self._rachas[persona.track_id] = racha
        else:
            racha.epp_faltante |= faltante
            racha.ts_ultimo_incumplimiento = persona.capture_ts
            racha.cuadros += 1
            racha.confianzas.append(persona.confianza)
            if len(racha.cuadros_evidencia) < 8:
                racha.cuadros_evidencia.append(persona.cuadro_idx)

        if not racha.confirmado and racha.duracion >= self._regla.confirmacion_segundos:
            racha.confirmado = True

    def _quizas_cerrar(self, track_id: int, ahora: datetime) -> Hallazgo | None:
        racha = self._rachas.get(track_id)
        if racha is None:
            return None
        silencio = (ahora - racha.ts_ultimo_incumplimiento).total_seconds()
        if silencio < self._regla.cierre_segundos:
            return None  # oclusión breve: no partimos el hallazgo en dos
        del self._rachas[track_id]
        return self._construir(track_id, racha) if racha.confirmado else None

    def _construir(self, track_id: int, racha: _Racha) -> Hallazgo:
        return Hallazgo(
            track_id=track_id,
            regla_id=self._regla.id,
            regla_version=self._regla.version,
            epp_faltante=frozenset(racha.epp_faltante),
            severidad=self._regla.severidad,
            ts_inicio=racha.ts_inicio,
            ts_fin=racha.ts_ultimo_incumplimiento,
            cuadros_confirmados=racha.cuadros,
            confianza_media=sum(racha.confianzas) / len(racha.confianzas),
            cuadros_evidencia=tuple(racha.cuadros_evidencia),
        )


def agregar(regla: Regla, cuadros: Iterable[list[Deteccion]]) -> Iterator[Hallazgo]:
    """Atajo para procesar una secuencia completa de cuadros (uso en lote, v1)."""
    agregador = AgregadorDeHallazgos(regla)
    for detecciones in cuadros:
        yield from agregador.procesar_cuadro(detecciones)
    yield from agregador.cerrar()
