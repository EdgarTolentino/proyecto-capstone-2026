"""Carga un perfil de dominio (`perfiles/*.yaml`) en la base (ADR-011).

Un perfil es configuración: cambiar de construcción a minería es cargar otro archivo, sin
tocar código. La carga es idempotente por nombre de faena: si ya existe, no hace nada.

Uso: `python -m gepp_bd.semilla perfiles/construccion.yaml`
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from gepp_core import Severidad, TipoEPP
from sqlalchemy import select
from sqlalchemy.orm import Session

from gepp_bd.modelos import ROLES, Area, Faena, Fuente, Usuario, Zona
from gepp_bd.repositorios import reglas
from gepp_bd.sesion import crear_motor, transaccion


class PerfilInvalido(ValueError):
    pass


def leer(ruta: Path) -> dict[str, Any]:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, dict):
        raise PerfilInvalido(f"{ruta}: el perfil debe ser un mapa YAML")
    for clave in ("perfil", "faena", "areas", "fuentes", "zonas", "reglas"):
        if clave not in datos:
            raise PerfilInvalido(f"{ruta}: falta la clave {clave!r}")
    return datos


def _epp(nombres: list[str], donde: str) -> frozenset[TipoEPP]:
    try:
        return frozenset(TipoEPP(n) for n in nombres)
    except ValueError as e:
        raise PerfilInvalido(f"{donde}: {e}") from e


def cargar(sesion: Session, perfil: dict[str, Any]) -> Faena:
    """Inserta faena, áreas, fuentes, zonas, usuarios de demostración y reglas. Devuelve la faena.

    Todas las referencias entre secciones son por nombre y se validan: un área o una
    fuente mal escrita falla con el nombre, no con un error de clave foránea.
    """
    existente = sesion.execute(
        select(Faena).where(Faena.nombre == perfil["faena"]["nombre"])
    ).scalar_one_or_none()
    if existente is not None:
        return existente

    faena = Faena(
        nombre=perfil["faena"]["nombre"],
        zona_horaria=perfil["faena"].get("zona_horaria", "America/Santiago"),
    )
    sesion.add(faena)
    sesion.flush()

    areas: dict[str, Area] = {}
    for a in perfil["areas"]:
        area = Area(faena_id=faena.id, nombre=a["nombre"], criticidad=a.get("criticidad", 1))
        sesion.add(area)
        areas[a["nombre"]] = area
    sesion.flush()

    def area_de(nombre: str, donde: str) -> Area:
        if nombre not in areas:
            raise PerfilInvalido(f"{donde}: el área {nombre!r} no está declarada en `areas`")
        return areas[nombre]

    fuentes: dict[str, Fuente] = {}
    for f in perfil["fuentes"]:
        fuente = Fuente(
            area_id=area_de(f["area"], f"fuente {f['nombre']!r}").id,
            nombre=f["nombre"],
            tipo=f["tipo"],
            uri=f["uri"],
            fps_objetivo=f.get("fps_objetivo", 5.0),
        )
        sesion.add(fuente)
        fuentes[f["nombre"]] = fuente
    sesion.flush()

    for z in perfil["zonas"]:
        donde = f"zona {z['nombre']!r}"
        if z["fuente"] not in fuentes:
            raise PerfilInvalido(f"{donde}: la fuente {z['fuente']!r} no está en `fuentes`")
        # Sin la clave `evaluable` la zona queda sin medir (NULL): no restringe. Con la clave,
        # el motor solo exige esos EPP en esa cámara (V2, #3).
        evaluable = (
            sorted(e.value for e in _epp(z["evaluable"], donde)) if "evaluable" in z else None
        )
        sesion.add(
            Zona(
                area_id=area_de(z["area"], donde).id,
                fuente_id=fuentes[z["fuente"]].id,
                nombre=z["nombre"],
                tipo=z["tipo"],
                poligono=z["poligono"],
                solape_minimo=z.get("solape_minimo", 0.5),
                evaluable=evaluable,
            )
        )
    sesion.flush()

    for u in perfil.get("usuarios", []):
        donde = f"usuario {u['email']!r}"
        if u["rol"] not in ROLES:
            raise PerfilInvalido(f"{donde}: rol {u['rol']!r} inválido")
        area_usuario = area_de(u["area"], donde) if u.get("area") else None
        sesion.add(
            Usuario(
                email=u["email"],
                nombre=u["nombre"],
                rol=u["rol"],
                area_id=area_usuario.id if area_usuario else None,
            )
        )
    sesion.flush()

    for r in perfil["reglas"]:
        donde = f"regla {r['nombre']!r}"
        reglas.crear(
            sesion,
            reglas.DefinicionRegla(
                area_id=area_de(r["area"], donde).id,
                nombre=r["nombre"],
                epp_exigido=_epp(r["epp_exigido"], donde),
                severidad=Severidad(r["severidad"]),
                base_licitud=r["base_licitud"],
                finalidad_declarada=r["finalidad_declarada"],
                norma_fundante=r.get("norma_fundante"),
                confirmacion_segundos=r.get("confirmacion_segundos", 2.0),
                cierre_segundos=r.get("cierre_segundos", 3.0),
                confianza_minima=r.get("confianza_minima", 0.45),
                retencion_dias=r.get("retencion_dias", 30),
            ),
        )
    return faena


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("uso: python -m gepp_bd.semilla perfiles/<perfil>.yaml", file=sys.stderr)
        return 2
    perfil = leer(Path(args[0]))
    with transaccion(crear_motor()) as sesion:
        faena = cargar(sesion, perfil)
        print(f"Perfil {perfil['perfil']!r} cargado en la faena {faena.nombre!r} (id {faena.id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
