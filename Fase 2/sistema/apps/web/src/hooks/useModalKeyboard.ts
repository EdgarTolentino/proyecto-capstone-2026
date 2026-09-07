import { useEffect, type RefObject } from "react";

// El teclado queda dentro del último diálogo abierto y Escape cierra solo ese diálogo.
export function useModalKeyboard(ref: RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    const manejar = (event: KeyboardEvent) => {
      const dialogs = document.querySelectorAll('[role="dialog"]');
      if (dialogs[dialogs.length - 1] !== ref.current) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
      if (event.key !== "Tab") return;
      const elements = ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea, select, summary, [tabindex="0"]');
      if (!elements?.length) return;
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", manejar);
    return () => window.removeEventListener("keydown", manejar);
  }, [ref, onClose]);
}
