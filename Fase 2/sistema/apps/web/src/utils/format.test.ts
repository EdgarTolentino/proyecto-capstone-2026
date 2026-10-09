import { expect, it } from "vitest";

import { duracionEnPalabras, formatearBytes, formatearReloj, formatearVelocidad } from "./format";

it.each([
  [0, "0 B"],
  [1, "1 B"],
  [1023, "1023 B"],
  [1024, "1,0 KB"],
  [1536, "1,5 KB"],
  [1048524, "1023,9 KB"], // 1023,949 KB: justo debajo del umbral de 1023,95, se queda en KB
  [1048525, "1,0 MB"], // 1023,950 KB: justo en el umbral, pasa a MB
  [1048575, "1,0 MB"], // 1023,999 KB redondea a 1024,0: pasa a la unidad siguiente
  [1048576, "1,0 MB"],
  [700 * 1024 * 1024, "700,0 MB"],
  [2 * 1024 ** 3, "2,0 GB"],
  [5 * 1024 ** 4, "5,0 TB"],
  [5000 * 1024 ** 4, "5000,0 TB"], // no hay unidad mayor
])("formatea %d bytes como %s", (bytes, esperado) => {
  expect(formatearBytes(bytes)).toBe(esperado);
});

it.each([-1, Number.NaN, Number.POSITIVE_INFINITY])("un tamaño inválido (%s) se muestra como guion", (bytes) => {
  expect(formatearBytes(bytes)).toBe("—");
});

it.each([
  [0, "0:00"],
  [9, "0:09"],
  [59, "0:59"], // justo antes del minuto
  [60, "1:00"], // justo en el minuto
  [150, "2:30"],
  [59.9, "0:59"], // los segundos sueltos se truncan, no se redondean
  [3599, "59:59"],
  [3600, "1:00:00"], // justo en la hora
  [3723, "1:02:03"],
])("formatea %d s como reloj %s", (segundos, esperado) => {
  expect(formatearReloj(segundos)).toBe(esperado);
});

it.each([-1, Number.NaN, Number.POSITIVE_INFINITY])("un reloj inválido (%s) se muestra como guion", (segundos) => {
  expect(formatearReloj(segundos)).toBe("—");
});

it.each([
  [0, "0 segundos"],
  [1, "1 segundo"],
  [30, "30 segundos"],
  [60, "1 minuto"],
  [61, "1 minuto 1 segundo"],
  [150, "2 minutos 30 segundos"],
  [300, "5 minutos"],
  [3600, "1 hora"],
  [3723, "1 hora 2 minutos 3 segundos"],
  [7200, "2 horas"],
])("dice %d s en palabras como «%s»", (segundos, esperado) => {
  expect(duracionEnPalabras(segundos)).toBe(esperado);
});

it("una duración inválida no se inventa", () => {
  expect(duracionEnPalabras(Number.NaN)).toBe("duración desconocida");
  expect(duracionEnPalabras(-3)).toBe("duración desconocida");
});

it.each([
  [0, "0,0× tiempo real"],
  [0.8, "0,8× tiempo real"],
  [1, "1,0× tiempo real"],
  [2.5, "2,5× tiempo real"],
  [12, "12,0× tiempo real"],
])("formatea la velocidad %d como «%s»", (velocidad, esperado) => {
  expect(formatearVelocidad(velocidad)).toBe(esperado);
});

it.each([-0.1, Number.NaN, Number.POSITIVE_INFINITY])("una velocidad inválida (%s) da null", (velocidad) => {
  expect(formatearVelocidad(velocidad)).toBeNull();
});
