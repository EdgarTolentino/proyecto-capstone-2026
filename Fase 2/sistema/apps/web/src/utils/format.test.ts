import { expect, it } from "vitest";

import { formatearBytes } from "./format";

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
