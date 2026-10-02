import { useCallback, useEffect, useState } from "react";

import type { FiltrosHallazgos, VistaTriage } from "../api/types";
import { esFechaValida } from "../api/fechas";

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
  const desde = url.searchParams.get("desde");
  const hasta = url.searchParams.get("hasta");

  return {
    vista: vista && vistas.includes(vista) ? vista : "por_revisar",
    estado: url.searchParams.get("estado") ?? undefined,
    severidad: url.searchParams.get("severidad") ?? undefined,
    areaId: url.searchParams.get("area_id") ?? undefined,
    fuenteId: url.searchParams.get("fuente_id") ?? undefined,
    epp: url.searchParams.get("epp") ?? undefined,
    desde: desde && esFechaValida(desde) ? desde : undefined,
    hasta: hasta && esFechaValida(hasta) ? hasta : undefined,
    turno: url.searchParams.get("turno") ?? undefined,
    orden: url.searchParams.get("orden") ?? "ts_inicio_desc",
    hallazgoId: Number.isFinite(id) && id > 0 ? id : undefined,
  };
}

export function useHallazgoFilters() {
  const [filtros, setFiltros] = useState(leerFiltros);

  useEffect(() => {
    const volver = () => {
      const url = new URL(window.location.href);
      for (const nombre of ["desde", "hasta"] as const) {
        const valor = url.searchParams.get(nombre);
        if (valor && !esFechaValida(valor)) url.searchParams.delete(nombre);
      }
      window.history.replaceState({}, "", url);
      setFiltros(leerFiltros());
    };
    volver();
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
