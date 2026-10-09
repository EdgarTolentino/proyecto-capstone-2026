import { expect, it } from "vitest";

import { LIMITE_SIN_CUADRO_S, vistaTerminada } from "./reproductorVivo";

// Valores diádicos: el umbral y sus vecinos son exactos en coma flotante.
it.each([
  [0, 59_750, false],
  [0, 60_000, true],
  [0, 60_250, true],
  [1_000, 60_750, false],
  [1_000, 61_000, true],
])("la racha de 404 que empezó en %d ms, vista a los %d ms, terminó: %s", (primero, ahora, esperado) => {
  expect(LIMITE_SIN_CUADRO_S).toBe(60);
  expect(vistaTerminada(primero, ahora)).toBe(esperado);
});

it("sin racha de 404 la vista no terminó", () => {
  expect(vistaTerminada(undefined, 1e12)).toBe(false);
});

it.each([Number.NaN, Number.POSITIVE_INFINITY, -1])("un reloj inválido (%s) no declara terminada la vista", (ahora) => {
  expect(vistaTerminada(0, ahora)).toBe(false);
});

it("un reloj que retrocede (ahora anterior al inicio de la racha) no declara terminada la vista", () => {
  expect(vistaTerminada(100_000, 10_000)).toBe(false);
});
