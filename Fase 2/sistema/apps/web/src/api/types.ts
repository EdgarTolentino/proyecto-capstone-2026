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
export type Regla = components["schemas"]["Regla"];
export type ReglaEntrada = components["schemas"]["ReglaEntrada"];
export type ResultadoSimulacion = components["schemas"]["ResultadoSimulacion"];
export type Panel = components["schemas"]["Panel"];
export type Reporte = components["schemas"]["Reporte"];
export type Video = components["schemas"]["Video"];
export type AvanceVideo = NonNullable<Video["avance"]>;

export interface PaginaVideos {
  items: Video[];
  siguiente_cursor?: string | null;
}

export type EntradaVideo = components["schemas"]["EntradaVideo"];
export type Pedido = components["schemas"]["Pedido"];
export type PedidoNuevo = components["schemas"]["PedidoNuevo"];
export type EstadoPedido = Pedido["estado"];

// El contrato define estas listas dentro de la respuesta y no les da un nombre propio.
export interface ListaEntrada {
  items: EntradaVideo[];
}

export interface ListaPedidos {
  items: Pedido[];
}

export interface FiltrosPanel {
  desde?: string;
  hasta?: string;
  turno?: string;
  obraId?: number;
}

export type TipoReporte = "ranking-epp" | "zonas" | "mapa-calor" | "tendencia";
export type SegmentacionReporte = "zona" | "turno" | "camara" | "epp";

export interface FiltrosReporte {
  desde?: string;
  hasta?: string;
  areaId?: number;
  segmentacion?: SegmentacionReporte;
}

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
