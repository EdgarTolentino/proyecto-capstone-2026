"""Recall de la clase `cabeza` contra una verdad que no la trae (ADR-013).

La verdad de CVAT (`prueba-youtube-lote0`) marca `persona`, `casco` y `chaleco`; nadie etiquetó
la cabeza sin casco. En vez de re-etiquetar, la cabeza esperada se DERIVA:

    toda `persona` de la verdad sin un `casco` asociado es una cabeza esperada.

**Casco asociado** es el del sistema, no uno nuevo: `gepp_core.asociacion.epp_puesto`, es decir,
un casco cuyo centro cae en la franja `FRANJA_ESPERADA[CASCO]` de la persona (el 30 % superior de
su caja, a todo su ancho, borde incluido). Así «persona sin casco» aquí y «casco faltante» en la
regla son la misma cosa.

**Emparejamiento de una predicción `cabeza`.** La caja de cabeza es mucho más chica que la de
persona: el IoU contra la persona no sirve. Una predicción pertenece a la persona cuya franja de
casco contiene el CENTRO de la predicción, con el borde incluido y medido en px (la franja en
coordenadas normalizadas puede quedar un ulp corta). Si lo contienen varias (personas encimadas),
a la de franja con centro más cercano EN PX: normalizar cada eje por una dimensión distinta
cambia cuál es la más cercana. Un empate exacto se resuelve por la caja de la persona (x, y,
ancho, alto), no por el orden del COCO. Después, por persona y en orden de score:

| Dónde cae el centro de la predicción | Cuenta como |
|---|---|
| franja de una persona SIN casco, la de mayor score | **acierto** (una por persona) |
| franja de una persona SIN casco, ya con acierto | **duplicada** |
| franja de una persona CON casco | **falso positivo sobre persona con casco** |
| ninguna franja | **sin persona** |

El recall es aciertos / cabezas esperadas. Solo cuentan las predicciones con score >= umbral; un
score fuera de [0, 1] o no finito es un error de entrada.

Limitaciones que hereda (no se pueden corregir sin re-etiquetar), en los dos sentidos: una
persona cuyo casco no se etiquetó (lejana, de menos de 8 px: guía de etiquetado §4 y §7) figura
como cabeza esperada aunque lleve casco, y baja el recall; un casco que cae en la franja de dos
personas encimadas las da a las dos por protegidas, y si a una le faltaba, sube el recall. La
cifra no es una cota en ningún sentido: es una estimación con estos dos sesgos declarados.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gepp_core import Caja, ClaseDetectada, Deteccion
from gepp_core.asociacion import epp_puesto
from gepp_core.dominio import FRANJA_ESPERADA, TipoEPP

from gepp_vision.etiquetado import TOLERANCIA_PX
from gepp_vision.evaluacion.coco import CajaPx, Recorte, en_region
from gepp_vision.evaluacion.reporte import limitacion_videos, sha256

#: Las predicciones se evalúan con la misma confianza que la regla (`deteccion.UMBRAL_REGLA`).
#: Instante fijo: el dominio exige zona horaria y aquí el tiempo no entra (ADR-005).
_INSTANTE = datetime(2000, 1, 1, tzinfo=UTC)
_FRANJA_CASCO = FRANJA_ESPERADA[TipoEPP.CASCO]
CLASE_CABEZA = "cabeza"


@dataclass(frozen=True, slots=True)
class MetricasCabeza:
    esperadas: int  # personas de la verdad sin casco asociado
    aciertos: int
    predichas: int  # cabezas sobre el umbral
    duplicadas: int
    falsos_positivos: int  # sobre una persona CON casco
    sin_persona: int  # en ninguna franja de persona
    recall: float | None  # None: no hay cabezas esperadas

    @property
    def perdidas(self) -> int:
        return self.esperadas - self.aciertos


def evaluar_cabeza(
    verdad: Sequence[CajaPx],
    predichas: Sequence[CajaPx],
    tamanos_imagen: Mapping[str, tuple[int, int]],
    recorte: Recorte,
    umbral: float,
) -> dict[str, MetricasCabeza]:
    """`dentro` y `fuera` del recorte, y `total`, sobre las imágenes de `tamanos_imagen`.

    Una persona va a la región de su centro; una predicción sin persona, a la de su propio
    centro. `verdad` trae personas y cascos; `predichas`, las cajas `cabeza` con score.
    """
    if not 0 < umbral <= 1:
        raise ValueError(f"umbral fuera de (0, 1]: {umbral}")
    if any(c.score is None for c in predichas):
        raise ValueError("una predicción sin score: ¿se pasó la verdad como predicciones?")
    malos = [c.score for c in predichas if c.score is not None and not 0 <= c.score <= 1]
    if malos:  # NaN también: no cumple 0 <= s <= 1
        raise ValueError(f"score fuera de [0, 1] o no finito: {malos[:3]}")

    # (región, resultado) de cada persona y de cada predicción sin persona.
    hechos: list[tuple[bool, str]] = []
    for archivo, (ancho, alto) in sorted(tamanos_imagen.items()):
        personas = [c for c in verdad if c.archivo == archivo and c.clase == "persona"]
        cascos = [c for c in verdad if c.archivo == archivo and c.clase == "casco"]
        cabezas = [
            c
            for c in predichas
            if c.archivo == archivo
            and c.clase == CLASE_CABEZA
            and c.score is not None
            and c.score >= umbral
        ]
        hechos += _de_la_imagen(personas, cascos, cabezas, ancho, alto, recorte)

    salida = {}
    for region, adentro in (("dentro", True), ("fuera", False)):
        salida[region] = _contar([r for d, r in hechos if d is adentro])
    salida["total"] = _contar([r for _, r in hechos])
    return salida


def personas_sin_casco(
    personas: Sequence[CajaPx], cascos: Sequence[CajaPx], ancho: int, alto: int
) -> list[bool]:
    """Por persona, ¿le falta el casco? La definición única de «sin casco asociado»: la de la
    regla (`epp_puesto`). La usan la evaluación y el premarcado de cabezas para CVAT."""
    dets_cascos = [
        Deteccion(_INSTANTE, 0, ClaseDetectada.CASCO, _normalizada(c, ancho, alto), 1.0)
        for c in cascos
    ]
    return [
        TipoEPP.CASCO
        not in epp_puesto(
            Deteccion(_INSTANTE, 0, ClaseDetectada.PERSONA, _normalizada(p, ancho, alto), 1.0),
            dets_cascos,
            confianza_minima=0.0,
        )
        for p in personas
    ]


def persona_dueña(
    personas: Sequence[CajaPx], x: float, y: float, ancho: int, alto: int
) -> int | None:
    """Índice de la persona a la que pertenece el punto (px): la de franja de casco más cercana
    EN PX entre todas las que la contienen (con casco o sin él), desempate por su caja. Un solo
    criterio para la evaluación y para el premarcado de cabezas."""
    franjas = [_normalizada(p, ancho, alto).franja(*_FRANJA_CASCO) for p in personas]
    dueñas = [i for i, f in enumerate(franjas) if _contiene_px(f, x, y, ancho, alto)]
    if not dueñas:
        return None
    return min(
        dueñas,
        key=lambda i: (
            _distancia2_px(franjas[i].centro, (x, y), ancho, alto),
            (personas[i].x, personas[i].y, personas[i].ancho, personas[i].alto),
        ),
    )


def _de_la_imagen(
    personas: Sequence[CajaPx],
    cascos: Sequence[CajaPx],
    cabezas: Sequence[CajaPx],
    ancho: int,
    alto: int,
    recorte: Recorte,
) -> list[tuple[bool, str]]:
    """Una tupla (¿dentro del recorte?, resultado) por persona y por predicción huérfana.

    Una persona sin casco deja `esperada`. Cada predicción deja `predicha` y su resultado
    (`acierto`, `duplicada`, `falso_positivo` o `sin_persona`), en la región de la persona a
    la que cayó o, si no cayó en ninguna, en la de su propio centro.
    """
    sin_casco = personas_sin_casco(personas, cascos, ancho, alto)
    adentro_p = [_dentro(p, recorte) for p in personas]
    hechos = [(a, "esperada") for a, s in zip(adentro_p, sin_casco, strict=True) if s]

    acertada = [False] * len(personas)
    for cabeza in sorted(cabezas, key=lambda c: -(c.score or 0.0)):
        cx, cy = cabeza.centro  # px
        i = persona_dueña(personas, cx, cy, ancho, alto)
        if i is None:
            hechos += [
                (_dentro(cabeza, recorte), "predicha"),
                (_dentro(cabeza, recorte), "sin_persona"),
            ]
            continue
        if not sin_casco[i]:
            resultado = "falso_positivo"
        elif acertada[i]:
            resultado = "duplicada"
        else:
            acertada[i] = True
            resultado = "acierto"
        hechos += [(adentro_p[i], "predicha"), (adentro_p[i], resultado)]
    return hechos


def _contar(resultados: Sequence[str]) -> MetricasCabeza:
    n = resultados.count
    esperadas = n("esperada")  # una por persona sin casco
    aciertos = n("acierto")
    return MetricasCabeza(
        esperadas=esperadas,
        aciertos=aciertos,
        predichas=n("predicha"),
        duplicadas=n("duplicada"),
        falsos_positivos=n("falso_positivo"),
        sin_persona=n("sin_persona"),
        recall=aciertos / esperadas if esperadas else None,
    )


def reporte_cabeza(
    regiones: Mapping[str, MetricasCabeza],
    *,
    modelo: str,
    clases: Path,
    imagenes: Sequence[str],
    recorte: Recorte,
    umbral: float,
    entradas: Mapping[str, Path],
    git: Mapping[str, Any],
) -> dict[str, Any]:
    """JSON con lo necesario para reproducir la cifra (commit, SHA-256, parámetros)."""
    return {
        "nivel": "1-cabeza",
        "modelo": modelo,
        "commit": git["commit"],
        "cambios_sin_confirmar": git["cambios_sin_confirmar"],
        "entradas": {n: {"ruta": str(r), "sha256": sha256(r)} for n, r in entradas.items()},
        "parametros": {
            "recorte_px": list(recorte),
            "umbral_confianza": umbral,
            "franja_casco": list(_FRANJA_CASCO),
            "mapa_de_clases": str(clases),
            "imagenes": len(imagenes),
        },
        "regiones": {r: {**asdict(m), "perdidas": m.perdidas} for r, m in regiones.items()},
        "imagenes": list(imagenes),
        "limitaciones": [
            limitacion_videos(imagenes),
            "La cabeza esperada se deriva (persona sin casco asociado), no está etiquetada. Sesgo "
            "a la baja: una persona cuyo casco no se etiquetó cuenta como cabeza esperada. Sesgo "
            "al alza: un casco en la franja de dos personas encimadas las da a las dos por "
            "protegidas. El recall no es una cota en ningún sentido.",
            "Mide objetos, no eventos: no hay prevalencia de incumplimiento.",
        ],
    }


def tabla_cabeza(datos: Mapping[str, Any]) -> str:
    """Tabla para pegar en el issue. Recibe la salida de `reporte_cabeza`."""
    par = datos["parametros"]
    lineas = [
        f"Recall de `cabeza` · {datos['modelo']} · {par['imagenes']} imágenes · "
        f"confianza >= {par['umbral_confianza']}",
        "",
        "| Región | Esperadas | Aciertos | Recall | Predichas | FP sobre persona con casco "
        "| Duplicadas | Sin persona |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for region, m in datos["regiones"].items():
        recall = "—" if m["recall"] is None else f"{m['recall']:.3f}".replace(".", ",")
        lineas.append(
            f"| {region} | {m['esperadas']} | {m['aciertos']} | {recall} | {m['predichas']} "
            f"| {m['falsos_positivos']} | {m['duplicadas']} | {m['sin_persona']} |"
        )
    lineas += ["", *(f"- {texto}" for texto in datos["limitaciones"])]
    return "\n".join(lineas)


def _normalizada(c: CajaPx, ancho: int, alto: int) -> Caja:
    return Caja(c.x / ancho, c.y / alto, (c.x + c.ancho) / ancho, (c.y + c.alto) / alto)


def _dentro(c: CajaPx, recorte: Recorte) -> bool:
    return bool(en_region([c], recorte, dentro=True))


def _contiene_px(f: Caja, x: float, y: float, ancho: int, alto: int) -> bool:
    """¿El punto (px) cae en la franja normalizada `f`, borde incluido? La comparación va en px
    con `TOLERANCIA_PX`: `0.3 * alto` normalizado puede quedar un ulp bajo el borde exacto."""
    return (
        f.x1 * ancho - TOLERANCIA_PX <= x <= f.x2 * ancho + TOLERANCIA_PX
        and f.y1 * alto - TOLERANCIA_PX <= y <= f.y2 * alto + TOLERANCIA_PX
    )


def _distancia2_px(c: tuple[float, float], p: tuple[float, float], ancho: int, alto: int) -> float:
    """Distancia² en px entre el centro normalizado `c` y el punto `p` en px."""
    return (c[0] * ancho - p[0]) ** 2 + (c[1] * alto - p[1]) ** 2
