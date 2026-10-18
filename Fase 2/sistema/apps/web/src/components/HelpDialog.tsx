import { X } from "lucide-react";
import { useEffect, useId, useRef } from "react";

import { useModalKeyboard } from "../hooks/useModalKeyboard";

export function HelpDialog({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLElement>(null);
  const cerrarRef = useRef<HTMLButtonElement>(null);
  const tituloId = useId();
  const mensajeId = useId();
  useModalKeyboard(dialogRef, onClose);

  useEffect(() => { cerrarRef.current?.focus(); }, []);

  return <div className="modal-layer" role="presentation">
    <section ref={dialogRef} className="reason-dialog" role="dialog" aria-modal="true" aria-labelledby={tituloId} aria-describedby={mensajeId}>
      <header><h2 id={tituloId}>Ayuda</h2><button ref={cerrarRef} type="button" onClick={onClose} aria-label="Cerrar ayuda"><X size={17} /></button></header>
      <p id={mensajeId}>Llámanos al +56 9 XXXX XXXX. Estamos las 24 horas para ayudarte.</p>
      <p>Mensaje de demostración · Número ficticio.</p>
    </section>
  </div>;
}
