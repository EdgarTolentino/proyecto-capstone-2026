import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, LoaderCircle } from "lucide-react";
import { useMemo, useState } from "react";

import {
  ApiError,
  listarHallazgos,
  obtenerCatalogos,
  obtenerPanel,
  obtenerEstado,
  obtenerSesion,
  triarHallazgo,
  triarLote,
} from "./api/client";
import type { DecisionTriage } from "./api/types";
import { INTERVALO_BANDEJA_MS } from "./api/videos";
import { AppShell } from "./components/AppShell";
import { BulkActionsBar } from "./components/BulkActionsBar";
import { EvidenceDrawer } from "./components/EvidenceDrawer";
import { FalsePositiveDialog } from "./components/FalsePositiveDialog";
import { HallazgoFilters } from "./components/HallazgoFilters";
import { HallazgosGrid } from "./components/HallazgosGrid";
import { ReglasPage } from "./components/ReglasPage";
import { SalaEnVivoPage } from "./components/SalaEnVivoPage";
import { PanelPage } from "./components/PanelPage";
import { TriageTabs } from "./components/TriageTabs";
import { VideosPage } from "./components/VideosPage";
import { useAppNavigation } from "./hooks/useAppNavigation";
import { useHallazgoFilters } from "./hooks/useHallazgoFilters";
import { useHallazgoShortcuts } from "./hooks/useHallazgoShortcuts";
import { usePanelFilters } from "./hooks/usePanelFilters";

