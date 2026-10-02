import { RotateCcw } from "lucide-react";

import type { Catalogos, FiltrosPanel } from "../api/types";

interface PanelFiltersProps {
  filtros: FiltrosPanel;
  catalogos?: Catalogos;
  onChange: (cambios: Partial<FiltrosPanel>) => void;
}

export function PanelFilters({ filtros, catalogos, onChange }: PanelFiltersProps) {
  const limpiar = () => onChange({ obraId: undefined, desde: undefined, hasta: undefined, turno: undefined });

  return (
    <div className="filters panel-filters" role="group" aria-label="Filtros del panel general">
      <label className="select-filter">
        <span>Obra</span>
        <select
          value={filtros.obraId ?? ""}
          onChange={(event) => onChange({ obraId: event.target.value ? Number(event.target.value) : undefined })}
        >
          <option value="">Todas las obras</option>
          {catalogos?.obras?.map((obra) => obra && <option key={obra.id} value={obra.id}>{obra.nombre}</option>)}
        </select>
      </label>
      <label className="date-filter">
        <span>Desde</span>
        <input type="date" value={filtros.desde ?? ""} max={filtros.hasta} onChange={(event) => onChange({ desde: event.target.value || undefined })} />
      </label>
      <label className="date-filter">
        <span>Hasta</span>
        <input type="date" value={filtros.hasta ?? ""} min={filtros.desde} onChange={(event) => onChange({ hasta: event.target.value || undefined })} />
      </label>
      <label className="select-filter">
        <span>Turno</span>
        <select value={filtros.turno ?? ""} onChange={(event) => onChange({ turno: event.target.value || undefined })}>
          <option value="">Todos los turnos</option>
          {catalogos?.turnos?.map((turno) => turno.codigo && <option key={turno.codigo} value={turno.codigo}>{turno.etiqueta ?? turno.codigo}</option>)}
        </select>
      </label>
      <button className="icon-button" type="button" onClick={limpiar} aria-label="Limpiar filtros del panel" title="Limpiar filtros del panel">
        <RotateCcw size={14} aria-hidden="true" />
      </button>
    </div>
  );
}
