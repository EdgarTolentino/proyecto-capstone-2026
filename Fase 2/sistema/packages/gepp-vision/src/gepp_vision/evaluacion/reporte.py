"""Salida de los niveles 0 y 1 (#31): las métricas con lo necesario para reproducirlas.

El CLAUDE.md pide que las métricas de un modelo vayan con el commit, los datos y los pesos que
las produjeron. Especificación: `docs/arquitectura/04-evaluar-niveles-0-1.md`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from gepp_vision.evaluacion.acuerdo import KAPPA_MINIMO, SIN_CAJA, Acuerdo, bajo_el_minimo
from gepp_vision.evaluacion.acuerdo import UMBRAL_IOU as UMBRAL_IOU_ACUERDO
from gepp_vision.evaluacion.coco import CLASES, Recorte
from gepp_vision.evaluacion.deteccion import MAX_DETS, UMBRAL_IOU, MetricasRegion

#: De dónde sale la verdad: la cifra contra pre-etiquetas corregidas está inflada.
ORIGENES: tuple[str, ...] = ("con-preetiquetas", "sin-preetiquetas")

LIMITACIONES: tuple[str, ...] = (
    "Los cuadros salen de un solo video, en 4 tramos: no hay intervalos de confianza por "
    "remuestreo de video (02-plan-de-evaluacion.md).",
    "El nivel 1 mide objetos, no eventos: no hay prevalencia de incumplimiento.",
)
#: El mAP recorre la curva completa: necesita predicciones desde este score (`preetiquetar.py
#: --umbral 0.05`). Con un mínimo más alto la curva se corta y el mAP sale bajo sin error.
SCORE_MINIMO_MAP = 0.05
#: Desde aquí avisa. No en 0,05 justo: el score sale en float32 y el mínimo de un archivo bien
#: hecho queda apenas encima (0,050000179 en las predicciones reales de los 240 cuadros del
#: 4-oct). 1/16 es diádico y deja fuera los umbrales de verdad altos (0,25; 0,4).
AVISO_SCORE_MINIMO = 0.0625
SESGO = (
    "La verdad se hizo corrigiendo pre-etiquetas de este mismo modelo: la cifra está inflada "
    "(04-evaluar-niveles-0-1.md, «El sesgo de las pre-etiquetas»)."
)


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def estado_git(directorio: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=directorio, capture_output=True, text=True, check=True
        ).stdout.strip()

    return {
        "commit": git("rev-parse", "HEAD"),
        "cambios_sin_confirmar": bool(git("status", "--porcelain")),
    }


def reporte(
    regiones: Mapping[str, MetricasRegion],
    *,
    origen_verdad: str,
    modelo: str,
    imagenes: Sequence[str],
    recorte: Recorte,
    umbral: float,
    score_minimo: float | None,
    entradas: Mapping[str, Path],
    git: Mapping[str, Any],
) -> dict[str, Any]:
    """`umbral` es el de confianza, el mismo para las tres clases. `score_minimo` es el menor
    score de las predicciones evaluadas, None si no hubo ninguna."""
    if origen_verdad not in ORIGENES:
        raise ValueError(f"origen de la verdad desconocido: {origen_verdad!r}")
    return {
        "nivel": 1,
        "modelo": modelo,
        "origen_verdad": origen_verdad,
        **git,
        "entradas": {n: {"ruta": str(r), "sha256": sha256(r)} for n, r in entradas.items()},
        "parametros": {
            "recorte_px": list(recorte),
            "umbral_confianza": umbral,
            "score_minimo": score_minimo,
            "umbral_iou": UMBRAL_IOU,
            "max_dets": MAX_DETS,
            "imagenes": len(imagenes),
        },
        "imagenes": list(imagenes),
        "limitaciones": [*LIMITACIONES, *([SESGO] if origen_verdad == ORIGENES[0] else [])],
        "regiones": {r: dataclasses.asdict(m) for r, m in regiones.items()},
    }


def _n(valor: float | None) -> str:
    return "—" if valor is None else f"{valor:.3f}".replace(".", ",")


def tabla_markdown(datos: Mapping[str, Any]) -> str:
    """Tabla para pegar en el #31. Recibe la salida de `reporte`."""
    par = datos["parametros"]
    lineas = [
        f"### Nivel 1 · {datos['modelo']} · verdad {datos['origen_verdad']} · "
        f"{par['imagenes']} imágenes",
        "",
        "| Región | Clase | Verdad | Predichas ≥ umbral | mAP50 | mAP50-95 | Chico | Mediano "
        "| Grande | Precisión | Recall |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for region, m in datos["regiones"].items():
        total = {
            "clase": "**total**",
            "n_verdad": sum(c["n_verdad"] for c in m["clases"]),
            "n_predichas": sum(c["n_predichas"] for c in m["clases"]),
            **m,
        }
        filas = [*m["clases"], total]
        for c in filas:
            t = c["map50_95_por_tamano"]
            lineas.append(
                f"| {region} | {c['clase']} | {c['n_verdad']} | "
                f"{c['n_predichas']} | {_n(c['map50'])} | {_n(c['map50_95'])} | "
                f"{_n(t['chico'])} | {_n(t['mediano'])} | {_n(t['grande'])} | "
                f"{_n(c.get('precision'))} | {_n(c.get('recall'))} |"
            )
    for region, m in datos["regiones"].items():
        if m["max_predicciones"] > par["max_dets"]:
            lineas += [
                "",
                f"Aviso: en la región {region} una imagen tuvo {m['max_predicciones']} "
                f"predicciones en una clase; las que pasan de maxDets {par['max_dets']} no se "
                "evaluaron y el mAP de esa región queda subestimado.",
            ]
    if par["score_minimo"] is not None and par["score_minimo"] >= AVISO_SCORE_MINIMO:
        lineas += [
            "",
            f"Aviso: la predicción de menor score tiene {_n(par['score_minimo'])}; el mAP "
            f"necesita predicciones desde {_n(SCORE_MINIMO_MAP)}: corre preetiquetar.py "
            f"--umbral {SCORE_MINIMO_MAP}. Con la curva cortada el mAP queda subestimado.",
        ]
    sucio = " (con cambios sin confirmar)" if datos["cambios_sin_confirmar"] else ""
    lineas += [
        "",
        f"Commit `{datos['commit'][:7]}`{sucio} · confianza ≥ {par['umbral_confianza']} · "
        f"IoU ≥ {par['umbral_iou']} · maxDets {par['max_dets']} · recorte {par['recorte_px']}",
        "",
        *(f"- {limitacion}" for limitacion in datos["limitaciones"]),
    ]
    return "\n".join(lineas) + "\n"


LIMITACIONES_ACUERDO: tuple[str, ...] = (
    "La primera exportación se etiquetó corrigiendo pre-etiquetas del modelo y la segunda "
    "desde cero: el kappa mezcla el desacuerdo entre personas con el efecto de las sugerencias "
    "(04-evaluar-niveles-0-1.md, §Nivel 0).",
    "Son los cuadros del doble etiquetado de un solo video: el kappa es una estimación gruesa.",
)


def reporte_acuerdo(
    resultado: Acuerdo, *, entradas: Mapping[str, Path], git: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "nivel": 0,
        **git,
        "entradas": {n: {"ruta": str(r), "sha256": sha256(r)} for n, r in entradas.items()},
        "parametros": {
            "umbral_iou": UMBRAL_IOU_ACUERDO,
            "kappa_minimo": KAPPA_MINIMO,
            "imagenes": len(resultado.imagenes),
        },
        "imagenes": list(resultado.imagenes),
        "limitaciones": list(LIMITACIONES_ACUERDO),
        "resultado": dataclasses.asdict(resultado),
    }


def tabla_acuerdo(datos: Mapping[str, Any]) -> str:
    """Tabla del nivel 0 para pegar en el #112. Recibe la salida de `reporte_acuerdo`."""
    r = datos["resultado"]
    categorias = [*CLASES, SIN_CAJA]
    lineas = [
        f"### Nivel 0 · acuerdo entre etiquetadores · {datos['parametros']['imagenes']} imágenes",
        "",
        "| Kappa | IoU medio | Pares | Solo la primera | Solo la segunda |",
        "|---|---|---|---|---|",
        f"| {_n(r['kappa'])} | {_n(r['iou_medio'])} | {r['pares']} | {r['solo_primera']} "
        f"| {r['solo_segunda']} |",
        "",
        "Filas: la primera exportación; columnas: la segunda.",
        "",
        "| | " + " | ".join(categorias) + " |",
        "|---" * (len(categorias) + 1) + "|",
    ]
    for fila in categorias:
        cuentas = r["matriz"].get(fila, {})
        celdas = " | ".join(str(cuentas.get(c, 0)) for c in categorias)
        lineas.append(f"| {fila} | {celdas} |")
    lineas.append("")
    if r["kappa"] is None:
        lineas.append(
            "Kappa indefinido: no hay pares, o las dos personas usaron una sola y la misma clase."
        )
    elif bajo_el_minimo(r["kappa"]):
        lineas.append(
            f"**Alerta:** kappa {_n(r['kappa'])} bajo {_n(KAPPA_MINIMO)}. Según la guía §6: parar, "
            "discutir las diferencias y anotarlas en la §7 antes de seguir."
        )
    sucio = " (con cambios sin confirmar)" if datos["cambios_sin_confirmar"] else ""
    lineas += [
        "",
        f"Commit `{datos['commit'][:7]}`{sucio} · IoU ≥ {datos['parametros']['umbral_iou']}",
        "",
        *(f"- {limitacion}" for limitacion in datos["limitaciones"]),
    ]
    return "\n".join(lineas) + "\n"
