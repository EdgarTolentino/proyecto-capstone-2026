import { X } from "lucide-react";
import { useEffect, useId, useRef, type RefObject } from "react";

import { useModalKeyboard } from "../hooks/useModalKeyboard";

const preguntas = [
  ["¿Cómo recupero mi contraseña?", "La recuperación de contraseña no está disponible en esta versión. Si tienes dificultades para acceder, contacta a la persona que administra tu acceso."],
  ["¿Cómo actualizo mi perfil?", "La edición del perfil no está disponible en esta versión. Solicita los cambios a la persona que administra tu cuenta."],
  ["¿Qué hago si no puedo acceder?", "Comprueba tu conexión y consulta con la persona que administra tu cuenta si tu acceso sigue habilitado. No compartas tus credenciales."],
];

export function AccountHelpDialog({ onClose, volverA }: { onClose: () => void; volverA: RefObject<HTMLButtonElement | null> }) {
  const dialogRef = useRef<HTMLElement>(null);
  const cerrarRef = useRef<HTMLButtonElement>(null);
  const tituloId = useId();
  const avisoId = useId();
  useModalKeyboard(dialogRef, onClose);
  useEffect(() => {
    cerrarRef.current?.focus();
    return () => {
      const destino = volverA.current;
      if (destino?.isConnected) destino.focus();
      else document.querySelector<HTMLButtonElement>('.help-menu__trigger')?.focus();
    };
  }, [volverA]);

  return <div className="modal-layer" role="presentation">
    <section ref={dialogRef} className="reason-dialog account-help" role="dialog" aria-modal="true" aria-labelledby={tituloId}>
      <header><h2 id={tituloId}>Problemas con tu cuenta</h2><button ref={cerrarRef} type="button" aria-label="Cerrar problemas con tu cuenta" onClick={onClose}><X size={17} /></button></header>
      <div className="account-help__columns">
        <form aria-label="Contacto con soporte" onSubmit={(event) => event.preventDefault()}>
          <h3>Contacto con soporte</h3>
          <label>Destinatario provisional<input type="email" value="epp@soporte.cl" readOnly /></label>
          <label>Asunto<input type="text" /></label>
          <label>Describe tu problema<textarea rows={4} /></label>
          <p id={avisoId}>El envío de solicitudes estará disponible próximamente</p>
          <button type="submit" className="primary-button" disabled aria-describedby={avisoId}>Enviar solicitud</button>
        </form>
        <section aria-label="Preguntas frecuentes sobre tu cuenta">
          <h3>Preguntas frecuentes sobre tu cuenta</h3>
          {preguntas.map(([pregunta, respuesta]) => <details key={pregunta} name="preguntas-cuenta"><summary>{pregunta}</summary><p>{respuesta}</p></details>)}
        </section>
      </div>
    </section>
  </div>;
}
