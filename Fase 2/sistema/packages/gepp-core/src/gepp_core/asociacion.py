"""Asociar EPP sueltos a la persona correcta.

El detector devuelve cajas independientes: una de persona, una de casco, una de
chaleco. Con varias personas en el cuadro hay que decidir de quién es cada casco.

El criterio es geométrico y deliberadamente simple: un EPP pertenece a la persona
cuando su centro cae en la franja del cuerpo donde ese EPP debería estar. Un casco
flotando a la altura de las rodillas no se cuenta como casco puesto.
"""

from __future__ import annotations

from gepp_core.dominio import (
    CONFIANZA_MINIMA_REGLA,
    FRANJA_ESPERADA,
    ClaseDetectada,
    Deteccion,
    ModoIncumplimiento,
    TipoEPP,
)

#: Correspondencia entre clase del detector y tipo de EPP.
CLASE_A_EPP: dict[ClaseDetectada, TipoEPP] = {
    ClaseDetectada.CASCO: TipoEPP.CASCO,
    ClaseDetectada.CHALECO: TipoEPP.CHALECO,
    ClaseDetectada.LENTES: TipoEPP.LENTES,
    ClaseDetectada.GUANTES: TipoEPP.GUANTES,
    ClaseDetectada.ARNES: TipoEPP.ARNES,
    ClaseDetectada.CALZADO: TipoEPP.CALZADO,
}

#: Clase de EVIDENCIA positiva de que falta un EPP (ADR-013) -> el EPP que falta. Los EPP sin
#: entrada aquí (lentes, guantes, arnés, calzado) no tienen clase de evidencia.
EVIDENCIA_DE_FALTA: dict[ClaseDetectada, TipoEPP] = {
    ClaseDetectada.CABEZA: TipoEPP.CASCO,
    ClaseDetectada.SIN_CHALECO: TipoEPP.CHALECO,
}


def epp_puesto(
    persona: Deteccion,
    detecciones: list[Deteccion],
    confianza_minima: float = CONFIANZA_MINIMA_REGLA,
) -> set[TipoEPP]:
    """EPP que esta persona lleva puesto, según las detecciones del mismo cuadro."""
    if persona.clase is not ClaseDetectada.PERSONA:
        raise ValueError("la detección de referencia debe ser una persona")

    puesto: set[TipoEPP] = set()
    for det in detecciones:
        tipo = CLASE_A_EPP.get(det.clase)
        if tipo is None or det.confianza < confianza_minima:
            continue
        desde, hasta = FRANJA_ESPERADA[tipo]
        if persona.caja.franja(desde, hasta).contiene(det.caja.centro):
            puesto.add(tipo)
    return puesto


def _hay_evidencia_de_falta(
    persona: Deteccion,
    detecciones: list[Deteccion],
    tipo: TipoEPP,
    confianza_minima: float,
) -> bool:
    """¿El modelo vio la falta de `tipo`? (confianza >= mínima y centro en la franja)"""
    desde, hasta = FRANJA_ESPERADA[tipo]
    franja = persona.caja.franja(desde, hasta)
    return any(
        EVIDENCIA_DE_FALTA.get(det.clase) is tipo
        and det.confianza >= confianza_minima
        and franja.contiene(det.caja.centro)
        for det in detecciones
    )


def epp_faltante(
    persona: Deteccion,
    detecciones: list[Deteccion],
    exigido: frozenset[TipoEPP],
    confianza_minima: float = CONFIANZA_MINIMA_REGLA,
    modo: ModoIncumplimiento = ModoIncumplimiento.AUSENCIA,
) -> set[TipoEPP]:
    """EPP exigido que esta persona NO lleva puesto.

    - `AUSENCIA`: todo lo exigido que no se ve puesto.
    - `EVIDENCIA`: un EPP con clase de evidencia (`EVIDENCIA_DE_FALTA`) falta solo si el modelo
      vio esa evidencia en la franja de la persona **y** el EPP no está puesto (un casco y una
      cabeza a la vez: gana el casco). Un EPP exigido SIN clase de evidencia (lentes, guantes,
      arnés, calzado) se sigue evaluando por ausencia, porque no hay otra forma de decidirlo.
    """
    sin_puesto = set(exigido) - epp_puesto(persona, detecciones, confianza_minima)
    if modo is ModoIncumplimiento.AUSENCIA:
        return sin_puesto
    con_evidencia = set(EVIDENCIA_DE_FALTA.values())
    return {
        tipo
        for tipo in sin_puesto
        if tipo not in con_evidencia
        or _hay_evidencia_de_falta(persona, detecciones, tipo, confianza_minima)
    }
