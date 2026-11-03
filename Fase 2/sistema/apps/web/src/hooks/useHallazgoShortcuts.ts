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
  // Enter, c o x sin fila activa: la pantalla lo dice en vez de quedarse callada.
  onSinActivo?: () => void;
}

// Los atajos viven en un hook separado para poder probarlos sin montar toda la pantalla.
export function useHallazgoShortcuts(options: ShortcutOptions) {
  useEffect(() => {
    const usarAtajo = (event: KeyboardEvent) => {
      // Solo el visor permite revisar por teclado; los otros diálogos bloquean la bandeja.
      if (document.querySelector('[role="dialog"]:not([data-hallazgo-shortcuts])')) return;
      if (document.querySelector("[data-bloquea-atajos-hallazgos]")) return;
      const estaEscribiendo =
        event.target instanceof Element &&
        Boolean(event.target.closest("input, select, textarea, [contenteditable]:not([contenteditable='false'])"));
      const estaActivandoControl =
        (event.key === "Enter" || event.key === " " || event.key === "Spacebar") &&
        event.target instanceof Element &&
        Boolean(event.target.closest("button, a, [role='button']"));
      if (!options.enabled || estaEscribiendo || estaActivandoControl || event.ctrlKey || event.metaKey || event.altKey) return;

      const indice = options.hallazgos.findIndex((item) => item.id === options.activoId);
      // Un hallazgo abierto que ya no está en la lista no tiene vecinos (los botones del visor están
      // deshabilitados): `j` y `k` tampoco. Sin ninguno activo, `j` sí elige el primero.
      const fueraDeLaLista = indice === -1 && options.activoId !== undefined;
      if (event.key === "j" && !fueraDeLaLista && indice < options.hallazgos.length - 1) {
        options.onActivate(options.hallazgos[indice + 1].id);
      }
      if (event.key === "k" && !fueraDeLaLista && indice > 0) options.onActivate(options.hallazgos[indice - 1].id);
      const pideActuar =
        (event.key === "Enter" && !options.visorAbierto) ||
        ((event.key === "c" || event.key === "x") && options.permiteTriar);
      if (pideActuar && !options.activoId) options.onSinActivo?.();
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
