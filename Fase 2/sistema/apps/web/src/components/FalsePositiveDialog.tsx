import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useModalKeyboard } from "../hooks/useModalKeyboard";

interface FalsePositiveDialogProps {
  count: number;
  onCancel: () => void;
  onConfirm: (motivo: string) => void;
}

export function FalsePositiveDialog({ count, onCancel, onConfirm }: FalsePositiveDialogProps) {
  const [motivo, setMotivo] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  useModalKeyboard(dialogRef, onCancel);

  useEffect(() => {
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    inputRef.current?.focus();
    return () => {
      if (openerRef.current?.isConnected) openerRef.current.focus();
    };
  }, []);

  return (
    <div className="modal-layer" role="presentation">
      <section ref={dialogRef} className="reason-dialog" role="dialog" aria-modal="true" aria-labelledby="reason-title">
        <header><h2 id="reason-title">Marcar como falso positivo</h2><button type="button" onClick={onCancel} aria-label="Cerrar"><X size={17} /></button></header>
        <p>Este motivo ayuda a mejorar el detector. Se aplicará a {count === 1 ? "este hallazgo" : `${count} hallazgos`}.</p>
        <label>Motivo<textarea ref={inputRef} value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ej.: El casco está cubierto por la estructura" /></label>
        <footer><button type="button" onClick={onCancel}>Cancelar</button><button className="primary-button" type="button" disabled={!motivo.trim()} onClick={() => onConfirm(motivo.trim())}>Guardar decisión</button></footer>
      </section>
    </div>
  );
}
