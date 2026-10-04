"""Salida del nivel 1 (#31): las métricas con lo necesario para reproducirlas.

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

from gepp_vision.evaluacion.coco import Recorte
from gepp_vision.evaluacion.deteccion import MAX_DETS, UMBRAL_IOU, MetricasRegion

#: De dónde sale la verdad: la cifra contra pre-etiquetas corregidas está inflada.
ORIGENES: tuple[str, ...] = ("con-preetiquetas", "sin-preetiquetas")

LIMITACIONES: tuple[str, ...] = (
    "Los cuadros salen de un solo video, en 4 tramos: no hay intervalos de confianza por "
    "remuestreo de video (02-plan-de-evaluacion.md).",
    "El nivel 1 mide objetos, no eventos: no hay prevalencia de incumplimiento.",
)
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
    entradas: Mapping[str, Path],
    git: Mapping[str, Any],
) -> dict[str, Any]:
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
        "| Región | Clase | Verdad | Predichas | mAP50 | mAP50-95 | Chico | Mediano | Grande "
        "| Precisión | Recall |",
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
    sucio = " (con cambios sin confirmar)" if datos["cambios_sin_confirmar"] else ""
    lineas += [
        "",
        f"Commit `{datos['commit'][:7]}`{sucio} · confianza ≥ {par['umbral_confianza']} · "
        f"IoU ≥ {par['umbral_iou']} · maxDets {par['max_dets']} · recorte {par['recorte_px']}",
        "",
        *(f"- {limitacion}" for limitacion in datos["limitaciones"]),
    ]
    return "\n".join(lineas) + "\n"
