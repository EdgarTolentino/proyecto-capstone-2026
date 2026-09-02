"""Asociar EPP sueltos a la persona correcta.

El detector devuelve cajas independientes: una de persona, una de casco, una de
chaleco. Con varias personas en el cuadro hay que decidir de quién es cada casco.

El criterio es geométrico y deliberadamente simple: un EPP pertenece a la persona
cuando su centro cae en la franja del cuerpo donde ese EPP debería estar. Un casco
flotando a la altura de las rodillas no se cuenta como casco puesto.
"""

from __future__ import annotations

from gepp_core.dominio import FRANJA_ESPERADA, ClaseDetectada, Deteccion, TipoEPP

#: Correspondencia entre clase del detector y tipo de EPP.
CLASE_A_EPP: dict[ClaseDetectada, TipoEPP] = {
    ClaseDetectada.CASCO: TipoEPP.CASCO,
    ClaseDetectada.CHALECO: TipoEPP.CHALECO,
    ClaseDetectada.LENTES: TipoEPP.LENTES,
    ClaseDetectada.GUANTES: TipoEPP.GUANTES,
    ClaseDetectada.ARNES: TipoEPP.ARNES,
    ClaseDetectada.CALZADO: TipoEPP.CALZADO,
}


def epp_puesto(
    persona: Deteccion,
    detecciones: list[Deteccion],
    confianza_minima: float = 0.45,
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


def epp_faltante(
    persona: Deteccion,
    detecciones: list[Deteccion],
    exigido: frozenset[TipoEPP],
    confianza_minima: float = 0.45,
) -> set[TipoEPP]:
    """EPP exigido que esta persona NO lleva puesto."""
    return set(exigido) - epp_puesto(persona, detecciones, confianza_minima)
