import { expect, it } from "vitest";

import type { Pedido, Video } from "./types";
import { INTERVALO_AVANCE_MS, INTERVALO_REFRESCO_MS, intervaloDePedidos, intervaloDeRefresco } from "./videos";

function videoDePrueba(estado: Video["estado"], id: number): Video {
  return { id, archivo: `v${id}.mp4`, capture_ts_inicio: "2026-10-02T08:00:00Z", estado };
}

it("refresca solo mientras haya videos pendientes", () => {
  const pagina = (...estados: Video["estado"][]) => ({ items: estados.map((e, i) => videoDePrueba(e, i)) });

  expect(intervaloDeRefresco(undefined)).toBe(false);
  expect(intervaloDeRefresco([pagina("listo", "error")])).toBe(false);
  // Los valores van escritos aquí a propósito: comparar contra la constante de producción no
  // detectaría que alguien la cambiara.
  expect(INTERVALO_REFRESCO_MS).toBe(10_000);
  expect(INTERVALO_AVANCE_MS).toBe(3_000);
  expect(intervaloDeRefresco([pagina("listo"), pagina("en_cola")])).toBe(10_000);
  expect(intervaloDeRefresco([pagina("reintentando")])).toBe(10_000);
  expect(intervaloDeRefresco([pagina("en_cola", "reintentando")])).toBe(10_000);
  expect(intervaloDeRefresco([pagina("procesando")])).toBe(3_000);
  expect(intervaloDeRefresco([pagina("listo"), pagina("procesando")])).toBe(3_000);
  // Con uno procesando manda el ritmo rápido, aunque otros esperen en la cola.
  expect(intervaloDeRefresco([pagina("en_cola", "procesando", "reintentando")])).toBe(3_000);
  expect(intervaloDeRefresco([pagina("en_cola"), pagina("procesando")])).toBe(3_000);
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
