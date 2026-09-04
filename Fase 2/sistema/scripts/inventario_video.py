#!/usr/bin/env python3
"""Inventario tecnico de un directorio de video, sin dependencias externas.

Para cada archivo saca lo que el manifiesto de datos y V2 necesitan:
resolucion, fps reales, duracion, orientacion, si la camara esta fija, y el
factor de reescalado a la entrada del detector.

Solo stdlib + ffprobe/ffmpeg.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

# Entrada del detector. RF-DETR-Base = 560; Large = 728.
ENTRADA_DETECTOR = 560
# Lado minimo que un objeto necesita EN LA ENTRADA del detector para ser fiable.
PX_MINIMOS_ENTRADA = 20
# Muestreo para el analisis de movimiento.
FPS_MUESTREO = 2
ANCHO_MINI, ALTO_MINI = 160, 90
# Franja perimetral que se usa como referencia de fondo estatico.
MARGEN = 0.12


@dataclass
class Ficha:
    nombre: str
    ancho: int
    alto: int
    fps: float
    duracion: float
    codec: str
    mb: float
    mad_perimetro: float | None
    mad_actividad: float | None

    @property
    def orientacion(self) -> str:
        if self.ancho > self.alto:
            return "horizontal"
        if self.alto > self.ancho:
            return "VERTICAL"
        return "cuadrado"

    @property
    def factor_reescalado(self) -> float:
        """Cuanto encoge el cuadro al entrar al detector (lado largo manda)."""
        return ENTRADA_DETECTOR / max(self.ancho, self.alto)

    @property
    def px_minimos_en_cuadro(self) -> float:
        """Tamano minimo que un casco debe tener EN EL CUADRO para sobrevivir."""
        return PX_MINIMOS_ENTRADA / self.factor_reescalado

    @property
    def desperdicio_relleno(self) -> float:
        """Porcentaje del canvas cuadrado del detector que queda en relleno."""
        largo, corto = max(self.ancho, self.alto), min(self.ancho, self.alto)
        return 100.0 * (1.0 - corto / largo)

    @property
    def camara(self) -> str:
        if self.mad_perimetro is None:
            return "?"
        if self.mad_perimetro < 8:
            return "fija"
        if self.mad_perimetro < 20:
            return "leve deriva"
        return "SE MUEVE"

    @property
    def cuadros_a_5fps(self) -> int:
        return int(self.duracion * 5)


def ffprobe(ruta: Path) -> dict[str, dict[str, Any]]:
    salida = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(ruta),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    datos = json.loads(salida)
    return {"stream": datos["streams"][0], "format": datos["format"]}


def leer_pgm(ruta: Path) -> tuple[int, int, bytes]:
    """Lee un PGM binario (P5). Cabecera: magico, ancho, alto, maxval."""
    crudo = ruta.read_bytes()
    campos: list[bytes] = []
    pos = 0
    while len(campos) < 4:
        while pos < len(crudo) and crudo[pos : pos + 1].isspace():
            pos += 1
        if crudo[pos : pos + 1] == b"#":  # comentario
            while pos < len(crudo) and crudo[pos] != 0x0A:
                pos += 1
            continue
        inicio = pos
        while pos < len(crudo) and not crudo[pos : pos + 1].isspace():
            pos += 1
        campos.append(crudo[inicio:pos])
    return int(campos[1]), int(campos[2]), crudo[pos + 1 :]


def indices_perimetro(ancho: int, alto: int) -> list[int]:
    mx, my = int(ancho * MARGEN), int(alto * MARGEN)
    return [
        y * ancho + x
        for y in range(alto)
        for x in range(ancho)
        if x < mx or x >= ancho - mx or y < my or y >= alto - my
    ]


def mad(a: bytes, b: bytes, indices: list[int] | None = None) -> float:
    """Diferencia media absoluta, opcionalmente restringida a unos indices."""
    if indices is None:
        return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)
    return sum(abs(a[i] - b[i]) for i in indices) / len(indices)


def mediana_diferencias(a: bytes, b: bytes, indices: list[int]) -> float:
    """Mediana de |a-b| sobre unos indices.

    La MEDIA no sirve para detectar movimiento de camara: basta con que una
    esquina del perimetro tenga gente trabajando para dispararla. La MEDIANA
    exige que **la mayoria** del fondo haya cambiado, que es justo lo que pasa
    cuando la camara panea y no cuando solo se mueve lo que hay dentro.
    """
    diffs = sorted(abs(a[i] - b[i]) for i in indices)
    n = len(diffs)
    return diffs[n // 2] if n % 2 else (diffs[n // 2 - 1] + diffs[n // 2]) / 2


def analizar_movimiento(ruta: Path) -> tuple[float | None, float | None]:
    """Devuelve (MAD del perimetro contra el primer cuadro, MAD consecutivo).

    El perimetro es fondo casi siempre estatico: si sube, la camara se movio.
    El MAD consecutivo global mide cuanta accion hay en la escena.
    """
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(ruta),
                "-vf",
                f"fps={FPS_MUESTREO},scale={ANCHO_MINI}:{ALTO_MINI},format=gray",
                "-f",
                "image2",
                f"{tmp}/f_%04d.pgm",
            ],
            check=True,
            capture_output=True,
        )
        archivos = sorted(Path(tmp).glob("f_*.pgm"))
        if len(archivos) < 2:
            return None, None
        cuadros = [leer_pgm(f) for f in archivos]
        ancho, alto, _ = cuadros[0]
        borde = indices_perimetro(ancho, alto)
        base = cuadros[0][2]
        perimetro = max(mediana_diferencias(base, c[2], borde) for c in cuadros[1:])
        consecutivo = sum(
            mad(cuadros[i][2], cuadros[i + 1][2]) for i in range(len(cuadros) - 1)
        ) / (len(cuadros) - 1)
        return perimetro, consecutivo


def fichar(ruta: Path) -> Ficha:
    meta = ffprobe(ruta)
    s, f = meta["stream"], meta["format"]
    fps = float(Fraction(s.get("avg_frame_rate") or s["r_frame_rate"]))
    perimetro, actividad = analizar_movimiento(ruta)
    return Ficha(
        nombre=ruta.name,
        ancho=int(s["width"]),
        alto=int(s["height"]),
        fps=round(fps, 2),
        duracion=round(float(f["duration"]), 1),
        codec=s.get("codec_name", "?"),
        mb=round(int(f["size"]) / 1e6, 1),
        mad_perimetro=perimetro,
        mad_actividad=actividad,
    )


def main(directorio: str) -> int:
    if not shutil.which("ffprobe"):
        print("Falta ffprobe.", file=sys.stderr)
        return 1

    raiz = Path(directorio)
    videos = sorted(
        p for p in raiz.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    )
    if not videos:
        print(f"Sin video en {raiz}", file=sys.stderr)
        return 1

    fichas = [fichar(v) for v in videos]

    print(
        f"\n{len(fichas)} archivos · entrada del detector {ENTRADA_DETECTOR} px "
        f"· umbral {PX_MINIMOS_ENTRADA} px\n"
    )
    cab = (
        f"{'archivo':<52} {'resolucion':>11} {'fps':>6} {'seg':>6} "
        f"{'orient':>10} {'camara':>12} {'casco min':>10} {'relleno':>8}"
    )
    print(cab)
    print("-" * len(cab))
    for x in fichas:
        print(
            f"{x.nombre[:52]:<52} {f'{x.ancho}x{x.alto}':>11} {x.fps:>6.1f} "
            f"{x.duracion:>6.1f} {x.orientacion:>10} {x.camara:>12} "
            f"{x.px_minimos_en_cuadro:>9.0f}p {x.desperdicio_relleno:>7.0f}%"
        )

    print(f"\n{'archivo':<52} {'med perim':>10} {'MAD activ':>10} {'cuadros@5fps':>13}")
    print("-" * 88)
    for x in fichas:
        p = f"{x.mad_perimetro:.1f}" if x.mad_perimetro is not None else "-"
        a = f"{x.mad_actividad:.1f}" if x.mad_actividad is not None else "-"
        print(f"{x.nombre[:52]:<52} {p:>10} {a:>10} {x.cuadros_a_5fps:>13}")

    total = sum(x.duracion for x in fichas)
    print(
        f"\nTotal: {total:.0f} s ({total / 60:.1f} min) · "
        f"{sum(x.cuadros_a_5fps for x in fichas)} cuadros a 5 fps"
    )
    print(
        "\n'casco min' = px que un casco debe medir EN EL CUADRO para llegar "
        f"a {PX_MINIMOS_ENTRADA} px tras el reescalado."
    )
    print("Mediana perim.: <8 camara fija · 8-20 deriva leve · >20 se mueve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
