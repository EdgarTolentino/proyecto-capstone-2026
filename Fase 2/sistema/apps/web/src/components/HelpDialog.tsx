import { FileVideo, LifeBuoy, SearchCheck, ShieldCheck, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { useModalKeyboard } from "../hooks/useModalKeyboard";

const tarjetas = [
  { titulo: "Procesa un video", icono: FileVideo, texto: "En Videos, selecciona un archivo disponible en el servidor y la cámara correspondiente para solicitar su procesamiento. Esta acción requiere permiso para procesar videos." },
  { titulo: "Revisa los hallazgos", icono: SearchCheck, texto: "En Hallazgos, consulta los resultados y utiliza los filtros para encontrar lo que necesitas revisar. Los resultados disponibles dependen de tus permisos." },
  { titulo: "Valida la evidencia", icono: ShieldCheck, texto: "Si tienes permiso para ver evidencia, abre un hallazgo para revisar su evidencia y por qué se disparó. Los resultados son indicios y requieren validación humana." },
  { titulo: "¿Necesitas ayuda?", icono: LifeBuoy, texto: "Llámanos al +56 9 XXXX XXXX. Estamos las 24 horas para ayudarte.", nota: "Mensaje de demostración · Número ficticio." },
];

export function HelpDialog({ onClose }: { onClose: () => void }) {
  const [indice, setIndice] = useState(0);
  const dialogRef = useRef<HTMLElement>(null);
  const cerrarRef = useRef<HTMLButtonElement>(null);
  const tituloId = useId();
  const mensajeId = useId();
  const tarjeta = tarjetas[indice];
  const Icono = tarjeta.icono;
  const ultima = indice === tarjetas.length - 1;
  useModalKeyboard(dialogRef, onClose);

  useEffect(() => { cerrarRef.current?.focus(); }, []);

  return <div className="modal-layer" role="presentation">
    <section ref={dialogRef} className="reason-dialog quick-guide" role="dialog" aria-modal="true" aria-labelledby={tituloId}>
      <header><h2 id={tituloId}>Primeros pasos en Guardián EPP</h2><button ref={cerrarRef} type="button" onClick={onClose} aria-label="Cerrar guía rápida"><X size={17} /></button></header>
      <div className="quick-guide__card" aria-live="polite" aria-atomic="true">
        <span className="quick-guide__icon"><Icono size={28} aria-hidden="true" /></span>
        <p className="quick-guide__step">{indice + 1} de {tarjetas.length}</p>
        <h3>{tarjeta.titulo}</h3>
        <p id={mensajeId}>{tarjeta.texto}</p>
        {tarjeta.nota && <p className="quick-guide__note">{tarjeta.nota}</p>}
      </div>
      <footer>
        <button type="button" disabled={indice === 0} onClick={() => setIndice(indice - 1)}>Anterior</button>
        <button type="button" className="primary-button" onClick={() => ultima ? onClose() : setIndice(indice + 1)}>{ultima ? "Finalizar" : "Siguiente"}</button>
      </footer>
    </section>
  </div>;
}
