import { useCallback, useEffect, useRef, useState } from "react";

import type { Severidad, TipoEpp, VistaTriage } from "../api/types";

export type SeccionApp = "panel" | "hallazgos" | "reglas";

export interface DestinoHallazgos {
  vista?: VistaTriage;
  severidad?: Severidad;
  epp?: TipoEpp;
  hallazgoId?: number;
}

const parametrosCompartidos = ["desde", "hasta", "turno"] as const;
const parametrosPanel = [...parametrosCompartidos, "obra_id"] as const;

export function construirRutaHallazgos(destino: DestinoHallazgos): string {
  const actuales = new URL(window.location.href).searchParams;
  const parametros = new URLSearchParams();
  for (const nombre of parametrosCompartidos) {
    const valor = actuales.get(nombre);
    if (valor) parametros.set(nombre, valor);
  }
  if (destino.vista) parametros.set("vista", destino.vista);
  if (destino.severidad) parametros.set("severidad", String(destino.severidad));
  if (destino.epp) parametros.set("epp", destino.epp);
  if (destino.hallazgoId) parametros.set("hallazgo", String(destino.hallazgoId));
  const consulta = parametros.toString();
  return `/hallazgos${consulta ? `?${consulta}` : ""}`;
}

function leerSeccion(): SeccionApp {
  if (window.location.pathname.startsWith("/reglas")) return "reglas";
  if (window.location.pathname.startsWith("/hallazgos")) return "hallazgos";
  return "panel";
}

function ubicacionHallazgosActual(): string {
  const ruta = window.location.pathname.startsWith("/hallazgos")
    ? window.location.pathname
    : "/hallazgos";
  return `${ruta}${window.location.search}`;
}

function ubicacionPanelActual(): string {
  const actuales = new URL(window.location.href).searchParams;
  const parametros = new URLSearchParams();
  for (const nombre of parametrosPanel) {
    const valor = actuales.get(nombre);
    if (valor) parametros.set(nombre, valor);
  }
  const consulta = parametros.toString();
  return `/${consulta ? `?${consulta}` : ""}`;
}

export function useAppNavigation() {
  const [seccion, setSeccion] = useState(leerSeccion);
  const ultimaUbicacionHallazgos = useRef(
    leerSeccion() === "hallazgos" ? ubicacionHallazgosActual() : "/hallazgos",
  );
  const ultimaUbicacionPanel = useRef(ubicacionPanelActual());

  useEffect(() => {
    const volver = () => {
      const siguiente = leerSeccion();
      if (siguiente === "hallazgos") ultimaUbicacionHallazgos.current = ubicacionHallazgosActual();
      if (siguiente === "panel") ultimaUbicacionPanel.current = ubicacionPanelActual();
      setSeccion(siguiente);
    };
    window.addEventListener("popstate", volver);
    return () => window.removeEventListener("popstate", volver);
  }, []);

  const navegar = useCallback((destino: SeccionApp) => {
    const actual = leerSeccion();
    if (actual === destino) return;
    if (actual === "hallazgos") ultimaUbicacionHallazgos.current = ubicacionHallazgosActual();
    if (actual === "panel") ultimaUbicacionPanel.current = ubicacionPanelActual();

    const ruta = destino === "panel" ? ultimaUbicacionPanel.current : destino === "reglas" ? "/reglas" : ultimaUbicacionHallazgos.current;
    window.history.pushState({}, "", ruta);
    setSeccion(destino);
  }, []);

  const navegarHallazgos = useCallback((destino: DestinoHallazgos) => {
    if (leerSeccion() === "panel") ultimaUbicacionPanel.current = ubicacionPanelActual();
    const ruta = construirRutaHallazgos(destino);
    ultimaUbicacionHallazgos.current = ruta;
    window.history.pushState({}, "", ruta);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, []);

  return { seccion, navegar, navegarHallazgos };
}
