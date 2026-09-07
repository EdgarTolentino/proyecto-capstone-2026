import { describe, expect, it } from "vitest";

import { formatDuracion } from "./HallazgosGrid";

describe("formatDuracion", () => {
  it("muestra minutos y segundos en una sola línea", () => {
    expect(formatDuracion(192)).toBe("3 m 12 s");
    expect(formatDuracion(48)).toBe("48 s");
  });
});
