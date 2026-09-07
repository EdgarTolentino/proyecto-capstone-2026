import { useEffect } from "react";

import type { Hallazgo } from "../api/types";

interface ShortcutOptions {
  hallazgos: Hallazgo[];
  activoId?: number;
  enabled: boolean;
  permiteTriar: boolean;
  visorAbierto: boolean;
  onActivate: (id: number) => void;
  onOpen: (id: number) => void;
  onConfirm: () => void;
  onFalsePositive: () => void;
}

// Los atajos viven en un hook separado para poder probarlos sin montar toda la pantalla.
export function useHallazgoShortcuts(options: ShortcutOptions) {
  useEffect(() => {
    const usarAtajo = (event: KeyboardEvent) => {
      const estaEscribiendo =
        event.target instanceof Element &&
        event.target.matches("input, select, textarea, [contenteditable='true']");
      if (!options.enabled || estaEscribiendo || event.ctrlKey || event.metaKey || event.altKey) return;

      const indice = options.hallazgos.findIndex((item) => item.id === options.activoId);
      if (event.key === "j" && indice < options.hallazgos.length - 1) {
        options.onActivate(options.hallazgos[indice + 1].id);
      }
      if (event.key === "k" && indice > 0) options.onActivate(options.hallazgos[indice - 1].id);
      if (event.key === "Enter" && options.activoId && !options.visorAbierto) {
        options.onOpen(options.activoId);
      }
      if (event.key === "c" && options.activoId && options.permiteTriar) options.onConfirm();
      if (event.key === "x" && options.activoId && options.permiteTriar) options.onFalsePositive();
    };

    window.addEventListener("keydown", usarAtajo);
    return () => window.removeEventListener("keydown", usarAtajo);
  }, [options]);
}
