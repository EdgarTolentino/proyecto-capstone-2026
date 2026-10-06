import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, LoaderCircle, RotateCcw } from "lucide-react";
import { useState } from "react";

import { ApiError, listarVideos, reprocesarVideo } from "../api/client";
import type { Video } from "../api/types";
import { intervaloDeRefresco } from "../api/videos";
import "./VideosPage.css";

const estados: Record<Video["estado"], { nombre: string; clase: string }> = {
  en_cola: { nombre: "En cola", clase: "queued" },
  procesando: { nombre: "Procesando", clase: "processing" },
  reintentando: { nombre: "Reintentando", clase: "retrying" },
  listo: { nombre: "Listo", clase: "ready" },
  error: { nombre: "Error", clase: "error" },
};

const estadosConMotivo: ReadonlySet<Video["estado"]> = new Set(["error", "reintentando"]);
// En `en_cola` y `procesando` la API responde 409: ya va a procesarse.
const estadosReprocesables: ReadonlySet<Video["estado"]> = new Set(["listo", "error", "reintentando"]);

function esSinPermiso(error: unknown): boolean {
  return error instanceof ApiError && [401, 403].includes(error.status);
}

function EstadoVideo({ estado }: { estado: Video["estado"] }) {
  const dato = estados[estado];
  return (
    <span className={`video-status video-status--${dato.clase}`}>
      <span aria-hidden="true" />
      {dato.nombre}
    </span>
  );
}

export function VideosPage({ puedeEditarReglas = false }: { puedeEditarReglas?: boolean }) {
  const queryClient = useQueryClient();
  const [mensaje, setMensaje] = useState("");
  const consulta = useInfiniteQuery({
    queryKey: ["videos"],
    queryFn: ({ pageParam }) => listarVideos(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (ultimaPagina, _paginas, _parametroPagina, parametros) => {
      const siguiente = ultimaPagina.siguiente_cursor ?? undefined;
      return siguiente && !parametros.includes(siguiente) ? siguiente : undefined;
    },
    // Si un refresco falla, se deja de insistir hasta que la persona reintente.
    refetchInterval: (query) => (query.state.status === "error" ? false : intervaloDeRefresco(query.state.data?.pages)),
  });
  const videosPorId = new Map<number, Video>();
  for (const pagina of consulta.data?.pages ?? []) {
    for (const video of pagina.items) videosPorId.set(video.id, video);
  }
  const videos = [...videosPorId.values()];
  const errorPrincipal = consulta.isLoadingError;
  const reproceso = useMutation({
    mutationFn: (video: Video) => reprocesarVideo(video.id),
    // Se limpia antes de cada intento: no queda un mensaje viejo y uno repetido se vuelve a anunciar.
    onMutate: () => setMensaje(""),
    onSuccess: async (resultado, video) => {
      setMensaje(
        resultado.estado === "en_cola"
          ? `El video ${video.archivo} volvió a la cola.`
          : `Las reglas de ${video.archivo} se recalcularon sin usar la GPU.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["videos"] });
    },
    onError: (error, video) => {
      const status = error instanceof ApiError ? error.status : undefined;
      if (esSinPermiso(error)) setMensaje("No tienes permiso para reprocesar videos.");
      else if (status === 409) setMensaje(`El video ${video.archivo} ya se está procesando.`);
      else if (status === 404) setMensaje(`El video ${video.archivo} ya no existe.`);
      else setMensaje(`No fue posible reprocesar ${video.archivo}. Intenta nuevamente.`);
      // 409 y 404 dicen que la lista quedó vieja; los demás errores no cambian la cola.
      if (status === 409 || status === 404) void queryClient.invalidateQueries({ queryKey: ["videos"] });
    },
  });
  const sinPermiso = errorPrincipal && esSinPermiso(consulta.error);
  return (
    <main className="videos-page" aria-labelledby="videos-page-title" aria-busy={consulta.isLoading}>
      <div className="review-heading panel-heading">
        <div>
          <p className="eyebrow">INGESTA Y PROCESAMIENTO</p>
          <h2 id="videos-page-title">Cola de videos</h2>
        </div>
        {consulta.data && <span className="result-summary">{videos.length === 1 ? "1 video cargado" : `${videos.length} videos cargados`}</span>}
      </div>

      {consulta.isLoading && (
        <div className="state-message" role="status" aria-live="polite">
          <LoaderCircle className="spin" aria-hidden="true" /> Cargando videos…
        </div>
      )}
      {errorPrincipal && !sinPermiso && (
        <div className="state-message state-message--error" role="alert">
          <AlertTriangle aria-hidden="true" /> No fue posible cargar la cola de videos.
          <button type="button" onClick={() => void consulta.refetch()}>Reintentar</button>
        </div>
      )}
      {sinPermiso && <div className="state-message" role="alert">No tienes permiso para ver la cola de videos.</div>}
      {consulta.isSuccess && videos.length === 0 && (
        <div className="state-message" role="status">No hay videos en la cola.</div>
      )}
      {consulta.isRefetchError && !consulta.isFetching && (
        <div className="state-message" role="status">
          No fue posible actualizar la cola; se muestran los últimos datos cargados.
          <button type="button" onClick={() => void consulta.refetch()}>Reintentar</button>
        </div>
      )}
      {videos.length > 0 && (
        <>
          <div className="videos-table-wrap">
            <table className="videos-table" aria-label="Cola de videos">
              <thead>
                <tr>
                  <th scope="col">Archivo</th>
                  <th scope="col">Cámara</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Intentos</th>
                  <th scope="col">Motivo del error</th>
                  {puedeEditarReglas && <th scope="col">Acciones</th>}
                </tr>
              </thead>
              <tbody>
                {videos.map((video) => (
                  <tr key={video.id}>
                    <th scope="row" className="mono video-file">{video.archivo}</th>
                    <td>{video.fuente?.nombre ?? "—"}</td>
                    <td><EstadoVideo estado={video.estado} /></td>
                    <td className="mono video-attempts">{video.intentos ?? 0}</td>
                    <td className="video-error">{(estadosConMotivo.has(video.estado) && video.error_motivo) || "—"}</td>
                    {puedeEditarReglas && (
                      <td>
                        {estadosReprocesables.has(video.estado) ? (
                          <button
                            type="button"
                            className="video-reprocess"
                            aria-label={`Reprocesar ${video.archivo}`}
                            disabled={reproceso.isPending}
                            onClick={() => reproceso.mutate(video)}
                          >
                            <RotateCcw size={14} aria-hidden="true" />
                            Reprocesar
                          </button>
                        ) : "—"}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {consulta.isFetchNextPageError && (
            <div className="state-message state-message--error" role="alert">
              <AlertTriangle aria-hidden="true" />
              {esSinPermiso(consulta.error) ? "No tienes permiso para ver más videos." : "No fue posible cargar más videos."}
              {!esSinPermiso(consulta.error) && (
                <button type="button" onClick={() => void consulta.fetchNextPage()}>Reintentar cargar más</button>
              )}
            </div>
          )}
          {consulta.hasNextPage && !consulta.isFetchNextPageError && (
            <div className="videos-pagination">
              <button type="button" disabled={consulta.isFetchingNextPage} onClick={() => void consulta.fetchNextPage()}>
                {consulta.isFetchingNextPage ? "Cargando…" : "Cargar más videos"}
              </button>
            </div>
          )}
        </>
      )}
      <div className="video-message" role="status" aria-live="polite">{mensaje}</div>
    </main>
  );
}
