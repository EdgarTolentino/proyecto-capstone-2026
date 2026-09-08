import { useCallback, useEffect, useState } from "react";

import type { FiltrosHallazgos, VistaTriage } from "../api/types";

const vistas: VistaTriage[] = [
  "por_revisar",
  "confirmados",
  "descartados",
  "reincidentes",
  "todos",
];

function leerFiltros(): FiltrosHallazgos {
  const url = new URL(window.location.href);
  const vista = url.searchParams.get("vista") as VistaTriage | null;
  const id = Number(url.searchParams.get("hallazgo"));

  return {
    vista: vista && vistas.includes(vista) ? vista : "por_revisar",
    estado: url.searchParams.get("estado") ?? undefined,
    severidad: url.searchParams.get("severidad") ?? undefined,
    areaId: url.searchParams.get("area_id") ?? undefined,
    fuenteId: url.searchParams.get("fuente_id") ?? undefined,
    epp: url.searchParams.get("epp") ?? undefined,
    desde: url.searchParams.get("desde") ?? undefined,
    hasta: url.searchParams.get("hasta") ?? undefined,
    turno: url.searchParams.get("turno") ?? undefined,
    orden: url.searchParams.get("orden") ?? "ts_inicio_desc",
    hallazgoId: Number.isFinite(id) && id > 0 ? id : undefined,
  };
}

export function useHallazgoFilters() {
  const [filtros, setFiltros] = useState(leerFiltros);

  useEffect(() => {
    const volver = () => setFiltros(leerFiltros());
    window.addEventListener("popstate", volver);
    return () => window.removeEventListener("popstate", volver);
  }, []);

  const actualizar = useCallback((cambios: Partial<FiltrosHallazgos>, reemplazar = false) => {
    const url = new URL(window.location.href);
    const nombres: Record<keyof FiltrosHallazgos, string> = {
      vista: "vista",
      estado: "estado",
      severidad: "severidad",
      areaId: "area_id",
      fuenteId: "fuente_id",
      epp: "epp",
      desde: "desde",
      hasta: "hasta",
      turno: "turno",
      orden: "orden",
      hallazgoId: "hallazgo",
    };

    for (const [clave, valor] of Object.entries(cambios)) {
      const nombre = nombres[clave as keyof FiltrosHallazgos];
      if (valor === undefined || valor === "") url.searchParams.delete(nombre);
      else url.searchParams.set(nombre, String(valor));
    }

    window.history[reemplazar ? "replaceState" : "pushState"]({}, "", url);
    setFiltros(leerFiltros());
  }, []);

  return { filtros, actualizar };
}
