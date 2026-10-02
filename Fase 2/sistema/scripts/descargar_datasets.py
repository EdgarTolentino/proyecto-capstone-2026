"""Descarga los datasets públicos de `fuentes.yaml` fuera del repositorio (#31).

    uv run python scripts/descargar_datasets.py ~/datos/gepp/crudos [--solo NOMBRE]

- **Roboflow** pide una API key gratuita. Se lee de `ROBOFLOW_API_KEY` o de
  `~/.config/gepp/datos.env` (una línea `ROBOFLOW_API_KEY=...`). Nunca se imprime ni se
  escribe en el registro.
- **Kaggle**: los datasets públicos se bajan sin credenciales.

Cada fuente queda en `DESTINO/<nombre>/`, con un `ORIGEN.json` (URL sin la key, versión,
fecha, licencia declarada y sha256 del zip): es lo que se copia a la fila de `07-datasets.md`.
Una fuente ya descargada se salta; para repetirla, borra su carpeta.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gepp_vision.entrenamiento import Fuente, cargar_fuentes

RAIZ = Path(__file__).resolve().parent
ROBOFLOW = "https://api.roboflow.com"
KAGGLE = "https://www.kaggle.com/api/v1/datasets/download"
ENV = Path.home() / ".config/gepp/datos.env"


def api_key_roboflow() -> str:
    if clave := os.environ.get("ROBOFLOW_API_KEY"):
        return clave
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8").splitlines():
            nombre, _, valor = linea.partition("=")
            if nombre.strip() == "ROBOFLOW_API_KEY" and valor.strip():
                return valor.strip().strip("\"'")
    sys.exit(f"Falta ROBOFLOW_API_KEY: ponla en {ENV} (fuera del repositorio).")


def _json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def _sin_clave(url: str) -> str:
    partes = urllib.parse.urlsplit(url)
    consulta = [(k, v) for k, v in urllib.parse.parse_qsl(partes.query) if k != "api_key"]
    return urllib.parse.urlunsplit(partes._replace(query=urllib.parse.urlencode(consulta)))


def enlace_roboflow(proyecto: str, version: int | None, clave: str) -> tuple[str, str]:
    """(enlace del zip COCO, id de versión). Sin versión fija, toma la más reciente."""
    q = urllib.parse.urlencode({"api_key": clave})
    if version is None:
        versiones = _json(f"{ROBOFLOW}/{proyecto}?{q}")["versions"]
        version = max(int(v["id"].rsplit("/", 1)[1]) for v in versiones)
    for _ in range(30):  # Roboflow arma el export la primera vez que se pide
        datos = _json(f"{ROBOFLOW}/{proyecto}/{version}/coco?{q}")
        if enlace := datos.get("export", {}).get("link"):
            return enlace, f"{proyecto}/{version}"
        time.sleep(10)
    sys.exit(f"Roboflow no terminó de preparar {proyecto}/{version}")


def bajar(url: str, destino: Path) -> str:
    """Descarga a `destino` y devuelve el sha256."""
    sha = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=600) as r, destino.open("wb") as f:
        while bloque := r.read(1 << 20):
            sha.update(bloque)
            f.write(bloque)
    return sha.hexdigest()


def descargar(fuente: Fuente, destino: Path) -> None:
    carpeta = destino / fuente.nombre
    if (carpeta / "ORIGEN.json").exists():
        print(f"  {fuente.nombre}: ya estaba, se salta")
        return
    origen = fuente.origen
    if origen["tipo"] == "roboflow":
        url, version = enlace_roboflow(
            origen["proyecto"], origen.get("version"), api_key_roboflow()
        )
    elif origen["tipo"] == "kaggle":
        url, version = f"{KAGGLE}/{origen['dataset']}", origen["dataset"]
    else:
        sys.exit(f"{fuente.nombre}: origen desconocido {origen['tipo']!r}")

    carpeta.mkdir(parents=True, exist_ok=True)
    zip_ = carpeta / "descarga.zip"
    print(f"  {fuente.nombre}: descargando {version} ...", flush=True)
    sha = bajar(url, zip_)
    with zipfile.ZipFile(zip_) as z:
        z.extractall(carpeta)
    zip_.unlink()
    registro = {
        "fuente": fuente.nombre,
        "version": version,
        "url": _sin_clave(url) if origen["tipo"] == "kaggle" else f"{ROBOFLOW}/{version}/coco",
        "licencia_declarada": fuente.licencia,
        "descargado": datetime.now(UTC).isoformat(timespec="seconds"),
        "sha256_zip": sha,
    }
    (carpeta / "ORIGEN.json").write_text(json.dumps(registro, indent=2), encoding="utf-8")
    print(f"  {fuente.nombre}: listo ({version}, sha256 {sha[:12]})")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("destino", type=Path)
    p.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes.yaml")
    p.add_argument("--solo", help="descargar solo esta fuente")
    args = p.parse_args(argv)

    fuentes = [f for f in cargar_fuentes(args.fuentes) if args.solo in (None, f.nombre)]
    if not fuentes:
        sys.exit(f"ninguna fuente se llama {args.solo!r}")
    for fuente in fuentes:
        descargar(fuente, args.destino.expanduser())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
