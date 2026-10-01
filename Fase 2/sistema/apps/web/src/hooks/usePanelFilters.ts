import { useCallback, useEffect, useState } from "react";

import type { FiltrosPanel } from "../api/types";

const formatoFecha = /^\d{4}-\d{2}-\d{2}$/;

function leerFiltrosPanel(): FiltrosPanel {
  const parametros = new URL(window.location.href).searchParams;
  const obraId = Number(parametros.get("obra_id"));
  const desde = parametros.get("desde");
  const hasta = parametros.get("hasta");
  const turno = parametros.get("turno");

  return {
    ...(desde && formatoFecha.test(desde) ? { desde } : {}),
    ...(hasta && formatoFecha.test(hasta) ? { hasta } : {}),
    ...(turno ? { turno } : {}),
    ...(Number.isSafeInteger(obraId) && obraId > 0 ? { obraId } : {}),
  };
}

export function usePanelFilters() {
  const [filtros, setFiltros] = useState(leerFiltrosPanel);

  useEffect(() => {
    const volver = () => setFiltros(leerFiltrosPanel());
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

    window.history.pushState({}, "", url);
    setFiltros(leerFiltrosPanel());
  }, []);

  return { filtros, actualizar };
}
