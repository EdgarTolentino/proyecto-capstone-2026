import type { PaginaVideos, Video } from "./types";

export const INTERVALO_REFRESCO_MS = 10_000;

const estadosPendientes: ReadonlySet<Video["estado"]> = new Set(["en_cola", "procesando", "reintentando"]);

// La cola se vuelve a pedir solo mientras algún video puede cambiar de estado.
export function intervaloDeRefresco(paginas: PaginaVideos[] | undefined): number | false {
  const hayPendientes = paginas?.some((pagina) => pagina.items.some((video) => estadosPendientes.has(video.estado)));
  return hayPendientes ? INTERVALO_REFRESCO_MS : false;
}
