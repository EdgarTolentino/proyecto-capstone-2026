import { AlertTriangle, LoaderCircle } from "lucide-react";

import type { Panel } from "../api/types";

interface PanelPageProps {
  panel?: Panel;
  isLoading: boolean;
  isError: boolean;
  sinPermiso: boolean;
  onRetry: () => void;
}

function variacionTexto(variacion: number | null | undefined): string {
  if (variacion === null || variacion === undefined) return "Sin comparación";
  const porcentaje = Math.round(Math.abs(variacion) * 100);
  return `${variacion >= 0 ? "↑ +" : "↓ −"}${porcentaje}% vs. período anterior`;
}

function Sparkline({ serie }: { serie?: number[] }) {
  if (!serie?.length) return <span className="panel-sparkline panel-sparkline--empty">Sin tendencia</span>;
  const maximo = Math.max(...serie, 1);
  const puntos = serie.map((valor, indice) => {
    const x = serie.length === 1 ? 30 : (indice / (serie.length - 1)) * 60;
    const y = 19 - (valor / maximo) * 17;
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg className="panel-sparkline" viewBox="0 0 60 20" role="img" aria-label="Tendencia del indicador">
      <polyline points={puntos} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function PanelPage({ panel, isLoading, isError, sinPermiso, onRetry }: PanelPageProps) {
  return (
    <main className="panel-page" aria-labelledby="panel-page-title">
      <div className="review-heading panel-heading">
        <div>
          <p className="eyebrow">VISIÓN GENERAL</p>
          <h2 id="panel-page-title">Panel general</h2>
        </div>
      </div>

      {sinPermiso && <div className="state-message" role="alert">No tienes permiso para ver el panel general.</div>}
      {isLoading && <div className="state-message"><LoaderCircle className="spin" /> Cargando panel…</div>}
      {isError && (
        <div className="state-message state-message--error" role="alert">
          <AlertTriangle />
          No fue posible cargar el panel general.
          <button type="button" onClick={onRetry}>Reintentar</button>
        </div>
      )}
      {!isLoading && !isError && panel && (
        <section className="panel-indicators" aria-label="Indicadores del panel">
          {panel.indicadores.map((indicador) => (
            <article className="panel-indicator" key={indicador.clave}>
              <p>{indicador.etiqueta}</p>
              <strong className="panel-indicator__value mono">
                {indicador.valor}{indicador.unidad ? <small>{indicador.unidad}</small> : null}
              </strong>
              <span className="panel-indicator__variation">{variacionTexto(indicador.variacion)}</span>
              <Sparkline serie={indicador.serie} />
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
