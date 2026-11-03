import { ApiError } from "../api/client";

// Los fallos de la «Sala en vivo»: con 401 o 403 no se insiste (se ofrece «Reintentar»).
export const sinPermiso = (error: unknown) => error instanceof ApiError && [401, 403].includes(error.status);

export function textoDeFallo(error: unknown, recurso: "videos" | "hallazgos"): string {
  if (error instanceof ApiError && error.status === 401) return "Sesión no válida";
  if (sinPermiso(error)) return `No tienes permiso para ver los ${recurso}`;
  return `No fue posible consultar los ${recurso}`;
}
