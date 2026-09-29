import { useCallback, useEffect, useRef, useState } from "react";

export type SeccionApp = "hallazgos" | "reglas";

function leerSeccion(): SeccionApp {
  return window.location.pathname.startsWith("/reglas") ? "reglas" : "hallazgos";
}

function ubicacionHallazgosActual(): string {
  const ruta = window.location.pathname.startsWith("/hallazgos")
    ? window.location.pathname
    : "/hallazgos";
  return `${ruta}${window.location.search}`;
}

export function useAppNavigation() {
  const [seccion, setSeccion] = useState(leerSeccion);
  const ultimaUbicacionHallazgos = useRef(
    leerSeccion() === "hallazgos" ? ubicacionHallazgosActual() : "/hallazgos",
  );

  useEffect(() => {
    const volver = () => {
      const siguiente = leerSeccion();
      if (siguiente === "hallazgos") ultimaUbicacionHallazgos.current = ubicacionHallazgosActual();
      setSeccion(siguiente);
    };
    window.addEventListener("popstate", volver);
    return () => window.removeEventListener("popstate", volver);
  }, []);

  const navegar = useCallback((destino: SeccionApp) => {
    const actual = leerSeccion();
    if (actual === destino) return;
    if (actual === "hallazgos") ultimaUbicacionHallazgos.current = ubicacionHallazgosActual();

    const ruta = destino === "reglas" ? "/reglas" : ultimaUbicacionHallazgos.current;
    window.history.pushState({}, "", ruta);
    setSeccion(destino);
  }, []);

  return { seccion, navegar };
}
