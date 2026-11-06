import { useCallback, useEffect, useState } from "react";

import type { FiltrosReporte, SegmentacionReporte } from "../api/types";
import { esFechaValida, rangoDefectoPanel } from "../api/fechas";
import { leerSeccion } from "./useAppNavigation";

const segmentaciones: SegmentacionReporte[] = ["zona", "turno", "camara", "epp"];

function esSegmentacionReporte(valor: string): valor is SegmentacionReporte {
  return segmentaciones.includes(valor as SegmentacionReporte);
}

function normalizarUrlReporte(url = new URL(window.location.href)): URL {
  if (leerSeccion() !== "reportes") return url;

  for (const nombre of ["desde", "hasta"] as const) {
    const valor = url.searchParams.get(nombre);
    if (valor && !esFechaValida(valor)) url.searchParams.delete(nombre);
  }

  const areaId = url.searchParams.get("area_id");
  if (
    areaId !== null &&
    (!/^[1-9]\d*$/.test(areaId) || !Number.isSafeInteger(Number(areaId)))
  ) {
    url.searchParams.delete("area_id");
  }
  const segmentacion = url.searchParams.get("segmentacion");
  if (segmentacion && !esSegmentacionReporte(segmentacion)) url.searchParams.delete("segmentacion");

  const desde = url.searchParams.get("desde");
  const hasta = url.searchParams.get("hasta");
  if (desde && hasta && desde > hasta) {
    url.searchParams.delete("desde");
    url.searchParams.delete("hasta");
  }

  if (!url.searchParams.has("desde") && !url.searchParams.has("hasta")) {
    const rango = rangoDefectoPanel();
    url.searchParams.set("desde", rango.desde);
    url.searchParams.set("hasta", rango.hasta);
  }

  return url;
}

function leerFiltrosReporte(): FiltrosReporte {
  const parametros = normalizarUrlReporte().searchParams;
  const areaId = Number(parametros.get("area_id"));
  const desde = parametros.get("desde");
  const hasta = parametros.get("hasta");
  const segmentacion = parametros.get("segmentacion");

  return {
    ...(desde && esFechaValida(desde) ? { desde } : {}),
    ...(hasta && esFechaValida(hasta) ? { hasta } : {}),
    ...(Number.isSafeInteger(areaId) && areaId > 0 ? { areaId } : {}),
    ...(segmentacion && esSegmentacionReporte(segmentacion) ? { segmentacion } : {}),
  };
}

export function useReporteFilters() {
  const [filtros, setFiltros] = useState(leerFiltrosReporte);

  useEffect(() => {
    const sincronizar = () => {
      const url = normalizarUrlReporte();
      window.history.replaceState({}, "", url);
      setFiltros(leerFiltrosReporte());
    };
    sincronizar();
    window.addEventListener("popstate", sincronizar);
    return () => window.removeEventListener("popstate", sincronizar);
  }, []);

  const escribir = useCallback((cambios: Partial<FiltrosReporte>, reemplazar = false) => {
    const url = new URL(window.location.href);
    const nombres: Record<keyof FiltrosReporte, string> = {
      desde: "desde",
      hasta: "hasta",
      areaId: "area_id",
      segmentacion: "segmentacion",
    };

    for (const [clave, valor] of Object.entries(cambios)) {
      const nombre = nombres[clave as keyof FiltrosReporte];
      if (valor === undefined || valor === "") url.searchParams.delete(nombre);
      else url.searchParams.set(nombre, String(valor));
    }

    const normalizada = normalizarUrlReporte(url);
    window.history[reemplazar ? "replaceState" : "pushState"]({}, "", normalizada);
    setFiltros(leerFiltrosReporte());
  }, []);

  const actualizar = useCallback((cambios: Partial<FiltrosReporte>) => escribir(cambios), [escribir]);
  const reemplazar = useCallback((cambios: Partial<FiltrosReporte>) => escribir(cambios, true), [escribir]);

  return { filtros, actualizar, reemplazar };
}
