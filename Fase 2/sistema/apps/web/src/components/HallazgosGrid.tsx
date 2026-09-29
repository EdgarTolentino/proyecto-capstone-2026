import { useVirtualizer } from "@tanstack/react-virtual";
import {
  ArrowUpRight,
  createLucideIcon,
  Glasses,
  Hand,
  HardHat,
  SportShoe,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef } from "react";

import type { Hallazgo, TipoEpp } from "../api/types";
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

const columnas = ["", "Prioridad", "EPP faltante", "Área / zona", "Cámara", "Inicio", "Duración", "Cuadros", "Confianza", "Evidencia", "Asignado a"];

const SafetyVest = createLucideIcon("SafetyVest", [
  ["path", { d: "M8 3h8l1 4 3 2-2 4v8H6v-8L4 9l3-2 1-4Z", key: "vest" }],
  ["path", { d: "M9 3c0 2 1 4 3 5 2-1 3-3 3-5", key: "neck" }],
  ["path", { d: "M6 14h12M6 17h12", key: "reflective" }],
]);

const SafetyHarness = createLucideIcon("SafetyHarness", [
  ["circle", { cx: "12", cy: "4", r: "2", key: "head" }],
  ["path", { d: "M12 6v7M8 8l4 5 4-5M9 13h6M8 21l4-8 4 8", key: "harness" }],
]);

const presentacionEpp: Record<TipoEpp, { Icono: LucideIcon; etiqueta: string }> = {
  casco: { Icono: HardHat, etiqueta: "Sin casco" },
  chaleco: { Icono: SafetyVest, etiqueta: "Sin chaleco" },
  lentes: { Icono: Glasses, etiqueta: "Sin lentes" },
  guantes: { Icono: Hand, etiqueta: "Sin guantes" },
  arnes: { Icono: SafetyHarness, etiqueta: "Sin arnés" },
  calzado: { Icono: SportShoe, etiqueta: "Sin calzado" },
};

function EppFaltante({ tipos }: { tipos: TipoEpp[] }) {
  return tipos.map((tipo) => {
    const { Icono, etiqueta } = presentacionEpp[tipo];
    return (
      <span
        className="epp-icon"
        data-tooltip={etiqueta}
        key={tipo}
        role="img"
        tabIndex={0}
        aria-label={etiqueta}
      >
        <Icono aria-hidden="true" size={18} strokeWidth={1.8} />
      </span>
    );
  });
}

export function HallazgosGrid(props: HallazgosGridProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  // TanStack Virtual expone métodos imperativos para controlar el scroll. React Compiler
  // omite la memoización de este componente, pero la API sigue siendo segura aquí.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtual = useVirtualizer({
    count: props.hallazgos.length,
    getScrollElement: () => viewportRef.current,
    estimateSize: () => 64,
    overscan: 8,
  });
  const todos = props.hallazgos.length > 0 && props.hallazgos.every((item) => props.seleccionados.has(item.id));

  // Cuando j/k cambia la fila activa, la mantenemos dentro de la parte visible.
  useEffect(() => {
    const index = props.hallazgos.findIndex((item) => item.id === props.activoId);
    if (index >= 0) virtual.scrollToIndex(index, { align: "auto" });
  }, [props.activoId, props.hallazgos, virtual]);

  return (
    <div
      className="findings-grid"
      role="grid"
      tabIndex={0}
      aria-label="Bandeja de hallazgos"
      aria-rowcount={props.hallazgos.length + 1}
      aria-activedescendant={props.activoId ? `hallazgo-${props.activoId}` : undefined}
    >
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
      <div role="cell" className="epp-icons"><EppFaltante tipos={item.epp_faltante} /></div>
      <div role="cell" className="area-cell"><strong>{item.area?.nombre ?? "Sin área"}</strong><small>{item.zona?.nombre ?? "Sin zona"}</small></div>
      <div role="cell" className="truncate mono">{item.fuente?.nombre ?? "—"}</div>
      <div role="cell" className="mono strong">{formatHora(item.ts_inicio)}</div>
      <div role="cell" className="mono">{formatDuracion(item.duracion_s)}</div>
      <div role="cell" className="mono number">{item.cuadros_confirmados}</div>
      <div role="cell" className="confidence"><span><i style={{ width: `${item.confianza_media * 100}%` }} /></span><b className="mono">{item.confianza_media.toLocaleString("es-CL", { minimumFractionDigits: 2 })}</b></div>
      <div role="cell"><button className="thumbnail" type="button" disabled={!permiteEvidencia} title={permiteEvidencia ? undefined : "No tienes permiso para ver evidencia"} onClick={(e) => { e.stopPropagation(); onOpen(item.id); }} aria-label={`Abrir evidencia del hallazgo ${item.id}`}><span>Ver</span><ArrowUpRight size={15} /></button></div>
      <div role="cell" className="truncate">{item.asignado_a?.nombre ?? "—"}</div>
    </div>
  );
}