export default function App() {
  const queryClient = useQueryClient();
  const { seccion, navegar, navegarHallazgos } = useAppNavigation();
  const { filtros, actualizar } = useHallazgoFilters();
  const { filtros: filtrosPanel, actualizar: actualizarFiltrosPanel } = usePanelFilters();
  const [activoId, setActivoId] = useState<number>();
  const [seleccionados, setSeleccionados] = useState<Set<number>>(new Set());
  // A quién se aplicará el falso positivo, congelado al abrir el diálogo: si la bandeja se refresca
  // mientras se escribe el motivo, la decisión no cambia de destinatario.
  const [motivoPara, setMotivoPara] = useState<{ ids: number[]; lote: boolean } | null>(null);
  const mostrarMotivo = motivoPara !== null;
  const [mensaje, setMensaje] = useState("");

  const sesion = useQuery({ queryKey: ["sesion"], queryFn: obtenerSesion });
  const catalogos = useQuery({ queryKey: ["catalogos"], queryFn: obtenerCatalogos, staleTime: Infinity });
  const estado = useQuery({ queryKey: ["estado"], queryFn: obtenerEstado, refetchInterval: INTERVALO_BANDEJA_MS });
  const panel = useQuery({
    queryKey: ["panel", filtrosPanel],
    queryFn: () => obtenerPanel(filtrosPanel),
    enabled: seccion === "panel" && (sesion.data?.permisos?.includes("ver_hallazgos") ?? false),
    placeholderData: keepPreviousData,
    refetchInterval: INTERVALO_BANDEJA_MS,
  });
  const panelSinPermiso = panel.error instanceof ApiError && [401, 403].includes(panel.error.status);
  const mostrarAvisoObraSinFiltro = seccion === "hallazgos"
    && new URL(window.location.href).searchParams.has("obra_no_filtrada");
  // El visor no cambia la consulta ni desmonta la tabla: así conserva el desplazamiento.
  const filtrosLista = { ...filtros, hallazgoId: undefined };
  const pagina = useQuery({
    queryKey: ["hallazgos", filtrosLista],
    queryFn: () => listarHallazgos(filtrosLista),
    enabled: seccion === "hallazgos" && (sesion.data?.permisos?.includes("ver_hallazgos") ?? false),
    refetchInterval: INTERVALO_BANDEJA_MS,
  });

  const hallazgos = useMemo(() => pagina.data?.items ?? [], [pagina.data]);
  const permisos = new Set(sesion.data?.permisos ?? []);
  const permiteTriar = permisos.has("triar_hallazgos");
  const permiteEvidencia = permisos.has("ver_evidencia");
  // La fila activa se fija en la primera UNA vez (al abrir la bandeja o al cambiar de filtros). Si
  // después sale de la lista porque llegaron otros hallazgos, no se pasa sola a la primera: la
  // grilla saltaría al principio y los atajos actuarían sobre otra fila. Queda sin activa y `j`
  // vuelve a elegir.
  const firmaFiltros = JSON.stringify(filtrosLista);
  const [firmaVista, setFirmaVista] = useState(firmaFiltros);
  if (firmaFiltros !== firmaVista) {
    setFirmaVista(firmaFiltros);
    setActivoId(undefined);
  }
  if (activoId === undefined && hallazgos.length > 0) setActivoId(hallazgos[0].id);
  const activoVisibleId = hallazgos.some((item) => item.id === activoId) ? activoId : undefined;
  // Con la bandeja refrescándose, un hallazgo seleccionado puede salir de la página (llegan otros).
  // Lo que no está en la lista no se cuenta ni se envía en un triage en lote.
  const seleccionVigente = useMemo(() => {
    const presentes = new Set(hallazgos.map((item) => item.id));
    return new Set([...seleccionados].filter((id) => presentes.has(id)));
  }, [hallazgos, seleccionados]);
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
      const sinAplicar = resultado.omitidos ?? [];
      // Lo que la API no aplicó se dice con su motivo: la selección ya filtrada lo esconde.
      const motivos = [...new Set(sinAplicar.map((item) => item.motivo || "sin motivo"))].join("; ");
      setMensaje(
        `${resultado.aplicados ?? 0} decisiones guardadas.` +
          (sinAplicar.length ? ` ${sinAplicar.length} omitidas: ${motivos}.` : ""),
      );
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
    const ids = [...seleccionVigente];
    if (!ids.length || !permiteTriar) return;
    triageEnLote.mutate({ ids, decision });
  };

  // El destino del falso positivo, tal como está en pantalla AHORA: el visor, la selección o la fila activa.
  const abrirMotivo = () => {
    if (filtros.hallazgoId) setMotivoPara({ ids: [filtros.hallazgoId], lote: false });
    else if (seleccionVigente.size) setMotivoPara({ ids: [...seleccionVigente], lote: true });
    else if (atajoActivoId) setMotivoPara({ ids: [atajoActivoId], lote: false });
  };

  useHallazgoShortcuts({
    hallazgos,
    activoId: atajoActivoId,
    enabled: seccion === "hallazgos" && !mostrarMotivo && (sesion.data?.permisos?.includes("ver_hallazgos") ?? false),
    permiteTriar,
    visorAbierto: Boolean(filtros.hallazgoId),
    onActivate: (id) => {
      setActivoId(id);
      if (filtros.hallazgoId) actualizar({ hallazgoId: id }, true);
    },
    onOpen: abrir,
    onConfirm: () => decidir({ estado: "confirmado" }),
    onFalsePositive: abrirMotivo,
    onSinActivo: () => setMensaje("Ningún hallazgo activo: usa j o haz clic en una fila."),
  });

  const confirmarMotivo = (motivo: string) => {
    const destino = motivoPara;
    setMotivoPara(null);
    if (!destino?.ids.length || !permiteTriar) return;
    const decision: DecisionTriage = { estado: "falso_positivo", motivo };
    // Sobre los ids con que se abrió el diálogo, aunque la lista ya haya cambiado.
    if (destino.lote) triageEnLote.mutate({ ids: destino.ids, decision });
    else triageIndividual.mutate({ id: destino.ids[0], decision });
  };

  return (
    <AppShell catalogos={catalogos.data} estado={estado.data} sesion={sesion.data} sesionError={sesion.isError} seccion={seccion} onNavigate={navegar}>
      {seccion === "panel" && (
        <PanelPage
          panel={panel.data}
          filtros={filtrosPanel}
          catalogos={catalogos.data}
          isLoading={sesion.isLoading || panel.isLoading}
          isError={sesion.isError || (panel.isError && !panelSinPermiso)}
          sinPermiso={Boolean((sesion.data && !permisos.has("ver_hallazgos")) || panelSinPermiso)}
          onRetry={() => { if (sesion.isError) void sesion.refetch(); else void panel.refetch(); }}
          onChangeFilters={actualizarFiltrosPanel}
          onNavigateHallazgos={navegarHallazgos}
        />
      )}
      {seccion === "videos" && <VideosPage puedeProcesar={permisos.has("procesar_videos")} puedeVerEvidencia={permiteEvidencia} catalogos={catalogos.data} catalogosError={catalogos.isError} />}
      {seccion === "sala" && sesion.isError && (
        <main className="findings-page">
          <div className="state-message state-message--error" role="alert">
            <AlertTriangle />
            No fue posible validar tu sesión
            <button type="button" onClick={() => void sesion.refetch()}>Reintentar</button>
          </div>
        </main>
      )}
      {seccion === "sala" && permiteEvidencia && <SalaEnVivoPage />}
      {seccion === "sala" && sesion.data && !permiteEvidencia && (
        <main className="findings-page"><div className="state-message" role="alert">No tienes permiso para ver la sala en vivo.</div></main>
      )}
      {seccion === "hallazgos" && (
      <main className="findings-page">
        {mostrarAvisoObraSinFiltro && <div className="state-message" role="status">La obra seleccionada en el panel no se aplica en esta bandeja: el contrato de Hallazgos no ofrece filtro por obra.</div>}
        {sesion.isLoading && <div className="state-message"><LoaderCircle className="spin" /> Cargando sesión…</div>}
        {sesion.isError && (
          <div className="state-message state-message--error" role="alert">
            <AlertTriangle />
            No fue posible cargar la sesión.
            <button type="button" onClick={() => void sesion.refetch()}>Reintentar</button>
          </div>
        )}
        {sesion.data && !permisos.has("ver_hallazgos") && <div className="state-message" role="alert">No tienes permiso para ver hallazgos.</div>}
        {sesion.data && permisos.has("ver_hallazgos") && (
          <>
            <TriageTabs vista={filtros.vista} contadores={pagina.data?.contadores} onChange={(vista) => { actualizar({ vista, estado: undefined, hallazgoId: undefined }); setSeleccionados(new Set()); }} />
            <div className="review-heading">
              <div><p className="eyebrow">CONTROL Y VALIDACIÓN</p><h2>Bandeja de hallazgos</h2></div>
              <div className="shortcut-help" aria-label="Atajos disponibles"><kbd>j</kbd><kbd>k</kbd> navegar <kbd>c</kbd> confirmar <kbd>x</kbd> descartar <kbd>↵</kbd> abrir</div>
            </div>
            <HallazgoFilters filtros={filtros} catalogos={catalogos.data} onChange={(cambios) => { actualizar(cambios); setSeleccionados(new Set()); }} />
            <div className="legal-notice"><AlertTriangle size={13} aria-hidden="true" /> Indicio automatizado. Requiere validación humana. El sistema reporta por área y turno, nunca por persona.</div>
            <div className="results-bar">
              <div className="result-summary" aria-live="polite">{pagina.data ? `${hallazgos.length} hallazgos en esta vista` : "Consultando hallazgos…"}</div>
              <div className="severity-key" aria-label="Leyenda de severidad"><span className="severity severity--critica"><i>◆</i> Crítica</span><span className="severity severity--alta"><i>▲</i> Alta</span><span className="severity severity--media"><i>●</i> Media</span><span className="severity severity--baja"><i>○</i> Baja</span></div>
            </div>

            {pagina.isLoading && <div className="state-message"><LoaderCircle className="spin" /> Cargando bandeja…</div>}
            {pagina.isError && <div className="state-message state-message--error"><AlertTriangle /> No fue posible cargar la bandeja. Comprueba que el mock esté encendido con <code>make mock</code>.</div>}
            {pagina.data && hallazgos.length === 0 && <div className="state-message">No hay hallazgos con estos filtros.</div>}
            {pagina.data && hallazgos.length > 0 && (
              <HallazgosGrid
                hallazgos={hallazgos}
                activoId={activoVisibleId}
                seleccionados={seleccionVigente}
                permiteSeleccionar={permiteTriar}
                permiteEvidencia={permiteEvidencia}
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
            {seleccionVigente.size > 0 && (
              <BulkActionsBar
                count={seleccionVigente.size}
                busy={triageEnLote.isPending}
                onConfirm={() => decidirSeleccion({ estado: "confirmado" })}
                onFalsePositive={abrirMotivo}
                onClear={() => setSeleccionados(new Set())}
              />
            )}
          </>
        )}
      </main>
      )}
      {seccion === "reglas" && sesion.isLoading && (
        <main className="rules-page"><div className="state-message"><LoaderCircle className="spin" /> Cargando sesión…</div></main>
      )}
      {seccion === "reglas" && sesion.isError && (
        <main className="rules-page">
          <div className="state-message state-message--error" role="alert">
            <AlertTriangle />
            No fue posible cargar la sesión.
            <button type="button" onClick={() => void sesion.refetch()}>Reintentar</button>
          </div>
        </main>
      )}
      {seccion === "reglas" && sesion.data && <ReglasPage catalogos={catalogos.data} puedeEditar={permisos.has("editar_reglas")} />}
      {seccion === "hallazgos" && filtros.hallazgoId && permiteEvidencia && (
        <EvidenceDrawer
          hallazgoId={filtros.hallazgoId}
          cola={hallazgos}
          permiteTriar={permiteTriar}
          onClose={cerrarVisor}
          onMove={(hallazgoId) => { setActivoId(hallazgoId); actualizar({ hallazgoId }, true); }}
          onTriage={(decision) => triageIndividual.mutate({ id: filtros.hallazgoId!, decision })}
          onFalsePositive={abrirMotivo}
          isUpdating={triageIndividual.isPending}
        />
      )}
      {seccion === "hallazgos" && mostrarMotivo && (
        <FalsePositiveDialog
          count={motivoPara?.ids.length ?? 1}
          onCancel={() => setMotivoPara(null)}
          onConfirm={confirmarMotivo}
        />
      )}
      <div className="live-message" aria-live="polite">{mensaje}</div>
    </AppShell>
  );
}
