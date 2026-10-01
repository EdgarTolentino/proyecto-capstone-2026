import { AlertTriangle, RadioTower } from "lucide-react";

import type { Panel, TipoEpp } from "../api/types";
import type { DestinoHallazgos } from "../hooks/useAppNavigation";
import { SeverityBadge } from "./SeverityBadge";

interface PanelOperationsProps {
  criticos: Panel["criticos_recientes"];
  cobertura: Panel["cobertura"];
  onNavigateHallazgos: (destino: DestinoHallazgos) => void;
}

const nombresEpp: Record<TipoEpp, string> = {
  casco: "casco",
  chaleco: "chaleco",
  lentes: "lentes",
  guantes: "guantes",
  arnes: "arnés",
  calzado: "calzado",
};

const motivosCobertura: Record<NonNullable<NonNullable<Panel["cobertura"]["sin_cobertura"]>[number]["motivo"]>, string> = {
  sin_ingesta: "Sin ingesta",
  requiere_recalibracion: "Requiere recalibración",
  error: "Error de fuente",
  regla_degradada: "Regla degradada",
};

const formatoFecha = new Intl.DateTimeFormat("es-CL", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function CriticosRecientes({ criticos, onNavigateHallazgos }: { criticos: Panel["criticos_recientes"]; onNavigateHallazgos: PanelOperationsProps["onNavigateHallazgos"] }) {
  const recientes = criticos.slice(0, 8);
  return (
    <section className="panel-operation" aria-labelledby="panel-criticos-title">
      <header><div><p className="eyebrow">ATENCIÓN PRIORITARIA</p><h3 id="panel-criticos-title">Hallazgos críticos recientes</h3></div><span>Máximo 8</span></header>
      {recientes.length === 0 ? <p className="panel-operation__empty">No hay hallazgos críticos en el período.</p> : (
        <ol className="panel-critical-list" aria-label="Hallazgos críticos recientes">
          {recientes.map((hallazgo) => (
            <li className="panel-critical-list__item--link" key={hallazgo.id}>
              <SeverityBadge severidad={hallazgo.severidad} />
              <div>
                <strong>Hallazgo #{hallazgo.id} · Sin {hallazgo.epp_faltante.map((epp) => nombresEpp[epp]).join(" y ")}</strong>
                <span>{hallazgo.area?.nombre ?? "Sin área"} / {hallazgo.zona?.nombre ?? "Sin zona"} · {hallazgo.fuente?.nombre ?? "Sin fuente"}</span>
              </div>
              <time className="mono" dateTime={hallazgo.ts_inicio}>{formatoFecha.format(new Date(hallazgo.ts_inicio))}</time>
              <button className="panel-row-action" type="button" aria-label={`Ver hallazgo #${hallazgo.id}`} onClick={() => onNavigateHallazgos({ vista: "todos", severidad: 4, hallazgoId: hallazgo.id })} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function CoberturaOperacional({ cobertura }: { cobertura: Panel["cobertura"] }) {
  const activas = cobertura.fuentes_activas ?? 0;
  const total = cobertura.fuentes_totales ?? 0;
  const sinCobertura = cobertura.sin_cobertura ?? [];
  const completa = total > 0 && activas >= total && sinCobertura.length === 0;

  return (
    <section className="panel-operation panel-coverage" aria-labelledby="panel-cobertura-title">
      <header><div><p className="eyebrow">VISIBILIDAD OPERACIONAL</p><h3 id="panel-cobertura-title">Cobertura</h3></div><RadioTower size={18} aria-hidden="true" /></header>
      <strong className="panel-coverage__count mono">{activas} de {total}</strong>
      <span>fuentes activas</span>
      <progress value={Math.min(activas, Math.max(total, 1))} max={Math.max(total, 1)} aria-label={`${activas} de ${total} fuentes activas`} />
      {total === 0 && <p className="panel-operation__empty">Sin fuentes configuradas.</p>}
      {completa && <p className="panel-coverage__complete">Cobertura completa</p>}
      {sinCobertura.length > 0 && (
        <div className="panel-coverage__warning">
          <p><AlertTriangle size={15} aria-hidden="true" /> Fuentes sin cobertura</p>
          <ul aria-label="Fuentes sin cobertura">
            {sinCobertura.map((item, indice) => (
              <li key={`${item.fuente?.id ?? "fuente"}-${indice}`}>
                <strong>{item.fuente?.nombre ?? "Fuente sin identificar"}</strong>
                <span>{item.motivo ? motivosCobertura[item.motivo] : "Motivo no informado"}</span>
                {item.desde && <time dateTime={item.desde}>Desde {formatoFecha.format(new Date(item.desde))}</time>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export function PanelOperations({ criticos, cobertura, onNavigateHallazgos }: PanelOperationsProps) {
  return <section className="panel-operations" aria-label="Críticos recientes y cobertura" data-panel-band="operacion"><CriticosRecientes criticos={criticos} onNavigateHallazgos={onNavigateHallazgos} /><CoberturaOperacional cobertura={cobertura} /></section>;
}
