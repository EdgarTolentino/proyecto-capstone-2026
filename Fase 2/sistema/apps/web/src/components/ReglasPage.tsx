import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, LoaderCircle } from "lucide-react";
import { useMemo, useState } from "react";

import { listarReglas } from "../api/client";
import type { Catalogos } from "../api/types";

interface ReglasPageProps {
  catalogos?: Catalogos;
}

export function ReglasPage({ catalogos }: ReglasPageProps) {
  const [areaId, setAreaId] = useState("");
  const reglas = useQuery({
    queryKey: ["reglas", { areaId: areaId || undefined }],
    queryFn: () => listarReglas(areaId || undefined),
  });
  const nombresArea = useMemo(
    () => new Map(
      catalogos?.areas?.flatMap((area) => area?.id && area.nombre ? [[area.id, area.nombre] as const] : []) ?? [],
    ),
    [catalogos?.areas],
  );

  return (
    <main className="rules-page">
      <div className="review-heading rules-heading">
        <div>
          <p className="eyebrow">CONFIGURACIÓN OPERACIONAL</p>
          <h2>Reglas de seguridad</h2>
          <p>Consulta las reglas vigentes por área, su estado y la versión aplicada.</p>
        </div>
      </div>

      <div className="filters rules-filters" aria-label="Filtros de reglas">
        <label className="select-filter">
          <span className="sr-only">Área</span>
          <select value={areaId} onChange={(event) => setAreaId(event.target.value)}>
            <option value="">Todas las áreas</option>
            {catalogos?.areas?.map((area) => area && (
              <option key={area.id} value={area.id}>{area.nombre}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="results-bar">
        <div className="result-summary" aria-live="polite">
          {reglas.data ? `${reglas.data.length} ${reglas.data.length === 1 ? "regla" : "reglas"} en esta vista` : "Consultando reglas…"}
        </div>
        <span className="rules-readonly">Vista de consulta</span>
      </div>

      {reglas.isLoading && (
        <div className="state-message" role="status"><LoaderCircle className="spin" /> Cargando reglas…</div>
      )}
      {reglas.isError && (
        <div className="state-message state-message--error" role="alert">
          <AlertTriangle />
          No fue posible cargar las reglas.
          <button type="button" onClick={() => void reglas.refetch()}>Reintentar</button>
        </div>
      )}
      {reglas.data && reglas.data.length === 0 && (
        <div className="state-message">No hay reglas para el área seleccionada.</div>
      )}
      {reglas.data && reglas.data.length > 0 && (
        <div className="rules-table-wrap">
          <table className="rules-table">
            <caption className="sr-only">Listado de reglas de seguridad</caption>
            <thead>
              <tr><th scope="col">Nombre</th><th scope="col">Área</th><th scope="col">Estado</th><th scope="col">Versión</th></tr>
            </thead>
            <tbody>
              {reglas.data.map((regla) => (
                <tr key={regla.id}>
                  <th scope="row">{regla.nombre}</th>
                  <td>{nombresArea.get(regla.area_id) ?? `Área #${regla.area_id}`}</td>
                  <td><span className={`rule-status rule-status--${regla.activa ? "active" : "inactive"}`}>{regla.activa ? "Activa" : "Inactiva"}</span></td>
                  <td className="mono">Versión {regla.version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
