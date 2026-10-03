import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, LoaderCircle, RotateCcw } from "lucide-react";
import { useState } from "react";

import { ApiError, listarVideos, reprocesarVideo } from "../api/client";
import type { Video } from "../api/types";
import "./VideosPage.css";

const estados: Record<Video["estado"], { nombre: string; clase: string }> = {
    en_cola: { nombre: "En cola", clase: "queued" },
    procesando: { nombre: "Procesando", clase: "processing" },
    reintentando: { nombre: "Reintentando", clase: "retrying" },
    listo: { nombre: "Listo", clase: "ready" },
    error: { nombre: "Error", clase: "error" },
};

function EstadoVideo({ estado }: { estado: Video["estado"] }) {
    const dato = estados[estado];
    return (
        <span role="status" className={`video-status video-status--${dato.clase}`} aria-label={`Estado: ${dato.nombre}`}>
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
    });
    const videosPorId = new Map<number, Video>();
    for (const pagina of consulta.data?.pages ?? []) {
        for (const video of pagina.items) videosPorId.set(video.id, video);
    }
    const videos = [...videosPorId.values()];
    const sinPermiso = consulta.error instanceof ApiError && [401, 403].includes(consulta.error.status);
    const reproceso = useMutation({
        mutationFn: (id: number) => reprocesarVideo(id),
        onSuccess: async (video) => {
            setMensaje(video.estado === "en_cola"
                ? "El video volvió a la cola."
                : "Las reglas del video se recalcularon sin usar la GPU.");
            await queryClient.invalidateQueries({ queryKey: ["videos"] });
        },
        onError: (error) => {
            const conflicto = error instanceof ApiError && error.status === 409;
            setMensaje(conflicto
                ? "El video ya se está procesando."
                : "No fue posible reprocesar el video. Intenta nuevamente.");
            if (conflicto) void queryClient.invalidateQueries({ queryKey: ["videos"] });
        },
    });

    return (
        <main className="videos-page" aria-labelledby="videos-page-title" aria-busy={consulta.isLoading}>
            <div className="review-heading panel-heading">
                <div>
                    <p className="eyebrow">INGESTA Y PROCESAMIENTO</p>
                    <h2 id="videos-page-title">Cola de videos</h2>
                </div>
                {consulta.data && <span className="result-summary">{videos.length} videos cargados</span>}
            </div>

            {consulta.isLoading && (
                <div className="state-message" role="status" aria-live="polite">
                    <LoaderCircle className="spin" aria-hidden="true" /> Cargando videos…
                </div>
            )}
            {consulta.isError && !sinPermiso && (
                <div className="state-message state-message--error" role="alert">
                    <AlertTriangle aria-hidden="true" /> No fue posible cargar la cola de videos.
                    <button type="button" onClick={() => void consulta.refetch()}>Reintentar</button>
                </div>
            )}
            {sinPermiso && <div className="state-message" role="alert">No tienes permiso para ver la cola de videos.</div>}
            {consulta.isSuccess && videos.length === 0 && (
                <div className="state-message" role="status">No hay videos en la cola.</div>
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
                                        <td className="video-error">{video.error_motivo || "—"}</td>
                                        {puedeEditarReglas && (
                                            <td>
                                                <button
                                                    type="button"
                                                    className="video-reprocess"
                                                    aria-label={`Reprocesar ${video.archivo}`}
                                                    disabled={reproceso.isPending}
                                                    onClick={() => reproceso.mutate(video.id)}
                                                >
                                                    <RotateCcw size={14} aria-hidden="true" />
                                                    Reprocesar
                                                </button>
                                            </td>
                                        )}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    {consulta.hasNextPage && (
                        <div className="videos-pagination">
                            <button type="button" disabled={consulta.isFetchingNextPage} onClick={() => void consulta.fetchNextPage()}>
                                {consulta.isFetchingNextPage ? "Cargando…" : "Cargar más videos"}
                            </button>
                        </div>
                    )}
                </>
            )}
            {mensaje && <div className="video-message" role="status" aria-live="polite">{mensaje}</div>}
        </main>
    );
}