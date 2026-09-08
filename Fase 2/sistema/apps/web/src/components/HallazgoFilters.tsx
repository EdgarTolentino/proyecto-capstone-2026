import { RotateCcw } from "lucide-react";

import type { Catalogos, FiltrosHallazgos } from "../api/types";

interface HallazgoFiltersProps {
  filtros: FiltrosHallazgos;
  catalogos?: Catalogos;
  onChange: (cambios: Partial<FiltrosHallazgos>) => void;
}

export function HallazgoFilters({ filtros, catalogos, onChange }: HallazgoFiltersProps) {
  const limpiar = () =>
    onChange({
      severidad: undefined,
      estado: undefined,
      areaId: undefined,
      fuenteId: undefined,
      epp: undefined,
      desde: undefined,
      hasta: undefined,
      turno: undefined,
      orden: "ts_inicio_desc",
    });

  return (
    <div className="filters" aria-label="Filtros de hallazgos">
      <label className="date-filter">
        <span>Desde</span>
        <input type="date" value={filtros.desde ?? ""} onChange={(e) => onChange({ desde: e.target.value })} />
      </label>
      <label className="date-filter">
        <span>Hasta</span>
        <input type="date" value={filtros.hasta ?? ""} onChange={(e) => onChange({ hasta: e.target.value })} />
      </label>
      <FilterSelect label="Área" value={filtros.areaId} onChange={(areaId) => onChange({ areaId })}>
        {catalogos?.areas?.map((area) => <option key={area?.id} value={area?.id}>{area?.nombre}</option>)}
      </FilterSelect>
      <FilterSelect label="Severidad" value={filtros.severidad} onChange={(severidad) => onChange({ severidad })}>
        <option value="4">Crítica</option><option value="3">Alta</option>
        <option value="2">Media</option><option value="1">Baja</option>
      </FilterSelect>
      <FilterSelect label="Estado" value={filtros.estado} onChange={(estado) => onChange({ estado })}>
        <option value="por_revisar">Por revisar</option>
        <option value="confirmado">Confirmado</option>
        <option value="falso_positivo">Falso positivo</option>
        <option value="duplicado">Duplicado</option>
        <option value="pospuesto">Pospuesto</option>
      </FilterSelect>
      <FilterSelect label="Tipo de EPP" value={filtros.epp} onChange={(epp) => onChange({ epp })}>
        {catalogos?.epp?.map((epp) => <option key={epp} value={epp}>{epp}</option>)}
      </FilterSelect>
      <FilterSelect label="Cámara" value={filtros.fuenteId} onChange={(fuenteId) => onChange({ fuenteId })}>
        {catalogos?.fuentes?.map((fuente) => <option key={fuente?.id} value={fuente?.id}>{fuente?.nombre}</option>)}
      </FilterSelect>
      <FilterSelect label="Turno" value={filtros.turno} onChange={(turno) => onChange({ turno })}>
        {catalogos?.turnos?.map((turno) => <option key={turno.codigo} value={turno.codigo}>{turno.etiqueta}</option>)}
      </FilterSelect>
      <FilterSelect label="Orden" value={filtros.orden} onChange={(orden) => onChange({ orden })}>
        <option value="ts_inicio_desc">Más recientes</option>
        <option value="severidad_desc">Mayor severidad</option>
        <option value="duracion_desc">Mayor duración</option>
        <option value="confianza_desc">Mayor confianza</option>
      </FilterSelect>
      <button className="icon-button" type="button" onClick={limpiar} aria-label="Limpiar filtros" title="Limpiar filtros">
        <RotateCcw size={14} />
      </button>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value?: string;
  onChange: (value: string | undefined) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="select-filter">
      <span className="sr-only">{label}</span>
      <select value={value ?? ""} onChange={(event) => onChange(event.target.value || undefined)}>
        <option value="">{label}: todos</option>
        {children}
      </select>
    </label>
  );
}
