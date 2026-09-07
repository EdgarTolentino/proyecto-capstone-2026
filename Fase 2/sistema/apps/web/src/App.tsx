import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, LoaderCircle } from "lucide-react";
import { useMemo, useState } from "react";

import {
  ApiError,
  listarHallazgos,
  obtenerCatalogos,
  obtenerEstado,
  obtenerSesion,
  triarHallazgo,
  triarLote,
} from "./api/client";
import type { DecisionTriage } from "./api/types";
import { AppShell } from "./components/AppShell";
import { BulkActionsBar } from "./components/BulkActionsBar";
import { EvidenceDrawer } from "./components/EvidenceDrawer";
import { FalsePositiveDialog } from "./components/FalsePositiveDialog";
import { HallazgoFilters } from "./components/HallazgoFilters";
import { HallazgosGrid } from "./components/HallazgosGrid";
import { TriageTabs } from "./components/TriageTabs";
import { useHallazgoFilters } from "./hooks/useHallazgoFilters";
import { useHallazgoShortcuts } from "./hooks/useHallazgoShortcuts";

export default function App() {
  const queryClient = useQueryClient();
  const { filtros, actualizar } = useHallazgoFilters();
  const [activoId, setActivoId] = useState<number>();
  const [seleccionados, setSeleccionados] = useState<Set<number>>(new Set());
  const [mostrarMotivo, setMostrarMotivo] = useState(false);
  const [mensaje, setMensaje] = useState("");

  const sesion = useQuery({ queryKey: ["sesion"], queryFn: obtenerSesion });
  const catalogos = useQuery({ queryKey: ["catalogos"], queryFn: obtenerCatalogos, staleTime: Infinity });
  const estado = useQuery({ queryKey: ["estado"], queryFn: obtenerEstado, refetchInterval: 5_000 });
  // El visor no cambia la consulta ni desmonta la tabla: así conserva el desplazamiento.
  const filtrosLista = { ...filtros, hallazgoId: undefined };
  const pagina = useQuery({
    queryKey: ["hallazgos", filtrosLista],
    queryFn: () => listarHallazgos(filtrosLista),
    enabled: sesion.data?.permisos?.includes("ver_hallazgos") ?? false,
  });

  const hallazgos = useMemo(() => pagina.data?.items ?? [], [pagina.data]);
  const permisos = new Set(sesion.data?.permisos ?? []);
  const permiteTriar = permisos.has("triar_hallazgos");
  const permiteEvidencia = permisos.has("ver_evidencia");
  const activoVisibleId = hallazgos.some((item) => item.id === activoId)
    ? activoId
    : hallazgos[0]?.id;
  const atajoActivoId = filtros.hallazgoId ?? activoVisibleId;

  const actualizarBandeja = async () => {
    await queryClient.invalidateQueries({ queryKey: ["hallazgos"] });
    await queryClient.invalidateQueries({ queryKey: ["estado"] });
  };

  const triageIndividual = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: DecisionTriage }) =>
      triarHallazgo(id, decision),
    onSuccess: async (_resultado, variables) => {
      setMensaje("Decisión guardada.");

      // Después de resolver desde el visor avanzamos al siguiente caso de la cola.
      if (filtros.hallazgoId === variables.id) {
        const indice = hallazgos.findIndex((item) => item.id === variables.id);
        const siguiente = hallazgos[indice + 1] ?? hallazgos[indice - 1];
        if (siguiente) {
          setActivoId(siguiente.id);
          actualizar({ hallazgoId: siguiente.id }, true);
        } else actualizar({ hallazgoId: undefined }, true);
      }
      await actualizarBandeja();
    },
    onError: (error) => {
      setMensaje(
        error instanceof ApiError && error.status === 409
          ? "Otro usuario ya resolvió este hallazgo. Actualizamos la bandeja."
          : "No pudimos guardar la decisión. Intenta nuevamente.",
      );
      if (error instanceof ApiError && error.status === 409) void actualizarBandeja();
    },
  });

  const triageEnLote = useMutation({
    mutationFn: ({ ids, decision }: { ids: number[]; decision: DecisionTriage }) =>
      triarLote(ids, decision),
    onSuccess: async (resultado) => {
      const omitidos = new Set(resultado.omitidos?.flatMap((item) => item.id ?? []) ?? []);
      setSeleccionados(omitidos);
      setMensaje(`${resultado.aplicados ?? 0} decisiones guardadas.`);
      await actualizarBandeja();
    },
    onError: () => setMensaje("No pudimos aplicar la acción en lote."),
  });

  const abrir = (id: number) => {
    if (permiteEvidencia) actualizar({ hallazgoId: id });
  };

  const cerrarVisor = () => {
    actualizar({ hallazgoId: undefined });
    window.setTimeout(() => document.querySelector<HTMLElement>(".grid-viewport")?.focus(), 0);
  };

  const decidir = (decision: DecisionTriage) => {
    if (!atajoActivoId || !permiteTriar || triageIndividual.isPending) return;
    triageIndividual.mutate({ id: atajoActivoId, decision });
  };

  const decidirSeleccion = (decision: DecisionTriage) => {
    const ids = [...seleccionados];
    if (!ids.length || !permiteTriar) return;
    triageEnLote.mutate({ ids, decision });
  };

  useHallazgoShortcuts({
    hallazgos,
    activoId: atajoActivoId,
    enabled: !mostrarMotivo && (sesion.data?.permisos?.includes("ver_hallazgos") ?? false),
    permiteTriar,
    visorAbierto: Boolean(filtros.hallazgoId),
    onActivate: (id) => {
      setActivoId(id);
      if (filtros.hallazgoId) actualizar({ hallazgoId: id }, true);
    },
    onOpen: abrir,
    onConfirm: () => decidir({ estado: "confirmado" }),
    onFalsePositive: () => setMostrarMotivo(true),
  });

  const confirmarMotivo = (motivo: string) => {
    const decision: DecisionTriage = { estado: "falso_positivo", motivo };
    if (filtros.hallazgoId) {
      triageIndividual.mutate({ id: filtros.hallazgoId, decision });
    } else if (seleccionados.size) decidirSeleccion(decision);
    else decidir(decision);
    setMostrarMotivo(false);
  };

  return (
    <AppShell catalogos={catalogos.data} estado={estado.data} sesion={sesion.data}>
      <main className="findings-page">
        {sesion.data && !permisos.has("ver_hallazgos") && <div role="alert">No tienes permiso para ver hallazgos.</div>}
        <TriageTabs vista={filtros.vista} contadores={pagina.data?.contadores} onChange={(vista) => { actualizar({ vista, estado: undefined, hallazgoId: undefined }); setSeleccionados(new Set()); }} />
        <HallazgoFilters filtros={filtros} catalogos={catalogos.data} onChange={(cambios) => { actualizar(cambios); setSeleccionados(new Set()); }} />
        <div className="legal-notice"><AlertTriangle size={13} aria-hidden="true" /> Indicio automatizado. Requiere validación humana. El sistema reporta por área y turno, nunca por persona.</div>
        <div className="result-summary" aria-live="polite">{pagina.data ? `${hallazgos.length} hallazgos` : "Consultando hallazgos…"}</div>

        {pagina.isLoading && <div className="state-message"><LoaderCircle className="spin" /> Cargando bandeja…</div>}
        {pagina.isError && <div className="state-message state-message--error"><AlertTriangle /> No fue posible cargar la bandeja. Comprueba que el mock esté encendido con <code>make mock</code>.</div>}
        {pagina.data && hallazgos.length === 0 && <div className="state-message">No hay hallazgos con estos filtros.</div>}
        {pagina.data && hallazgos.length > 0 && (
          <HallazgosGrid
            hallazgos={hallazgos}
            activoId={activoVisibleId}
            seleccionados={seleccionados}
            permiteSeleccionar={permiteTriar}
            onActivate={setActivoId}
            onOpen={abrir}
            onSelect={(id, checked) => setSeleccionados((actuales) => {
              const siguiente = new Set(actuales);
              if (checked) siguiente.add(id);
              else siguiente.delete(id);
              return siguiente;
            })}
            onSelectAll={(checked) => setSeleccionados(checked ? new Set(hallazgos.map((item) => item.id)) : new Set())}
          />
        )}
        {seleccionados.size > 0 && (
          <BulkActionsBar
            count={seleccionados.size}
            busy={triageEnLote.isPending}
            onConfirm={() => decidirSeleccion({ estado: "confirmado" })}
            onFalsePositive={() => setMostrarMotivo(true)}
            onClear={() => setSeleccionados(new Set())}
          />
        )}
      </main>
      {filtros.hallazgoId && permiteEvidencia && (
        <EvidenceDrawer
          hallazgoId={filtros.hallazgoId}
          cola={hallazgos}
          permiteTriar={permiteTriar}
          onClose={cerrarVisor}
          onMove={(hallazgoId) => { setActivoId(hallazgoId); actualizar({ hallazgoId }, true); }}
          onTriage={(decision) => triageIndividual.mutate({ id: filtros.hallazgoId!, decision })}
          onFalsePositive={() => setMostrarMotivo(true)}
          isUpdating={triageIndividual.isPending}
        />
      )}
      {mostrarMotivo && (
        <FalsePositiveDialog
          count={filtros.hallazgoId ? 1 : seleccionados.size || 1}
          onCancel={() => setMostrarMotivo(false)}
          onConfirm={confirmarMotivo}
        />
      )}
      <div className="live-message" aria-live="polite">{mensaje}</div>
    </AppShell>
  );
}
