import { AlertTriangle, Download, LoaderCircle, RotateCcw } from "lucide-react";
import { useState } from "react";

import type { Catalogos, FiltrosReporte, Reporte, SegmentacionReporte, TipoReporte } from "../api/types";

interface Props {
  reporte?: Reporte;
  tipo: TipoReporte;
  filtros: FiltrosReporte;
  catalogos?: Catalogos;
  isLoading: boolean;
  isError: boolean;
  sinPermiso: boolean;
  onRetry: () => void;
  onChangeTipo: (tipo: TipoReporte) => void;
  onChangeFilters: (cambios: Partial<FiltrosReporte>) => void;
  onDownloadCsv: () => Promise<string>;
}

const reportes = [
  { tipo: "ranking-epp", etiqueta: "Por EPP", titulo: "Incumplimientos por EPP", descripcion: "Elementos de protección personal con más incumplimientos." },
  { tipo: "zonas", etiqueta: "Por zona", titulo: "Incumplimientos por zona", descripcion: "Ranking de zonas y tendencia de las últimas ocho semanas." },
] as const;
const segmentaciones: { valor: SegmentacionReporte; etiqueta: string }[] = [
  { valor: "zona", etiqueta: "Zona" },
  { valor: "turno", etiqueta: "Turno" },
  { valor: "camara", etiqueta: "Cámara" },
  { valor: "epp", etiqueta: "Tipo de EPP" },
];
const etiquetaSegmentacion: Record<SegmentacionReporte, string> = {
  zona: "zona",
  turno: "turno",
  camara: "cámara",
  epp: "EPP",
};

function valorPublicado(fila: Reporte["filas"][number]): number | null {
  return fila.datos_insuficientes || fila.valor == null ? null : fila.valor;
}

function textoValor(fila: Reporte["filas"][number]): string {
  const valor = valorPublicado(fila);
  return valor === null ? "Datos insuficientes" : valor.toLocaleString("es-CL", { maximumFractionDigits: 2 });
}

function Minigrafico({ valores, etiqueta }: { valores: number[]; etiqueta: string }) {
  const maximo = Math.max(...valores, 1);
  const puntos = valores.map((valor, indice) => {
    const x = valores.length === 1 ? 2 : (indice / (valores.length - 1)) * 56 + 2;
    return `${x},${18 - (valor / maximo) * 16}`;
  }).join(" ");
  return <svg className="reportes-sparkline" viewBox="0 0 60 20" role="img" aria-label={`Tendencia de ocho semanas de ${etiqueta}`}><polyline points={puntos} fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
}

function Grafico({ filas, tipo, segmentacion }: { filas: Reporte["filas"]; tipo: TipoReporte; segmentacion: SegmentacionReporte }) {
  const maximo = Math.max(...filas.map((fila) => valorPublicado(fila) ?? 0), 0);
  return (
    <section className="reportes-ranking" aria-label={`Gráfico de incumplimientos por ${etiquetaSegmentacion[segmentacion]}`}>
      {filas.map((fila) => {
        const valor = valorPublicado(fila);
        return (
          <div className="reportes-ranking__row" key={fila.etiqueta}>
            <span className="reportes-ranking__label">{fila.etiqueta}</span>
            <div className="reportes-ranking__track" aria-hidden="true">
              {valor !== null && maximo > 0 && <span className="reportes-ranking__bar" style={{ width: `${(valor / maximo) * 100}%` }} />}
            </div>
            <span className="reportes-ranking__value mono">{textoValor(fila)}</span>
            {tipo === "zonas" && fila.serie && <Minigrafico valores={fila.serie} etiqueta={fila.etiqueta} />}
          </div>
        );
      })}
    </section>
  );
}

