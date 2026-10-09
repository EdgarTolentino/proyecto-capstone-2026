import { expect, it } from "vitest";

import type { Pedido, Video } from "./types";
import { INTERVALO_REFRESCO_MS, intervaloDePedidos, intervaloDeRefresco } from "./videos";

function videoDePrueba(estado: Video["estado"], id: number): Video {
  return { id, archivo: `v${id}.mp4`, capture_ts_inicio: "2026-10-02T08:00:00Z", estado };
}

it("refresca solo mientras haya videos pendientes", () => {
  const pagina = (...estados: Video["estado"][]) => ({ items: estados.map((e, i) => videoDePrueba(e, i)) });

  expect(intervaloDeRefresco(undefined)).toBe(false);
  expect(intervaloDeRefresco([pagina("listo", "error")])).toBe(false);
  expect(intervaloDeRefresco([pagina("listo"), pagina("en_cola")])).toBe(INTERVALO_REFRESCO_MS);
  expect(intervaloDeRefresco([pagina("procesando")])).toBe(INTERVALO_REFRESCO_MS);
  expect(intervaloDeRefresco([pagina("reintentando")])).toBe(INTERVALO_REFRESCO_MS);
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
