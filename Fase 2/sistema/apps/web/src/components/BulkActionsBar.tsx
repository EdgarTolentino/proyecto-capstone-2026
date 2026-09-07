import { Check, X } from "lucide-react";

export function BulkActionsBar({ count, busy, onConfirm, onFalsePositive, onClear }: {
  count: number;
  busy: boolean;
  onConfirm: () => void;
  onFalsePositive: () => void;
  onClear: () => void;
}) {
  return (
    <div className="bulk-actions" role="toolbar" aria-label="Acciones para hallazgos seleccionados">
      <strong className="mono">{count} seleccionados</strong>
      <button className="primary-button" type="button" disabled={busy} onClick={onConfirm}><Check size={15} /> Confirmar</button>
      <button type="button" disabled={busy} onClick={onFalsePositive}>Falso positivo</button>
      <button className="bulk-close" type="button" onClick={onClear} aria-label="Limpiar selección"><X size={16} /></button>
    </div>
  );
}
