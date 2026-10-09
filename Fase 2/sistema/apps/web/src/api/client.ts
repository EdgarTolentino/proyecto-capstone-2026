import type {
  Catalogos,
  DecisionTriage,
  EstadoSistema,
  FiltrosHallazgos,
  Hallazgo,
  HallazgoDetalle,
  ListaEntrada,
  ListaPedidos,
  PaginaHallazgos,
  PaginaVideos,
  Panel,
  FiltrosPanel,
  Pedido,
  PedidoNuevo,
  Regla,
  ReglaEntrada,
  ResultadoSimulacion,
  Sesion,
  Video,
} from "./types";
import type { operations } from "./schema";
import { esFechaValida, inicioDelDiaEnFaena, sumarDias } from "./fechas";

// En desarrollo usamos el mock. En producción esta URL se cambia con VITE_API_URL.
const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:4010";
// Con qué cuenta entra la web: `demo` es el prevencionista de demostración. Cada integrante
// pone la suya en `apps/web/.env.development.local` (VITE_API_TOKEN=mortega); ver `.env.example`.
// Ese archivo solo lo carga `npm run dev`: ni las pruebas ni `vite build` lo leen.
const AUTHORIZATION = `Bearer ${import.meta.env.VITE_API_TOKEN || "demo"}`;

function baseApi(): URL {
  const base = new URL(API_URL, window.location.origin);
  base.pathname = `${base.pathname.replace(/\/+$/, "")}/`;
  return base;
}

function urlApi(ruta: string): URL {
  return new URL(ruta.replace(/^\/+/, ""), baseApi());
}

function cabecerasApi(headers?: HeadersInit): Headers {
  const result = new Headers(headers);
  result.set("Authorization", AUTHORIZATION);
  return result;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    // `codigo` del cuerpo de error del contrato (p. ej. `pedido_existente`): distingue los 409.
    public readonly codigo?: string,
  ) {
    super(message);
  }
}

async function api<T>(ruta: string, opciones?: RequestInit): Promise<T> {
  const headers = cabecerasApi(opciones?.headers);
  headers.set("Content-Type", "application/json");
  const respuesta = await fetch(urlApi(ruta), {
    ...opciones,
    headers,
  });

  if (!respuesta.ok) {
    const error = (await respuesta.json().catch(() => null)) as { mensaje?: string; codigo?: string } | null;
    throw new ApiError(
      error?.mensaje ?? "No pudimos comunicarnos con la API.",
      respuesta.status,
      typeof error?.codigo === "string" ? error.codigo : undefined,
    );
  }

  return respuesta.json() as Promise<T>;
}

function parametrosDeApi(filtros: FiltrosHallazgos): URLSearchParams {
  const parametros = new URLSearchParams({ limite: "200" });

  const instanteFecha = (valor: string, fin = false) => {
    if (/^\d{4}-\d{2}-\d{2}$/.test(valor)) {
      if (!esFechaValida(valor)) return undefined;
      return inicioDelDiaEnFaena(fin ? sumarDias(valor, 1) : valor);
    }
    return Number.isFinite(Date.parse(valor)) ? valor : undefined;
  };

  // Las pestañas se traducen a filtros del contrato.
  if (filtros.vista === "por_revisar") parametros.set("estado", "por_revisar");
  if (filtros.vista === "confirmados") parametros.set("estado", "confirmado");
  if (filtros.vista === "reincidentes") parametros.set("reincidente", "true");
  if (filtros.estado) parametros.set("estado", filtros.estado);

  if (filtros.severidad) parametros.set("severidad", filtros.severidad);
  if (filtros.areaId) parametros.set("area_id", filtros.areaId);
  if (filtros.fuenteId) parametros.set("fuente_id", filtros.fuenteId);
  if (filtros.epp) parametros.set("epp", filtros.epp);
  if (filtros.desde) {
    const desde = instanteFecha(filtros.desde);
    if (desde) parametros.set("desde", desde);
  }
  if (filtros.hasta) {
    const hasta = instanteFecha(filtros.hasta, true);
    if (hasta) parametros.set("hasta", hasta);
  }
  if (filtros.turno) parametros.set("turno", filtros.turno);
  if (filtros.orden) parametros.set("orden", filtros.orden);

  return parametros;
}

export async function listarHallazgos(filtros: FiltrosHallazgos): Promise<PaginaHallazgos> {
  const pagina = await api<PaginaHallazgos>(`/hallazgos?${parametrosDeApi(filtros)}`);

  // El contrato agrupa varios estados bajo “Descartados”, pero no ofrece ese filtro.
  // Para esta pestaña filtramos la página completa que entrega el mock.
  if (filtros.vista === "descartados") {
    const descartados = new Set(["falso_positivo", "duplicado"]);
    return { ...pagina, items: pagina.items.filter((item) => descartados.has(item.estado)) };
  }

  return pagina;
}

export const obtenerHallazgo = (id: number) => api<HallazgoDetalle>(`/hallazgos/${id}`);
export const obtenerCatalogos = () => api<Catalogos>("/catalogos");
export const obtenerEstado = () => api<EstadoSistema>("/estado");
export const obtenerSesion = () => api<Sesion>("/yo");

