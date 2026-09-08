import type { components } from "./schema";

// Estos tipos vienen del contrato OpenAPI. Si el contrato cambia, TypeScript avisa.
export type Hallazgo = components["schemas"]["Hallazgo"];
export type HallazgoDetalle = components["schemas"]["HallazgoDetalle"];
export type PaginaHallazgos = components["schemas"]["PaginaHallazgos"];
export type Catalogos = components["schemas"]["Catalogos"];
export type Sesion = components["schemas"]["Sesion"];
export type DecisionTriage = components["schemas"]["DecisionTriage"];
export type Severidad = components["schemas"]["Severidad"];
export type TipoEpp = components["schemas"]["TipoEpp"];
export type EstadoHallazgo = components["schemas"]["EstadoHallazgo"];

// El contrato define este objeto dentro de GET /estado y no le da un nombre propio.
export interface EstadoSistema {
  ingesta: {
    activa?: boolean;
    en_proceso?: number;
    en_cola?: number;
  };
  cobertura: {
    fuentes_activas?: number;
    fuentes_totales?: number;
  };
  pendientes_por_revisar: number;
}

export type VistaTriage =
  | "por_revisar"
  | "confirmados"
  | "descartados"
  | "reincidentes"
  | "todos";

export interface FiltrosHallazgos {
  vista: VistaTriage;
  estado?: string;
  severidad?: string;
  areaId?: string;
  fuenteId?: string;
  epp?: string;
  desde?: string;
  hasta?: string;
  turno?: string;
  orden?: string;
  hallazgoId?: number;
}
