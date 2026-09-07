import { useVirtualizer } from "@tanstack/react-virtual";
import { ImageOff } from "lucide-react";
import { useEffect, useRef } from "react";

import type { Hallazgo } from "../api/types";
import { formatDuracion, formatHora } from "../utils/format";
import { SeverityBadge } from "./SeverityBadge";

interface HallazgosGridProps {
  hallazgos: Hallazgo[];
  activoId?: number;
  seleccionados: Set<number>;
  permiteSeleccionar: boolean;
  permiteEvidencia: boolean;
  onActivate: (id: number) => void;
  onOpen: (id: number) => void;
  onSelect: (id: number, selected: boolean) => void;
  onSelectAll: (selected: boolean) => void;
}

const columnas = ["", "Severidad", "Incumplimiento", "Área / zona", "Cámara", "Inicio", "Duración", "Cuadros", "Confianza", "Recorte", "Asignado a"];

export function HallazgosGrid(props: HallazgosGridProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  // TanStack Virtual expone métodos imperativos para controlar el scroll. React Compiler
  // omite la memoización de este componente, pero la API sigue siendo segura aquí.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtual = useVirtualizer({
    count: props.hallazgos.length,
    getScrollElement: () => viewportRef.current,
    estimateSize: () => 40,
    overscan: 8,
  });
  const todos = props.hallazgos.length > 0 && props.hallazgos.every((item) => props.seleccionados.has(item.id));

  // Cuando j/k cambia la fila activa, la mantenemos dentro de la parte visible.
  useEffect(() => {
    const index = props.hallazgos.findIndex((item) => item.id === props.activoId);
    if (index >= 0) virtual.scrollToIndex(index, { align: "auto" });
  }, [props.activoId, props.hallazgos, virtual]);

  return (
    <div className="findings-grid" role="grid" aria-label="Bandeja de hallazgos" aria-rowcount={props.hallazgos.length + 1}>
      <div className="grid-header" role="row">
        {columnas.map((columna, indice) => (
          <div role="columnheader" key={`${columna}-${indice}`}>
            {indice === 0 ? (
              <input type="checkbox" checked={todos} disabled={!props.permiteSeleccionar} onChange={(e) => props.onSelectAll(e.target.checked)} aria-label="Seleccionar todos" />
            ) : columna}
          </div>
        ))}
      </div>
      <div
        className="grid-viewport"
        ref={viewportRef}
        tabIndex={0}
        aria-activedescendant={props.activoId ? `hallazgo-${props.activoId}` : undefined}
      >
        <div className="grid-spacer" style={{ height: virtual.getTotalSize() }}>
          {virtual.getVirtualItems().map((row) => {
            const item = props.hallazgos[row.index];
            return (
              <HallazgoRow
                key={item.id}
                item={item}
                activo={item.id === props.activoId}
                seleccionado={props.seleccionados.has(item.id)}
                permiteSeleccionar={props.permiteSeleccionar}
                permiteEvidencia={props.permiteEvidencia}
                onActivate={props.onActivate}
                onOpen={props.onOpen}
                onSelect={props.onSelect}
                style={{ transform: `translateY(${row.start}px)` }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

function HallazgoRow({ item, activo, seleccionado, permiteSeleccionar, permiteEvidencia, onActivate, onOpen, onSelect, style }: {
  item: Hallazgo;
  activo: boolean;
  seleccionado: boolean;
  permiteSeleccionar: boolean;
  permiteEvidencia: boolean;
  onActivate: (id: number) => void;
  onOpen: (id: number) => void;
  onSelect: (id: number, selected: boolean) => void;
  style: React.CSSProperties;
}) {
  return (
    <div
      id={`hallazgo-${item.id}`}
      role="row"
      aria-selected={activo}
      tabIndex={-1}
      className={`finding-row severity-border--${item.severidad} ${activo ? "is-active" : ""}`}
      style={style}
      onClick={() => onActivate(item.id)}
      onDoubleClick={() => onOpen(item.id)}
    >
      <div role="cell"><input type="checkbox" checked={seleccionado} disabled={!permiteSeleccionar} onChange={(e) => onSelect(item.id, e.target.checked)} onClick={(e) => e.stopPropagation()} aria-label={`Seleccionar hallazgo ${item.id}`} /></div>
      <div role="cell"><SeverityBadge severidad={item.severidad} /></div>
      <div role="cell" className="epp-tags">{item.epp_faltante.map((epp) => <span key={epp}>sin {epp}</span>)}</div>
      <div role="cell" className="area-cell"><strong>{item.area?.nombre ?? "Sin área"}</strong><small>{item.zona?.nombre ?? "Sin zona"}</small></div>
      <div role="cell" className="truncate mono">{item.fuente?.nombre ?? "—"}</div>
      <div role="cell" className="mono strong">{formatHora(item.ts_inicio)}</div>
      <div role="cell" className="mono">{formatDuracion(item.duracion_s)}</div>
      <div role="cell" className="mono number">{item.cuadros_confirmados}</div>
      <div role="cell" className="confidence"><span><i style={{ width: `${item.confianza_media * 100}%` }} /></span><b className="mono">{item.confianza_media.toLocaleString("es-CL", { minimumFractionDigits: 2 })}</b></div>
      <div role="cell"><button className="thumbnail" type="button" disabled={!permiteEvidencia} title={permiteEvidencia ? undefined : "No tienes permiso para ver evidencia"} onClick={(e) => { e.stopPropagation(); onOpen(item.id); }} aria-label={`Abrir evidencia del hallazgo ${item.id}`}><ImageOff size={15} /></button></div>
      <div role="cell" className="truncate">{item.asignado_a?.nombre ?? "—"}</div>
    </div>
  );
}
