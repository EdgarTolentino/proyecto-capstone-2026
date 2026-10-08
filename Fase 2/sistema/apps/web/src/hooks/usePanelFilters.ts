import { useCallback, useEffect, useState } from "react";

import type { FiltrosPanel } from "../api/types";
import { esFechaValida, rangoDefectoPanel } from "../api/fechas";
import { leerSeccion } from "./useAppNavigation";

function normalizarUrlPanel(url = new URL(window.location.href)): URL {
  if (leerSeccion() !== "panel") return url;

  for (const nombre of ["desde", "hasta"] as const) {
    const valor = url.searchParams.get(nombre);
    if (valor && !esFechaValida(valor)) url.searchParams.delete(nombre);
  }
  const obraId = url.searchParams.get("obra_id");
  if (obraId && (!Number.isSafeInteger(Number(obraId)) || Number(obraId) < 1)) {
    url.searchParams.delete("obra_id");
  }

  if (!url.searchParams.has("desde") && !url.searchParams.has("hasta")) {
    const rango = rangoDefectoPanel();
    url.searchParams.set("desde", rango.desde);
    url.searchParams.set("hasta", rango.hasta);
  }

  return url;
}

function leerFiltrosPanel(): FiltrosPanel {
  const parametros = normalizarUrlPanel().searchParams;
  const obraId = Number(parametros.get("obra_id"));
  const desde = parametros.get("desde");
  const hasta = parametros.get("hasta");
  const turno = parametros.get("turno");

  return {
    ...(desde && esFechaValida(desde) ? { desde } : {}),
    ...(hasta && esFechaValida(hasta) ? { hasta } : {}),
    ...(turno ? { turno } : {}),
    ...(Number.isSafeInteger(obraId) && obraId > 0 ? { obraId } : {}),
  };
}

export function usePanelFilters() {
  const [filtros, setFiltros] = useState(leerFiltrosPanel);

  useEffect(() => {
    const volver = () => {
      const url = normalizarUrlPanel();
      window.history.replaceState({}, "", url);
      setFiltros(leerFiltrosPanel());
    };
    volver();
    window.addEventListener("popstate", volver);
    return () => window.removeEventListener("popstate", volver);
  }, []);

  const actualizar = useCallback((cambios: Partial<FiltrosPanel>) => {
    const url = new URL(window.location.href);
    const nombres: Record<keyof FiltrosPanel, string> = {
      desde: "desde",
      hasta: "hasta",
      turno: "turno",
      obraId: "obra_id",
    };

    for (const [clave, valor] of Object.entries(cambios)) {
      const nombre = nombres[clave as keyof FiltrosPanel];
      if (valor === undefined || valor === "") url.searchParams.delete(nombre);
      else url.searchParams.set(nombre, String(valor));
    }

    const normalizada = normalizarUrlPanel(url);
    window.history.pushState({}, "", normalizada);
    setFiltros(leerFiltrosPanel());
  }, []);

  return { filtros, actualizar };
}
