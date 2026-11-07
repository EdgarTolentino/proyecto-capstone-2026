import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download, LoaderCircle } from "lucide-react";
import { useState } from "react";

import { ApiError, descargarReporteCsv, obtenerReporte } from "../api/client";
import type { Reporte } from "../api/types";

interface Props {
  desde?: string;
  hasta?: string;
  areaId?: number;
}

type Fila = Reporte["filas"][number];

const razones: Record<NonNullable<Fila["razon"]>, string> = {
  n_insuficiente: "Menos de 5 incumplimientos",
  sin_dotacion: "Sin dotación registrada",
  dotacion_insuficiente: "Dotación menor a 5 personas",
  dotacion_incompleta: "Faltan días de dotación en el período",
};

const formatoTasa = new Intl.NumberFormat("es-CL", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function tasa(fila: Fila): string {
  if (fila.datos_insuficientes || fila.valor == null) {
    const motivo = fila.razon ? razones[fila.razon] : "Sin tasa disponible";
    return `Datos insuficientes — ${motivo}`;
  }
  return `${formatoTasa.format(fila.valor)} por cada 100 trabajadores`;
}

function composicion(fila: Fila) {
  const dato = fila.dotacion;
  if (!dato) return "—";
  if (dato.hombres == null || dato.mujeres == null || dato.otro == null) {
    return "No se muestra para proteger a grupos de menos de 5 personas";
  }
  return `Hombres: ${dato.hombres} · Mujeres: ${dato.mujeres} · Otro: ${dato.otro}`;
}

export function ReporteDotacion({ desde, hasta, areaId }: Props) {
  const [descargando, setDescargando] = useState(false);
  const [errorCsv, setErrorCsv] = useState("");
  const consulta = useQuery({
    queryKey: ["reporte-dotacion", { desde, hasta, areaId }],
    queryFn: () => obtenerReporte("dotacion", { desde, hasta, areaId, segmentacion: "turno" }),
    placeholderData: keepPreviousData,
  });
  const filas = consulta.data?.filas ?? [];
  const sinPermiso = consulta.error instanceof ApiError && [401, 403].includes(consulta.error.status);
  const cargaInicial = consulta.isLoading;
  const actualizando = consulta.isFetching && !cargaInicial;

  async function descargarCsv() {
    setDescargando(true);
    setErrorCsv("");
    try {
      const csv = await descargarReporteCsv("dotacion", { desde, hasta, areaId, segmentacion: "turno" });
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = "reporte-dotacion.csv";
      enlace.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (error) {
      setErrorCsv(error instanceof Error ? error.message : "No fue posible descargar el CSV.");
    } finally {
      setDescargando(false);
    }
  }

  return (
    <section className="reporte-dotacion" aria-labelledby="reporte-dotacion-title" aria-busy={consulta.isFetching}>
      <div className="reporte-dotacion__heading">
        <h4 id="reporte-dotacion-title">Tasa por dotación</h4>
        <button className="reportes-csv" type="button" onClick={() => void descargarCsv()} disabled={descargando || consulta.isFetching || consulta.isError || !consulta.data}>
          {descargando ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Download size={15} aria-hidden="true" />}
          {descargando ? "Descargando…" : "Exportar CSV"}
        </button>
      </div>
      <p className="reportes-page__note">Dotación del turno (dato de RR. HH., no se infiere de la imagen).</p>
      <p className="reportes-page__demo">Información sintética para fines de demostración.</p>
      {errorCsv && <div className="state-message state-message--error" role="alert">{errorCsv}</div>}
      {cargaInicial && <div className="state-message" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Cargando reporte de dotación…</div>}
      {actualizando && <p className="reporte-dotacion__loading" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Actualizando datos…</p>}
      {!consulta.isFetching && consulta.isError && !sinPermiso && <div className="state-message state-message--error" role="alert"><AlertTriangle aria-hidden="true" /> No fue posible cargar el reporte de dotación. <button type="button" onClick={() => void consulta.refetch()}>Reintentar</button></div>}
      {!consulta.isFetching && sinPermiso && <div className="state-message" role="alert">No tienes permiso para ver el reporte de dotación.</div>}
      {!consulta.isFetching && consulta.isSuccess && filas.length === 0 && <div className="state-message" role="status">No hay información de dotación para los filtros seleccionados.</div>}
      {filas.length > 0 && !consulta.isError && (
        <>
          <p className="reportes-notice"><AlertTriangle size={14} aria-hidden="true" />Las tasas protegidas se muestran como «Datos insuficientes»; la supresión se aplica en el servidor.</p>
          <div className="reportes-table-wrap">
            <table className="reportes-table">
              <caption>Incumplimientos por cada 100 trabajadores, agrupados por área y turno</caption>
              <thead><tr><th scope="col">Área y turno</th><th scope="col">Tasa</th><th scope="col">Incumplimientos</th><th scope="col">Dotación</th><th scope="col">Composición</th></tr></thead>
              <tbody>{filas.map((fila) => (
                <tr key={fila.etiqueta}>
                  <th scope="row">{fila.etiqueta}</th>
                  <td>{tasa(fila)}</td>
                  <td>{fila.n == null ? "—" : `≈ ${fila.n}`}</td>
                  <td>{fila.dotacion?.total == null ? "—" : `${fila.dotacion.total} ${fila.dotacion.total === 1 ? "persona" : "personas"}`}</td>
                  <td>{composicion(fila)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
