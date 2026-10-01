import { AlertTriangle, LoaderCircle } from "lucide-react";

import type { Catalogos, FiltrosPanel, Panel } from "../api/types";
import type { DestinoHallazgos } from "../hooks/useAppNavigation";
import { PanelCharts } from "./PanelCharts";
import { PanelFilters } from "./PanelFilters";
import { PanelOperations } from "./PanelOperations";

interface PanelPageProps {
  panel?: Panel;
  filtros?: FiltrosPanel;
  catalogos?: Catalogos;
  isLoading: boolean;
  isError: boolean;
  sinPermiso: boolean;
  onRetry: () => void;
  onChangeFilters?: (cambios: Partial<FiltrosPanel>) => void;
  onNavigateHallazgos: (destino: DestinoHallazgos) => void;
}

const destinoIndicador: Partial<Record<Panel["indicadores"][number]["clave"], DestinoHallazgos>> = {
  hallazgos_abiertos: { vista: "por_revisar" },
  criticos_sin_revisar: { vista: "por_revisar", severidad: 4 },
};

function variacionTexto(variacion: number | null | undefined): string {
  if (variacion === null || variacion === undefined) return "Sin comparación";
  const porcentaje = Math.round(Math.abs(variacion) * 100);
  return `${variacion >= 0 ? "↑ +" : "↓ −"}${porcentaje}% vs. período anterior`;
}

function Sparkline({ etiqueta, serie }: { etiqueta: string; serie?: number[] }) {
  if (!serie?.length) return <span className="panel-sparkline panel-sparkline--empty">Sin tendencia</span>;
  const maximo = Math.max(...serie, 1);
  const puntos = serie.map((valor, indice) => {
    const x = serie.length === 1 ? 30 : (indice / (serie.length - 1)) * 60;
    const y = 19 - (valor / maximo) * 17;
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg className="panel-sparkline" viewBox="0 0 60 20" role="img" aria-label={`Tendencia de ${etiqueta}: ${serie.join(", ")}`}>
      <polyline points={puntos} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function PanelPage({ panel, filtros, catalogos, isLoading, isError, sinPermiso, onRetry, onChangeFilters, onNavigateHallazgos }: PanelPageProps) {
  const panelVacio = !panel || (
    panel.indicadores.length === 0
    && (panel.tendencia.series ?? []).length === 0
    && panel.ranking_epp.length === 0
    && panel.criticos_recientes.length === 0
    && (panel.cobertura.fuentes_totales ?? 0) === 0
  );
  const mostrarError = !isLoading && isError;
  const mostrarSinPermiso = !isLoading && !isError && sinPermiso;
  const mostrarVacio = !isLoading && !isError && !sinPermiso && panelVacio;
  const mostrarPanel = !isLoading && !isError && !sinPermiso && !panelVacio && panel;

  return (
    <main className="panel-page" aria-labelledby="panel-page-title" aria-busy={isLoading}>
      <div className="review-heading panel-heading">
        <div>
          <p className="eyebrow">VISIÓN GENERAL</p>
          <h2 id="panel-page-title">Panel general</h2>
        </div>
      </div>

      {filtros && onChangeFilters && <PanelFilters filtros={filtros} catalogos={catalogos} onChange={onChangeFilters} />}

      {isLoading && <div className="state-message" role="status" aria-live="polite"><LoaderCircle className="spin" aria-hidden="true" /> Cargando panel…</div>}
      {mostrarError && (
        <div className="state-message state-message--error" role="alert">
          <AlertTriangle aria-hidden="true" />
          No fue posible cargar el panel general.
          <button type="button" onClick={onRetry}>Reintentar</button>
        </div>
      )}
      {mostrarSinPermiso && <div className="state-message" role="alert"><AlertTriangle aria-hidden="true" /> No tienes permiso para ver el panel general.</div>}
      {mostrarVacio && <div className="state-message" role="status">No hay información disponible para el período seleccionado.</div>}
      {mostrarPanel && (
        <>
          <section className="panel-indicators" aria-label="Indicadores del panel" data-panel-band="indicadores">
            {panel.indicadores.map((indicador) => (
              <article className={`panel-indicator ${destinoIndicador[indicador.clave] ? "panel-indicator--link" : ""}`} key={indicador.clave} aria-labelledby={`indicador-${indicador.clave}`}>
                <h3 id={`indicador-${indicador.clave}`}>{indicador.etiqueta}</h3>
                <strong className="panel-indicator__value mono">
                  {indicador.valor}{indicador.unidad ? <small>{indicador.unidad}</small> : null}
                </strong>
                <span className="panel-indicator__variation">{variacionTexto(indicador.variacion)}</span>
                <Sparkline etiqueta={indicador.etiqueta} serie={indicador.serie} />
                {destinoIndicador[indicador.clave] && <button className="panel-card-action" type="button" aria-label={`Ver ${indicador.etiqueta} en Hallazgos`} onClick={() => onNavigateHallazgos(destinoIndicador[indicador.clave]!)} />}
              </article>
            ))}
          </section>
          <PanelCharts tendencia={panel.tendencia} rankingEpp={panel.ranking_epp} onNavigateHallazgos={onNavigateHallazgos} />
          <PanelOperations criticos={panel.criticos_recientes} cobertura={panel.cobertura} onNavigateHallazgos={onNavigateHallazgos} />
        </>
      )}
    </main>
  );
}