function Tabla({ filas, tipo, titulo }: { filas: Reporte["filas"]; tipo: TipoReporte; titulo: string }) {
  const incluyeSerie = tipo === "zonas" && filas.some((fila) => fila.serie);
  return (
    <div className="reportes-table-wrap">
      <table className="reportes-table">
        <caption>Detalle del reporte: {titulo}</caption>
        <thead><tr><th scope="col">Dimensión</th><th scope="col">Incumplimientos</th>{incluyeSerie && <th scope="col">Últimas ocho semanas</th>}</tr></thead>
        <tbody>{filas.map((fila) => (
          <tr key={fila.etiqueta}>
            <th scope="row">{fila.etiqueta}</th>
            <td className="mono">{textoValor(fila)}</td>
            {incluyeSerie && <td>{fila.serie ? <Minigrafico valores={fila.serie} etiqueta={fila.etiqueta} /> : "Serie no disponible"}</td>}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export function ReportesPage({
  reporte, tipo, filtros, catalogos, isLoading, isError, sinPermiso,
  onRetry, onChangeTipo, onChangeFilters, onDownloadCsv,
}: Props) {
  const [descargando, setDescargando] = useState(false);
  const [errorCsv, setErrorCsv] = useState("");
  const actual = reportes.find((item) => item.tipo === tipo) ?? reportes[0];
  const segmentacion = filtros.segmentacion ?? (tipo === "ranking-epp" ? "epp" : "zona");
  const titulo = segmentacion === (tipo === "ranking-epp" ? "epp" : "zona")
    ? actual.titulo
    : `Ranking por ${etiquetaSegmentacion[segmentacion]}`;
  const filas = reporte?.filas ?? [];

  async function descargarCsv() {
    setDescargando(true);
    setErrorCsv("");
    try {
      const url = URL.createObjectURL(new Blob([await onDownloadCsv()], { type: "text/csv;charset=utf-8" }));
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = `reporte-${tipo}.csv`;
      enlace.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (error) {
      setErrorCsv(error instanceof Error ? error.message : "No fue posible descargar el CSV.");
    } finally {
      setDescargando(false);
    }
  }

  return (
    <main className="reportes-page" aria-labelledby="reportes-page-title" aria-busy={isLoading}>
      <div className="review-heading panel-heading"><div><p className="eyebrow">INDICADORES AGREGADOS</p><h2 id="reportes-page-title">Reportes</h2></div></div>
      <div className="reportes-tabs" role="tablist" aria-label="Tipo de reporte">
        {reportes.map((item, index) => (
          <button
            type="button" role="tab" id={`tab-${item.tipo}`} aria-selected={tipo === item.tipo}
            aria-controls="reporte-panel" tabIndex={tipo === item.tipo ? 0 : -1}
            className={tipo === item.tipo ? "reportes-tabs__tab is-active" : "reportes-tabs__tab"}
            key={item.tipo} onClick={() => onChangeTipo(item.tipo)}
            onKeyDown={(event) => {
              if (!["ArrowRight", "ArrowLeft"].includes(event.key)) return;
              event.preventDefault();
              const next = reportes[(index + (event.key === "ArrowRight" ? 1 : reportes.length - 1)) % reportes.length];
              onChangeTipo(next.tipo);
              document.getElementById(`tab-${next.tipo}`)?.focus();
            }}
          >{item.etiqueta}</button>
        ))}
      </div>
      <section id="reporte-panel" role="tabpanel" aria-labelledby={`tab-${tipo}`} className="reportes-kpi">
        <div className="reportes-kpi__heading">
          <div><p className="eyebrow">REPORTE AGREGADO</p><h3>{titulo}</h3><p>{actual.descripcion}</p></div>
          <button className="reportes-csv" type="button" onClick={() => void descargarCsv()} disabled={descargando || isLoading || !reporte}>
            {descargando ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Download size={15} aria-hidden="true" />}
            {descargando ? "Descargando…" : "Exportar CSV"}
          </button>
        </div>
        <div className="filters reportes-filtros" role="group" aria-label="Filtros de reportes">
          <label className="date-filter"><span>Desde</span><input type="date" value={filtros.desde ?? ""} max={filtros.hasta} onChange={(event) => {
            const desde = event.target.value || undefined;
            onChangeFilters({ desde, ...(desde && filtros.hasta && desde > filtros.hasta ? { hasta: undefined } : {}) });
          }} /></label>
          <label className="date-filter"><span>Hasta</span><input type="date" value={filtros.hasta ?? ""} min={filtros.desde} onChange={(event) => {
            const hasta = event.target.value || undefined;
            onChangeFilters({ hasta, ...(hasta && filtros.desde && hasta < filtros.desde ? { desde: undefined } : {}) });
          }} /></label>
          <label className="select-filter"><span>Área</span><select value={filtros.areaId ?? ""} onChange={(event) => onChangeFilters({ areaId: event.target.value ? Number(event.target.value) : undefined })}>
            <option value="">Todas las áreas</option>{catalogos?.areas?.map((area) => area && <option key={area.id} value={area.id}>{area.nombre}</option>)}
          </select></label>
          <label className="select-filter"><span>Segmentar por</span><select value={segmentacion} onChange={(event) => onChangeFilters({ segmentacion: event.target.value as SegmentacionReporte })}>
            {segmentaciones.map((item) => <option value={item.valor} key={item.valor}>{item.etiqueta}</option>)}
          </select></label>
          <button className="icon-button" type="button" aria-label="Restablecer filtros de reportes" onClick={() => onChangeFilters({ desde: undefined, hasta: undefined, areaId: undefined, segmentacion: undefined })}><RotateCcw size={14} aria-hidden="true" /></button>
        </div>
        {errorCsv && <div className="state-message state-message--error" role="alert">{errorCsv}</div>}
        {isLoading && <div className="state-message" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Cargando reporte…</div>}
        {!isLoading && isError && <div className="state-message state-message--error" role="alert"><AlertTriangle aria-hidden="true" /> No fue posible cargar el reporte. <button type="button" onClick={onRetry}>Reintentar</button></div>}
        {!isLoading && !isError && sinPermiso && <div className="state-message" role="alert">No tienes permiso para ver reportes.</div>}
        {!isLoading && !isError && !sinPermiso && reporte && filas.length === 0 && <div className="state-message" role="status">No hay información para los filtros seleccionados.</div>}
        {!isLoading && !isError && !sinPermiso && filas.length > 0 && (
          <>
            <p className="reportes-notice"><AlertTriangle size={14} aria-hidden="true" />Las celdas con población menor que 5 se muestran como «Datos insuficientes»; la supresión se aplica en el servidor.</p>
            <Grafico filas={filas} tipo={tipo} segmentacion={segmentacion} />
            <Tabla filas={filas} tipo={tipo} titulo={titulo} />
          </>
        )}
      </section>
    </main>
  );
}
