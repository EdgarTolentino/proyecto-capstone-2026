import type { CSSProperties } from "react";

import type { Panel, Severidad, TipoEpp } from "../api/types";
import type { DestinoHallazgos } from "../hooks/useAppNavigation";
import { SeverityBadge } from "./SeverityBadge";

interface PanelChartsProps {
  tendencia: Panel["tendencia"];
  rankingEpp: Panel["ranking_epp"];
  onNavigateHallazgos: (destino: DestinoHallazgos) => void;
}

const nombreSeveridad: Record<Severidad, string> = {
  4: "Crítica",
  3: "Alta",
  2: "Media",
  1: "Baja",
};

const nombreEpp: Record<string, string> = {
  casco: "Casco",
  chaleco: "Chaleco",
  lentes: "Lentes",
  guantes: "Guantes",
  arnes: "Arnés",
  calzado: "Calzado",
  otros: "Otros",
};

const eppFiltrables = new Set<TipoEpp>(["casco", "chaleco", "lentes", "guantes", "arnes", "calzado"]);

function esEppFiltrable(epp: string | undefined): epp is TipoEpp {
  return epp !== undefined && eppFiltrables.has(epp as TipoEpp);
}

function TendenciaSemanal({ tendencia, onNavigateHallazgos }: { tendencia: Panel["tendencia"]; onNavigateHallazgos: PanelChartsProps["onNavigateHallazgos"] }) {
  const etiquetas = tendencia.etiquetas ?? [];
  const series = (tendencia.series ?? []).flatMap((serie) =>
    serie.severidad === undefined
      ? []
      : [{ severidad: serie.severidad, valores: serie.valores ?? [] }],
  ).slice(0, 4);
  const totalPuntos = Math.max(etiquetas.length, ...series.map((serie) => serie.valores.length), 1);
  const maximo = Math.max(...series.flatMap((serie) => serie.valores), 1);
  const ancho = 600;
  const alto = 220;
  const margen = { arriba: 16, derecha: 12, abajo: 30, izquierda: 34 };
  const anchoGrafico = ancho - margen.izquierda - margen.derecha;
  const altoGrafico = alto - margen.arriba - margen.abajo;
  const x = (indice: number) => margen.izquierda + (totalPuntos === 1 ? anchoGrafico / 2 : (indice / (totalPuntos - 1)) * anchoGrafico);
  const y = (valor: number) => margen.arriba + altoGrafico - (valor / maximo) * altoGrafico;

  return (
    <section className="panel-chart" aria-labelledby="panel-trend-title">
      <header>
        <div><p className="eyebrow">EVOLUCIÓN</p><h3 id="panel-trend-title">Tendencia semanal por severidad</h3></div>
        <div className="panel-chart__legend" aria-label="Leyenda de severidades">
          {series.map((serie, indice) => <button className="panel-chart__filter" type="button" key={`${serie.severidad}-${indice}`} aria-label={`Ver hallazgos de severidad ${nombreSeveridad[serie.severidad]}`} onClick={() => onNavigateHallazgos({ vista: "todos", severidad: serie.severidad })}><SeverityBadge severidad={serie.severidad} /></button>)}
        </div>
      </header>
      {series.length === 0 ? <p className="panel-chart__empty">Sin datos de tendencia.</p> : (
        <>
          <svg className="panel-trend" viewBox={`0 0 ${ancho} ${alto}`} role="img" aria-label="Gráfico de tendencia semanal por severidad">
            {[0, 0.5, 1].map((proporcion) => (
              <line key={proporcion} className="panel-trend__grid" x1={margen.izquierda} x2={ancho - margen.derecha} y1={y(maximo * proporcion)} y2={y(maximo * proporcion)} />
            ))}
            {etiquetas.map((etiqueta, indice) => <text key={`${etiqueta}-${indice}`} className="panel-trend__label" x={x(indice)} y={alto - 8} textAnchor="middle">{etiqueta}</text>)}
            {series.map((serie, indice) => (
              <polyline
                key={`${serie.severidad}-${indice}`}
                className={`panel-trend__line panel-trend__line--${serie.severidad}`}
                points={serie.valores.map((valor, punto) => `${x(punto)},${y(valor)}`).join(" ")}
                fill="none"
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </svg>
          <table className="sr-only">
            <caption>Datos de tendencia semanal por severidad</caption>
            <thead><tr><th>Severidad</th>{etiquetas.map((etiqueta, indice) => <th key={`${etiqueta}-${indice}`}>{etiqueta}</th>)}</tr></thead>
            <tbody>{series.map((serie, indice) => <tr key={`${serie.severidad}-${indice}`}><th>{nombreSeveridad[serie.severidad]}</th>{etiquetas.map((_etiqueta, punto) => <td key={punto}>{serie.valores[punto] ?? 0}</td>)}</tr>)}</tbody>
          </table>
        </>
      )}
    </section>
  );
}

function RankingEpp({ ranking, onNavigateHallazgos }: { ranking: Panel["ranking_epp"]; onNavigateHallazgos: PanelChartsProps["onNavigateHallazgos"] }) {
  const principales = ranking.filter((item) => item.epp !== "otros").slice(0, 5);
  const otros = ranking.find((item) => item.epp === "otros");
  const items = otros ? [...principales, otros] : principales;
  const maximo = Math.max(...items.map((item) => item.total ?? 0), 1);

  return (
    <section className="panel-chart" aria-labelledby="panel-ranking-title">
      <header><div><p className="eyebrow">INCUMPLIMIENTOS</p><h3 id="panel-ranking-title">Ranking de EPP incumplido</h3></div></header>
      {items.length === 0 ? <p className="panel-chart__empty">Sin incumplimientos registrados.</p> : (
        <ol className="panel-ranking" aria-label="Ranking de EPP incumplido">
          {items.map((item, indice) => {
            const total = item.total ?? 0;
            const etiqueta = nombreEpp[item.epp ?? ""] ?? item.epp ?? "Sin clasificar";
            const epp = esEppFiltrable(item.epp) ? item.epp : undefined;
            return (
              <li className={epp ? "panel-ranking__item--link" : undefined} key={`${item.epp ?? "sin-clasificar"}-${indice}`}>
                <span>{etiqueta}</span>
                <span className="panel-ranking__track" aria-hidden="true"><i style={{ "--ranking-width": `${(total / maximo) * 100}%` } as CSSProperties} /></span>
                <strong className="mono">{total}</strong>
                {epp && <button className="panel-row-action" type="button" aria-label={`Ver hallazgos sin ${etiqueta}`} onClick={() => onNavigateHallazgos({ vista: "todos", epp })} />}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

export function PanelCharts({ tendencia, rankingEpp, onNavigateHallazgos }: PanelChartsProps) {
  return <section className="panel-charts" aria-label="Tendencia y ranking del panel" data-panel-band="analisis"><TendenciaSemanal tendencia={tendencia} onNavigateHallazgos={onNavigateHallazgos} /><RankingEpp ranking={rankingEpp} onNavigateHallazgos={onNavigateHallazgos} /></section>;
}
