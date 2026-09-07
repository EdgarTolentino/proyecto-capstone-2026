import type {
  Catalogos,
  DecisionTriage,
  EstadoSistema,
  FiltrosHallazgos,
  Hallazgo,
  HallazgoDetalle,
  PaginaHallazgos,
  Sesion,
} from "./types";

// En desarrollo usamos el mock. En producción esta URL se cambia con VITE_API_URL.
const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:4010";
const AUTHORIZATION = "Bearer demo";

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
    const error = (await respuesta.json().catch(() => null)) as { mensaje?: string } | null;
    throw new ApiError(error?.mensaje ?? "No pudimos comunicarnos con la API.", respuesta.status);
  }

  return respuesta.json() as Promise<T>;
}

function parametrosDeApi(filtros: FiltrosHallazgos): URLSearchParams {
  const parametros = new URLSearchParams({ limite: "200" });

  // Las pestañas se traducen a filtros del contrato.
  if (filtros.vista === "por_revisar") parametros.set("estado", "por_revisar");
  if (filtros.vista === "confirmados") parametros.set("estado", "confirmado");
  if (filtros.vista === "reincidentes") parametros.set("reincidente", "true");
  if (filtros.estado) parametros.set("estado", filtros.estado);

  if (filtros.severidad) parametros.set("severidad", filtros.severidad);
  if (filtros.areaId) parametros.set("area_id", filtros.areaId);
  if (filtros.fuenteId) parametros.set("fuente_id", filtros.fuenteId);
  if (filtros.epp) parametros.set("epp", filtros.epp);
  if (filtros.desde) parametros.set("desde", new Date(`${filtros.desde}T00:00:00`).toISOString());
  if (filtros.hasta) parametros.set("hasta", new Date(`${filtros.hasta}T23:59:59`).toISOString());
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
