import { expect, it } from "vitest";

import { ApiError } from "./client";
import type { Pedido, Video } from "./types";
import { INTERVALO_AVANCE_MS, INTERVALO_BANDEJA_MS, INTERVALO_REFRESCO_MS, intervaloDePedidos, intervaloDeRefresco, intervaloTrasError } from "./videos";

function videoDePrueba(estado: Video["estado"], id: number): Video {
  return { id, archivo: `v${id}.mp4`, capture_ts_inicio: "2026-10-02T08:00:00Z", estado };
}

it("refresca siempre la cola y más seguido mientras un video procesa", () => {
  const pagina = (...estados: Video["estado"][]) => ({ items: estados.map((e, i) => videoDePrueba(e, i)) });

  // Los valores van escritos aquí a propósito: comparar contra la constante de producción no
  // detectaría que alguien la cambiara.
  expect(INTERVALO_REFRESCO_MS).toBe(10_000);
  expect(INTERVALO_AVANCE_MS).toBe(3_000);
  expect(INTERVALO_BANDEJA_MS).toBe(5_000);
  // Sin datos, vacía o con todo terminado: sigue pidiendo, porque puede llegar un video nuevo.
  expect(intervaloDeRefresco(undefined)).toBe(5_000);
  expect(intervaloDeRefresco([pagina()])).toBe(5_000);
  expect(intervaloDeRefresco([pagina("listo", "error")])).toBe(5_000);
  expect(intervaloDeRefresco([pagina("listo", "en_cola")])).toBe(5_000);
  expect(intervaloDeRefresco([pagina("reintentando")])).toBe(5_000);
  expect(intervaloDeRefresco([pagina("procesando")])).toBe(3_000);
  expect(intervaloDeRefresco([pagina("listo", "procesando")])).toBe(3_000);
  // Con uno procesando manda el ritmo rápido, aunque otros esperen en la cola.
  expect(intervaloDeRefresco([pagina("en_cola", "procesando", "reintentando")])).toBe(3_000);
  // Con más de una página cargada cada refresco repite todas: el ritmo baja a 10 s.
  expect(intervaloDeRefresco([pagina("listo"), pagina("listo")])).toBe(10_000);
  expect(intervaloDeRefresco([pagina("procesando"), pagina("listo")])).toBe(10_000);
});

it("tras un error la cola sigue intentando cada 10 s, salvo con 401 o 403", () => {
  expect(intervaloTrasError(new ApiError("fallo", 500))).toBe(10_000);
  expect(intervaloTrasError(new ApiError("fallo", 404))).toBe(10_000);
  expect(intervaloTrasError(new TypeError("red caída"))).toBe(10_000);
  expect(intervaloTrasError(new ApiError("fallo", 401))).toBe(false);
  expect(intervaloTrasError(new ApiError("fallo", 403))).toBe(false);
});

it("vigila los pedidos solo mientras alguno está pendiente o tomado", () => {
  const pedido = (estado: Pedido["estado"]): Pedido => ({
    id: 1, archivo: "a.mp4", fuente: null, estado, motivo: null, video_id: null, creado_en: "2026-10-08T10:00:00Z",
  });

  expect(intervaloDePedidos(undefined)).toBe(false);
  expect(intervaloDePedidos([])).toBe(false);
  expect(intervaloDePedidos([pedido("registrado"), pedido("rechazado")])).toBe(false);
  expect(intervaloDePedidos([pedido("registrado"), pedido("pendiente")])).toBe(INTERVALO_REFRESCO_MS);
  expect(intervaloDePedidos([pedido("tomado")])).toBe(INTERVALO_REFRESCO_MS);
});
