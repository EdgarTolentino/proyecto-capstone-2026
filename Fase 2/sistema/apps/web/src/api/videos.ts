import { ApiError } from "./client";
import type { EstadoPedido, PaginaVideos, Pedido } from "./types";

export const INTERVALO_REFRESCO_MS = 10_000;
export const INTERVALO_AVANCE_MS = 3_000;
// Cada cuánto se vuelven a pedir la bandeja, el panel, el estado y la cola de videos: durante una
// demostración entran videos (cada trozo de la cámara es uno) y hallazgos sin que nadie recargue.
// React Query no consulta con la pestaña oculta (`refetchIntervalInBackground` es falso).
export const INTERVALO_BANDEJA_MS = 5_000;
// La sala en vivo pide solo los videos `procesando` (una consulta chica): un trozo de 5 s con GPU
// se procesa en 2-3 s y cada 5 s podría no verse nunca.
export const INTERVALO_SALA_MS = 1_000;
// Mínimo entre el inicio de dos pedidos de cuadros en vivo (cada pedido trae hasta 30 cuadros).
export const INTERVALO_VIVO_MS = 500;
// Sin cuadro (404) o con un error: no se golpea la API cuatro veces por segundo.
export const ESPERA_VIVO_SIN_CUADRO_MS = 1_000;

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

// Un pedido sigue «pedido» mientras espera al trabajador o este lo está registrando.
export function pedidoSigueAbierto(pedido: Pedido): boolean {
  return pedidosAbiertos.has(pedido.estado);
}

// Los pedidos se vuelven a pedir solo mientras alguno espera al trabajador.
export function intervaloDePedidos(pedidos: Pedido[] | undefined): number | false {
  return pedidos?.some((pedido) => pedidosAbiertos.has(pedido.estado)) ? INTERVALO_REFRESCO_MS : false;
}

// La cola se vuelve a pedir siempre: aunque esté vacía o todo haya terminado, puede llegar un video
// nuevo. Con uno procesando se pide más seguido, para que la barra de avance se mueva. Cada
// refresco repide TODAS las páginas cargadas: con más de una («Cargar más»), el ritmo baja a
// INTERVALO_REFRESCO_MS para no multiplicar las consultas.
export function intervaloDeRefresco(paginas: PaginaVideos[] | undefined): number {
  if ((paginas?.length ?? 0) > 1) return INTERVALO_REFRESCO_MS;
  const hayProcesando = paginas?.some((pagina) => pagina.items.some((video) => video.estado === "procesando"));
  return hayProcesando ? INTERVALO_AVANCE_MS : INTERVALO_BANDEJA_MS;
}

// Tras un error la cola sigue intentando, más despacio: una caída corta de la API no debe dejarla
// vieja hasta que alguien pulse «Reintentar». Con 401 o 403 no: reintentar sin permiso no sirve.
export function intervaloTrasError(error: unknown): number | false {
  return error instanceof ApiError && [401, 403].includes(error.status) ? false : INTERVALO_REFRESCO_MS;
}