export function listarVideos(cursor?: string): Promise<PaginaVideos> {
  const parametros = new URLSearchParams({ limite: "200" });
  if (cursor) parametros.set("cursor", cursor);
  return api<PaginaVideos>(`/videos?${parametros}`);
}

export const reprocesarVideo = (id: number) =>
  api<Video>(`/videos/${id}/reprocesar`, { method: "POST" });

export const listarEntradaVideos = () => api<ListaEntrada>("/videos/entrada");

export const listarPedidos = () => api<ListaPedidos>("/videos/pedidos");

export const pedirIngesta = (peticion: PedidoNuevo) =>
  api<Pedido>("/videos", { method: "POST", body: JSON.stringify(peticion) });

function parametrosDelPanel(filtros: FiltrosPanel = {}): URLSearchParams {
  const parametros = new URLSearchParams();

  const instante = (valor: string, fin = false) => {
    if (/^\d{4}-\d{2}-\d{2}$/.test(valor)) {
      if (!esFechaValida(valor)) return undefined;
      return inicioDelDiaEnFaena(fin ? sumarDias(valor, 1) : valor);
    }
    return Number.isFinite(Date.parse(valor)) ? valor : undefined;
  };

  if (filtros.desde) {
    const desde = instante(filtros.desde);
    if (desde) parametros.set("desde", desde);
  }
  if (filtros.hasta) {
    const hasta = instante(filtros.hasta, true);
    if (hasta) parametros.set("hasta", hasta);
  }
  if (filtros.turno) parametros.set("turno", filtros.turno);
  if (filtros.obraId !== undefined) parametros.set("obra_id", String(filtros.obraId));

  return parametros;
}

export function obtenerPanel(filtros: FiltrosPanel = {}): Promise<Panel> {
  const consulta = parametrosDelPanel(filtros).toString();
  return api<Panel>(`/panel${consulta ? `?${consulta}` : ""}`);
}

export function listarReglas(areaId?: string): Promise<Regla[]> {
  const parametros = new URLSearchParams();
  if (areaId) parametros.set("area_id", areaId);
  const consulta = parametros.toString();
  return api<Regla[]>(`/reglas${consulta ? `?${consulta}` : ""}`);
}

export const crearRegla = (entrada: ReglaEntrada) =>
  api<Regla>("/reglas", { method: "POST", body: JSON.stringify(entrada) });

export const actualizarRegla = (id: number, entrada: ReglaEntrada) =>
  api<Regla>(`/reglas/${id}`, { method: "PUT", body: JSON.stringify(entrada) });

export const simularRegla = (id: number, simulacion: { desde: string; hasta: string; regla: ReglaEntrada }) =>
  api<ResultadoSimulacion>(`/reglas/${id}/simular`, { method: "POST", body: JSON.stringify(simulacion) });

export async function obtenerEvidencia(ruta: string, signal?: AbortSignal): Promise<Blob> {
  const base = baseApi();
  const objetivo = new URL(ruta, base);
  if (objetivo.origin !== base.origin) {
    throw new ApiError("La evidencia apunta fuera de la API configurada.", 400);
  }
  const respuesta = await fetch(objetivo, {
    headers: cabecerasApi(),
    signal,
  });
  if (!respuesta.ok) throw new ApiError("Evidencia no disponible.", respuesta.status);
  return respuesta.blob();
}

// Los últimos cuadros que analiza el modelo, con su posición en el video. Nítidos y sin tapar
// rostros (excepción de ADR-006; decisión de Edgar del 2026-10-09). El tipo sale del contrato.
export type CuadrosVivo = operations["listarCuadrosVivo"]["responses"][200]["content"]["application/json"];
export type CuadroVivo = CuadrosVivo["cuadros"][number];

// Solo los cuadros con `seq > desde`, de más viejo a más nuevo. Con el Bearer en la cabecera, como
// la evidencia: nunca un <img src> directo ni el token en la URL.
export async function obtenerCuadrosVivo(videoId: number, desde: number, signal?: AbortSignal): Promise<CuadrosVivo> {
  const respuesta = await fetch(urlApi(`/videos/${videoId}/vivo/cuadros?desde=${desde}`), {
    headers: cabecerasApi(),
    cache: "no-store",
    signal,
  });
  if (!respuesta.ok) throw new ApiError("Vista del modelo no disponible.", respuesta.status);
  return respuesta.json() as Promise<CuadrosVivo>;
}

export const triarHallazgo = (id: number, decision: DecisionTriage) =>
  api<Hallazgo>(`/hallazgos/${id}/triage`, {
    method: "POST",
    body: JSON.stringify(decision),
  });

export const triarLote = (ids: number[], decision: DecisionTriage) =>
  api<{ aplicados?: number; omitidos?: { id?: number; motivo?: string }[] }>(
    "/hallazgos/triage-lote",
    {
      method: "POST",
      body: JSON.stringify({ ids, decision }),
    },
  );
