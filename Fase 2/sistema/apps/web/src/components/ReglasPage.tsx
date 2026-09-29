import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, LoaderCircle, Plus } from "lucide-react";
import { useMemo, useState } from "react";

import { actualizarRegla, ApiError, crearRegla, listarReglas, simularRegla } from "../api/client";
import type { Catalogos, Regla, ReglaEntrada } from "../api/types";
import { ReglaEditor } from "./ReglaEditor";

interface ReglasPageProps { catalogos?: Catalogos; puedeEditar: boolean; }

export function ReglasPage({ catalogos, puedeEditar }: ReglasPageProps) {
  const queryClient = useQueryClient();
  const [areaId, setAreaId] = useState("");
  const [editando, setEditando] = useState<Regla | "nueva" | null>(null);
  const [mensaje, setMensaje] = useState("");
  const reglas = useQuery({ queryKey: ["reglas", { areaId: areaId || undefined }], queryFn: () => listarReglas(areaId || undefined) });
  const nombresArea = useMemo(() => new Map(catalogos?.areas?.flatMap((area) => area?.id && area.nombre ? [[area.id, area.nombre] as const] : []) ?? []), [catalogos?.areas]);
  const guardar = useMutation({
    mutationFn: (entrada: ReglaEntrada) => editando === "nueva" ? crearRegla(entrada) : actualizarRegla(editando!.id, entrada),
    onSuccess: async (regla) => {
      setMensaje(editando === "nueva" ? `Regla creada en versión ${regla.version}.` : `Nueva versión ${regla.version} guardada.`);
      setEditando(null);
      await queryClient.invalidateQueries({ queryKey: ["reglas"] });
    },
  });
  const simulacion = useMutation({
    mutationFn: ({ id, desde, hasta, regla }: { id: number; desde: string; hasta: string; regla: ReglaEntrada }) => simularRegla(id, { desde, hasta, regla }),
  });
  const errorGuardar = guardar.error instanceof ApiError ? guardar.error.message : guardar.isError ? "No pudimos guardar la regla. Intenta nuevamente." : undefined;
  const abrirEditor = (seleccion: Regla | "nueva") => {
    setMensaje("");
    guardar.reset();
    simulacion.reset();
    setEditando(seleccion);
  };

  return <main className="rules-page">
    <div className="review-heading rules-heading"><div><p className="eyebrow">CONFIGURACIÓN OPERACIONAL</p><h2>Reglas de seguridad</h2><p>Consulta{puedeEditar ? ", crea y actualiza" : ""} la configuración por área.</p></div>{puedeEditar && <button type="button" className="primary-button" onClick={() => abrirEditor("nueva")}><Plus size={16} />Nueva regla</button>}</div>
    {puedeEditar && editando && <ReglaEditor key={editando === "nueva" ? "nueva" : editando.id} catalogos={catalogos} regla={editando === "nueva" ? undefined : editando} guardando={guardar.isPending} error={errorGuardar} simulando={simulacion.isPending} resultadoSimulacion={simulacion.data} errorSimulacion={simulacion.isError ? "No pudimos ejecutar la simulación. Intenta nuevamente." : undefined} onCancel={() => { setEditando(null); guardar.reset(); simulacion.reset(); }} onSubmit={(entrada) => guardar.mutate(entrada)} onSimular={({ desde, hasta, regla }) => { if (editando !== "nueva") simulacion.mutate({ id: editando.id, desde, hasta, regla }); }} />}
    <div className="filters rules-filters" aria-label="Filtros de reglas"><label className="select-filter"><span>Área</span><select value={areaId} onChange={(event) => setAreaId(event.target.value)}><option value="">Todas las áreas</option>{catalogos?.areas?.map((area) => area && <option key={area.id} value={area.id}>{area.nombre}</option>)}</select></label></div>
    <div className="results-bar"><div className="result-summary" aria-live="polite">{reglas.data ? `${reglas.data.length} ${reglas.data.length === 1 ? "regla" : "reglas"} en esta vista` : "Consultando reglas…"}</div><span className="rules-readonly">{puedeEditar ? "Selecciona una regla para editarla" : "Vista de consulta"}</span></div>
    {reglas.isLoading && <div className="state-message" role="status"><LoaderCircle className="spin" /> Cargando reglas…</div>}
    {reglas.isError && <div className="state-message state-message--error" role="alert"><AlertTriangle />No fue posible cargar las reglas.<button type="button" onClick={() => void reglas.refetch()}>Reintentar</button></div>}
    {reglas.data && reglas.data.length === 0 && <div className="state-message">No hay reglas para el área seleccionada.</div>}
    {reglas.data && reglas.data.length > 0 && <div className="rules-table-wrap"><table className="rules-table"><caption className="sr-only">Listado de reglas de seguridad</caption><thead><tr><th scope="col">Nombre</th><th scope="col">Área</th><th scope="col">Estado</th><th scope="col">Versión</th>{puedeEditar && <th scope="col"><span className="sr-only">Acción</span></th>}</tr></thead><tbody>{reglas.data.map((regla) => <tr key={regla.id}><th scope="row">{regla.nombre}</th><td>{nombresArea.get(regla.area_id) ?? `Área #${regla.area_id}`}</td><td><span className={`rule-status rule-status--${regla.activa ? "active" : "inactive"}`}>{regla.activa ? "Activa" : "Inactiva"}</span></td><td className="mono">Versión {regla.version}</td>{puedeEditar && <td><button type="button" onClick={() => abrirEditor(regla)}>Editar</button></td>}</tr>)}</tbody></table></div>}
    <p className="live-message" aria-live="polite">{mensaje}</p>
  </main>;
}
