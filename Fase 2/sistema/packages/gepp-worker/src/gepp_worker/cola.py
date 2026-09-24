"""Cola de trabajos en Redis entre el vigilante y el trabajador (ADR-009).

Separa capturar de procesar: un detector lento no detiene al vigilante, y si el trabajador
se cae los trabajos siguen en Redis.

Estructura:

- `gepp:trabajos:pendientes` — lista de trabajos por tomar (JSON).
- `gepp:trabajos:procesando` — lista de trabajos tomados y sin confirmar. Si el trabajador
  muere a la mitad, el trabajo queda aquí y `recuperar_huerfanos()` lo devuelve a la cola.
- `gepp:video:<hash>` — estado del video (`pendiente`, `procesando`, `listo`, `error`),
  intentos y último motivo de error. La clave es el hash: el mismo archivo copiado dos veces
  es un solo trabajo.

El estado definitivo vive en la tabla `video`; este es el estado de la cola, útil mientras
la API (PT-09) no exponga `GET /videos`.
"""

from __future__ import annotations

import builtins
import json
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Any

PREFIJO = "gepp"
MAXIMO_INTENTOS = 3


class EstadoTrabajo(StrEnum):
    PENDIENTE = "pendiente"
    PROCESANDO = "procesando"
    LISTO = "listo"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Trabajo:
    ruta: str
    hash_sha256: str
    bytes: int
    fuente_id: int
    intentos: int = 0

    def a_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def desde_json(cls, texto: str | builtins.bytes) -> Trabajo:
        return cls(**json.loads(texto))


class ColaTrabajos:
    """Encolar, tomar, confirmar y reintentar, con estado por video.

    Recibe un cliente de Redis ya construido (`redis.Redis` o `fakeredis.FakeRedis`): la cola
    no sabe de URLs ni de configuración.
    """

    def __init__(self, cliente: Any, *, maximo_intentos: int = MAXIMO_INTENTOS) -> None:
        if maximo_intentos < 1:
            raise ValueError("maximo_intentos debe ser al menos 1")
        self._r = cliente
        self._maximo = maximo_intentos
        self._pendientes = f"{PREFIJO}:trabajos:pendientes"
        self._procesando = f"{PREFIJO}:trabajos:procesando"

    @property
    def maximo_intentos(self) -> int:
        return self._maximo

    def _clave(self, hash_sha256: str) -> str:
        return f"{PREFIJO}:video:{hash_sha256}"

    def estado(self, hash_sha256: str) -> EstadoTrabajo | None:
        valor = self._r.hget(self._clave(hash_sha256), "estado")
        if valor is None:
            return None
        return EstadoTrabajo(valor.decode() if isinstance(valor, bytes) else valor)

    def detalle(self, hash_sha256: str) -> dict[str, str]:
        crudo = self._r.hgetall(self._clave(hash_sha256))
        return {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in crudo.items()
        }

    def encolar(self, trabajo: Trabajo) -> bool:
        """Encola si el hash es nuevo. Devuelve False si ya estaba en la cola o terminado.

        `HSETNX` es atómico: dos vigilantes que ven el mismo archivo a la vez encolan uno solo.
        """
        clave = self._clave(trabajo.hash_sha256)
        if not self._r.hsetnx(clave, "estado", EstadoTrabajo.PENDIENTE.value):
            return False
        self._r.hset(clave, mapping={"ruta": trabajo.ruta, "intentos": trabajo.intentos})
        self._r.lpush(self._pendientes, trabajo.a_json())
        return True

    def reencolar(self, trabajo: Trabajo) -> None:
        """Vuelve a encolar un video que ya pasó por la cola (alguien pidió reintentarlo),
        con los intentos en cero. A diferencia de `encolar`, no mira si el hash ya estaba."""
        limpio = replace(trabajo, intentos=0)
        clave = self._clave(trabajo.hash_sha256)
        self._r.hdel(clave, "motivo")
        self._r.hset(
            clave,
            mapping={"estado": EstadoTrabajo.PENDIENTE.value, "ruta": trabajo.ruta, "intentos": 0},
        )
        self._r.lpush(self._pendientes, limpio.a_json())

    def tomar(self, espera_s: float = 0) -> Trabajo | None:
        """Mueve el trabajo más antiguo a `procesando`. Con `espera_s > 0` bloquea hasta ese
        tiempo esperando uno."""
        if espera_s > 0:
            crudo = self._r.blmove(self._pendientes, self._procesando, espera_s, "RIGHT", "LEFT")
        else:
            crudo = self._r.lmove(self._pendientes, self._procesando, "RIGHT", "LEFT")
        if crudo is None:
            return None
        trabajo = Trabajo.desde_json(crudo)
        self._r.hset(self._clave(trabajo.hash_sha256), "estado", EstadoTrabajo.PROCESANDO.value)
        return trabajo

    def confirmar(self, trabajo: Trabajo) -> None:
        self._r.lrem(self._procesando, 1, trabajo.a_json())
        self._r.hset(self._clave(trabajo.hash_sha256), "estado", EstadoTrabajo.LISTO.value)

    def reintentar(self, trabajo: Trabajo, motivo: str) -> EstadoTrabajo:
        """Cuenta un intento fallido: vuelve a la cola o, al llegar al máximo, queda en error."""
        self._r.lrem(self._procesando, 1, trabajo.a_json())
        siguiente = replace(trabajo, intentos=trabajo.intentos + 1)
        clave = self._clave(trabajo.hash_sha256)
        self._r.hset(clave, mapping={"intentos": siguiente.intentos, "motivo": motivo})
        if siguiente.intentos >= self._maximo:
            self._r.hset(clave, "estado", EstadoTrabajo.ERROR.value)
            return EstadoTrabajo.ERROR
        self._r.hset(clave, "estado", EstadoTrabajo.PENDIENTE.value)
        self._r.lpush(self._pendientes, siguiente.a_json())
        return EstadoTrabajo.PENDIENTE

    def recuperar_huerfanos(self) -> int:
        """Devuelve a pendientes lo que quedó en `procesando` (trabajador caído). Se llama al
        arrancar el trabajador, antes de tomar nada."""
        n = 0
        while (
            crudo := self._r.lmove(self._procesando, self._pendientes, "LEFT", "RIGHT")
        ) is not None:
            trabajo = Trabajo.desde_json(crudo)
            self._r.hset(self._clave(trabajo.hash_sha256), "estado", EstadoTrabajo.PENDIENTE.value)
            n += 1
        return n

    def pendientes(self) -> int:
        return int(self._r.llen(self._pendientes))
