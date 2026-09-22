"""Trabajador: de un trabajo de la cola a filas en la base (PT-06).

    FuenteArchivo -> Muestreador -> PipelineEtapa1 -> gepp-bd

Tres transacciones por video, a propósito:

1. **Registro:** `video` (idempotente por hash) y estado `procesando`. Se confirma sola para
   que el estado se vea mientras el video corre.
2. **Resultado:** detecciones crudas, hallazgos, su evidencia y su notificación (outbox) y el
   estado `listo`, **todo o nada**. Si algo falla a la mitad no queda un hallazgo sin
   evidencia ni un aviso de un hallazgo que no existe, y reprocesar no duplica filas.
3. **Error:** si la 2 falla, estado `error` con el motivo.

Un video que ya está `listo` no se reprocesa: registrar el mismo hash devuelve la fila
existente y el trabajador la salta.

La evidencia sale de una **segunda pasada** por el video que decodifica solo los cuadros
elegidos. Guardar los cuadros de la primera pasada costaría gigas de memoria en un video de
30 min; releer el archivo cuesta unos segundos.

`proceso_ms` se mide con `time.monotonic`: es cuánto tardó el proceso, una duración, no un
instante. Ningún instante de este módulo sale del reloj del sistema (ADR-005).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from gepp_bd.modelos import Fuente, Zona
from gepp_bd.modelos import Regla as FilaRegla
from gepp_bd.repositorios import detecciones, evidencias, hallazgos, reglas, videos
from gepp_bd.sesion import transaccion
from gepp_core import ClaseDetectada, Deteccion, Hallazgo, Regla
from gepp_vision.evidencia import EvidenciaEscrita, escribir_evidencia
from gepp_vision.pipeline import PipelineEtapa1
from gepp_vision.privacidad import MascaraPrivacidad
from gepp_vision.puertos import Detector, Seguidor
from gepp_vision.seguimiento import SeguidorIoU
from sqlalchemy import Engine, select

from gepp_worker.cola import ColaTrabajos, Trabajo
from gepp_worker.fuente import Cuadro, PropiedadesFuente
from gepp_worker.fuente_archivo import FuenteArchivo
from gepp_worker.muestreo import Muestreador


@dataclass(frozen=True, slots=True)
class Aviso:
    """A quién se avisa de cada hallazgo. Sin aviso configurado no se escribe outbox."""

    canal: str
    destinatario: str


@dataclass(frozen=True, slots=True)
class Configuracion:
    carpeta_evidencia: Path
    fps_objetivo: float = 5.0
    aviso: Aviso | None = None


@dataclass(frozen=True, slots=True)
class Resultado:
    video_id: int
    omitido: bool
    cuadros: int = 0
    detecciones: int = 0
    hallazgos: int = 0


@dataclass(frozen=True, slots=True)
class _Contexto:
    video_id: int
    fuente_id: int
    area_id: int
    reglas: list[FilaRegla]
    privacidad: list[list[list[float]]]
    #: Las mismas reglas, tal como se aplican en esta cámara (zona, horario, evaluable).
    aplicables: list[Regla]


def _propiedades(ruta: Path) -> PropiedadesFuente:
    fuente = FuenteArchivo(ruta)
    fuente.abrir()
    try:
        return fuente.propiedades()
    finally:
        fuente.cerrar()


def _cuadro_de_evidencia(h: Hallazgo) -> int:
    """El cuadro del medio de los que registró el agregador: ni el primero (la persona
    puede estar entrando) ni el último (puede estar saliendo)."""
    if not h.cuadros_evidencia:
        raise ValueError("el hallazgo no trae cuadros de evidencia")
    return h.cuadros_evidencia[len(h.cuadros_evidencia) // 2]


class Trabajador:
    def __init__(
        self,
        motor: Engine,
        cola: ColaTrabajos,
        fabrica_detector: Callable[[], Detector],
        config: Configuracion,
        fabrica_seguidor: Callable[[], Seguidor] = SeguidorIoU,
    ) -> None:
        self._motor = motor
        self._cola = cola
        self._fabrica_detector = fabrica_detector
        self._fabrica_seguidor = fabrica_seguidor
        self._config = config

    # ── Cola ───────────────────────────────────────────────────────────────────

    def atender_uno(self, espera_s: float = 0) -> Resultado | None:
        """Toma un trabajo, lo procesa y lo confirma o lo devuelve para reintento."""
        trabajo = self._cola.tomar(espera_s)
        if trabajo is None:
            return None
        try:
            resultado = self.procesar(trabajo)
        except Exception as e:
            self._cola.reintentar(trabajo, f"{type(e).__name__}: {e}")
            return None
        self._cola.confirmar(trabajo)
        return resultado

    def correr(self, seguir: Callable[[], bool] = lambda: True, espera_s: float = 2.0) -> None:
        self._cola.recuperar_huerfanos()
        while seguir():
            self.atender_uno(espera_s)

    # ── Proceso de un video ────────────────────────────────────────────────────

    def procesar(self, trabajo: Trabajo) -> Resultado:
        inicio = time.monotonic()
        ruta = Path(trabajo.ruta)
        props = _propiedades(ruta)
        contexto = self._registrar(trabajo, props)
        if contexto is None:
            with transaccion(self._motor) as s:
                video = videos.por_hash(s, trabajo.hash_sha256)
                assert video is not None
                return Resultado(video_id=video.id, omitido=True)
        try:
            return self._analizar(ruta, props, contexto, inicio)
        except Exception as e:
            with transaccion(self._motor) as s:
                videos.cambiar_estado(
                    s, contexto.video_id, "error", error_motivo=f"{type(e).__name__}: {e}"
                )
            raise

    def _registrar(self, trabajo: Trabajo, props: PropiedadesFuente) -> _Contexto | None:
        duracion = props.cuadros_totales / props.fps if props.cuadros_totales is not None else None
        with transaccion(self._motor) as s:
            video, _ = videos.registrar(
                s,
                videos.NuevoVideo(
                    fuente_id=trabajo.fuente_id,
                    ruta=trabajo.ruta,
                    hash_sha256=trabajo.hash_sha256,
                    bytes=trabajo.bytes,
                    capture_ts_inicio=props.inicio_captura,
                    origen_capture_ts=props.origen_reloj,
                    duracion_s=duracion,
                    fps_declarado=props.fps,
                    ancho=props.ancho,
                    alto=props.alto,
                ),
            )
            if video.estado == "listo":
                return None
            fuente = s.get(Fuente, video.fuente_id)
            if fuente is None:
                raise LookupError(f"no existe la fuente {video.fuente_id}")
            activas = reglas.activas(s, area_id=fuente.area_id)
            if not activas:
                raise LookupError(f"el área {fuente.area_id} no tiene reglas activas")
            # Cada regla tal como se aplica en ESTA cámara: su zona, su horario y solo el EPP
            # que la cámara resuelve (V2). Las que no se pueden aplicar aquí, no entran.
            aplicables = reglas.para_fuente(s, fuente)
            if not aplicables:
                raise LookupError(
                    f"ninguna regla se puede aplicar en la fuente {fuente.id}: "
                    "el EPP que exigen no es evaluable en sus zonas"
                )
            privacidad = list(
                s.execute(
                    select(Zona.poligono).where(
                        Zona.fuente_id == fuente.id, Zona.tipo == "privacidad"
                    )
                ).scalars()
            )
            videos.cambiar_estado(s, video.id, "procesando")
            return _Contexto(video.id, fuente.id, fuente.area_id, activas, privacidad, aplicables)

    def _analizar(
        self, ruta: Path, props: PropiedadesFuente, ctx: _Contexto, inicio: float
    ) -> Resultado:
        mascara = MascaraPrivacidad([[(x, y) for x, y in p] for p in ctx.privacidad])
        pipeline = PipelineEtapa1(
            self._fabrica_detector(),
            self._fabrica_seguidor(),
            ctx.aplicables,
            mascara=mascara,
        )
        detector_version = pipeline.version_modelo
        muestreador = Muestreador(
            FuenteArchivo(ruta, inicio_captura=props.inicio_captura), self._config.fps_objetivo
        )
        muestreador.abrir()
        try:

            def cuadros() -> Iterator[Cuadro]:
                while muestreador.tomar():
                    cuadro = muestreador.recuperar()
                    if cuadro is not None:
                        yield cuadro

            resultado = pipeline.procesar_todo(cuadros())
        finally:
            muestreador.cerrar()

        escritas = self._escribir_evidencias(
            ruta, props, ctx, mascara, resultado.hallazgos, resultado.detecciones
        )
        try:
            with transaccion(self._motor) as s:
                n = detecciones.insertar(
                    s, ctx.video_id, resultado.detecciones, modelo_version=detector_version
                )
                for h, ev in zip(resultado.hallazgos, escritas, strict=True):
                    fila = hallazgos.guardar(
                        s,
                        h,
                        hallazgos.Contexto(
                            fuente_id=ctx.fuente_id, area_id=ctx.area_id, video_id=ctx.video_id
                        ),
                        self._avisos(h),
                    )
                    evidencias.insertar(
                        s,
                        hallazgo_id=fila.id,
                        ruta=str(ev.ruta),
                        hash_sha256=ev.hash_sha256,
                        cuadro_idx=ev.cuadro_idx,
                        capture_ts=ev.capture_ts,
                        purgar_el=ev.purgar_el,
                    )
                videos.cambiar_estado(
                    s,
                    ctx.video_id,
                    "listo",
                    cuadros_analizados=resultado.cuadros,
                    proceso_ms=round((time.monotonic() - inicio) * 1000),
                )
        except Exception:
            # Sin filas no hay evidencia: el recorte huérfano no se queda en disco.
            for ev in escritas:
                ev.ruta.unlink(missing_ok=True)
            raise
        return Resultado(
            video_id=ctx.video_id,
            omitido=False,
            cuadros=resultado.cuadros,
            detecciones=n,
            hallazgos=len(resultado.hallazgos),
        )

    def _avisos(self, h: Hallazgo) -> list[hallazgos.NuevaNotificacion]:
        aviso = self._config.aviso
        if aviso is None:
            return []
        return [
            hallazgos.NuevaNotificacion(
                canal=aviso.canal,
                destinatario=aviso.destinatario,
                cuerpo={
                    "regla_id": h.regla_id,
                    "regla_version": h.regla_version,
                    "epp_faltante": sorted(e.value for e in h.epp_faltante),
                    "severidad": int(h.severidad),
                    "ts_inicio": h.ts_inicio.isoformat(),
                },
            )
        ]

    def _escribir_evidencias(
        self,
        ruta: Path,
        props: PropiedadesFuente,
        ctx: _Contexto,
        mascara: MascaraPrivacidad,
        lista: list[Hallazgo],
        dets: list[Deteccion],
    ) -> list[EvidenciaEscrita]:
        """Segunda pasada: decodifica solo los cuadros elegidos y escribe los recortes."""
        if not lista:
            return []
        elegidos = [_cuadro_de_evidencia(h) for h in lista]
        personas: dict[int, list[Deteccion]] = {}
        for d in dets:
            if d.clase is ClaseDetectada.PERSONA and d.cuadro_idx in elegidos:
                personas.setdefault(d.cuadro_idx, []).append(d)
        retencion = {r.id: r.retencion_dias for r in ctx.reglas}

        imagenes = {}
        fuente = FuenteArchivo(ruta, inicio_captura=props.inicio_captura)
        fuente.abrir()
        try:
            indice = -1
            faltan = set(elegidos)
            while faltan and fuente.tomar():
                indice += 1
                if indice in faltan:
                    cuadro = fuente.recuperar()
                    if cuadro is not None:
                        imagenes[indice] = (cuadro.capture_ts, mascara.aplicar(cuadro.imagen))
                    faltan.discard(indice)
        finally:
            fuente.cerrar()

        escritas: list[EvidenciaEscrita] = []
        try:
            for n, (h, idx) in enumerate(zip(lista, elegidos, strict=True)):
                if idx not in imagenes:
                    raise LookupError(f"no se pudo leer el cuadro {idx} para la evidencia")
                capture_ts, imagen = imagenes[idx]
                en_cuadro = personas.get(idx, [])
                propia = next(d for d in en_cuadro if d.track_id == h.track_id)
                escritas.append(
                    escribir_evidencia(
                        imagen,
                        persona=propia.caja,
                        personas_en_cuadro=[d.caja for d in en_cuadro],
                        carpeta=self._config.carpeta_evidencia,
                        nombre=f"video{ctx.video_id}_h{n}_c{idx}",
                        cuadro_idx=idx,
                        capture_ts=capture_ts,
                        retencion_dias=retencion[h.regla_id],
                    )
                )
        except Exception:
            for ev in escritas:
                ev.ruta.unlink(missing_ok=True)
            raise
        return escritas
