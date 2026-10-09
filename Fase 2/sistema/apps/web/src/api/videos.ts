import { ApiError } from "./client";
import type { EstadoPedido, PaginaVideos, Pedido, Video } from "./types";

export const INTERVALO_REFRESCO_MS = 10_000;
export const INTERVALO_AVANCE_MS = 3_000;

const estadosPendientes: ReadonlySet<Video["estado"]> = new Set(["en_cola", "procesando", "reintentando"]);

const SIN_CARPETA = "El servidor no tiene configurada la carpeta de entrada.";
const SIN_PERMISO = "No tienes permiso para procesar videos.";

// Texto para la persona según el `status` y el `codigo` del contrato (PR 5). Un código que no
// se conoce cae en el mensaje genérico: nunca se muestra el texto crudo del servidor.
export function mensajeDePedido(error: unknown, archivo: string): string {
  if (error instanceof ApiError) {
    if ([401, 403].includes(error.status)) return SIN_PERMISO;
    if (error.status === 422) return "El nombre del archivo no es válido.";
    if (error.codigo === "archivo_no_encontrado") return `El archivo ${archivo} ya no está en la carpeta de entrada.`;
    if (error.codigo === "fuente_no_encontrada") return "La cámara elegida ya no existe.";
    if (error.codigo === "fuente_inactiva") return "La cámara elegida está inactiva.";
    if (error.codigo === "pedido_existente") return `El archivo ${archivo} ya tiene un pedido en curso.`;
    if (error.codigo === "entrada_no_configurada") return SIN_CARPETA;
  }
  return `No fue posible pedir el procesamiento de ${archivo}. Intenta nuevamente.`;
}

export function mensajeDeEntrada(error: unknown): string {
  if (error instanceof ApiError) {
    if ([401, 403].includes(error.status)) return SIN_PERMISO;
    if (error.codigo === "entrada_no_configurada") return SIN_CARPETA;
  }
  return "No fue posible leer la carpeta de entrada.";
}

// Estos dos errores dicen que la lista que la persona veía quedó vieja.
export function pedidoDejoListaVieja(error: unknown): boolean {
  return error instanceof ApiError && ["archivo_no_encontrado", "pedido_existente"].includes(error.codigo ?? "");
}

const pedidosAbiertos: ReadonlySet<EstadoPedido> = new Set(["pendiente", "tomado"]);

// Los pedidos se vuelven a pedir solo mientras alguno espera al trabajador.
export function intervaloDePedidos(pedidos: Pedido[] | undefined): number | false {
  return pedidos?.some((pedido) => pedidosAbiertos.has(pedido.estado)) ? INTERVALO_REFRESCO_MS : false;
}

// La cola se vuelve a pedir solo mientras algún video puede cambiar de estado. Con uno
// procesando se pide más seguido, para que la barra de avance se mueva.
export function intervaloDeRefresco(paginas: PaginaVideos[] | undefined): number | false {
  const videos = paginas?.flatMap((pagina) => pagina.items) ?? [];
  if (videos.some((video) => video.estado === "procesando")) return INTERVALO_AVANCE_MS;
  return videos.some((video) => estadosPendientes.has(video.estado)) ? INTERVALO_REFRESCO_MS : false;
}
