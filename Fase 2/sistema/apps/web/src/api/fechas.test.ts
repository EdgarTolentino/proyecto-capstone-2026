import { describe, expect, it } from "vitest";

import { esFechaValida, fechaActualEnFaena, inicioDelDiaEnFaena, rangoDefectoPanel, sumarDias } from "./fechas";

describe("fechas de la faena", () => {
  it("valida el calendario, incluyendo años bisiestos y fechas imposibles", () => {
    expect(esFechaValida("2024-02-29")).toBe(true);
    expect(esFechaValida("2026-02-29")).toBe(false);
    expect(esFechaValida("2026-13-01")).toBe(false);
    expect(esFechaValida("2026-04-31")).toBe(false);
  });

  it("suma días de calendario sin depender de la zona local del navegador", () => {
    expect(sumarDias("2026-03-01", -1)).toBe("2026-02-28");
    expect(sumarDias("2024-03-01", -1)).toBe("2024-02-29");
  });

  it("calcula la fecha actual en la zona de la faena y muestra siete días calendario por defecto", () => {
    const ahora = new Date("2026-10-01T02:00:00.000Z");
    expect(fechaActualEnFaena(ahora)).toBe("2026-09-30");
    expect(rangoDefectoPanel(new Date("2026-10-01T12:00:00.000Z"))).toEqual({
      desde: "2026-09-25",
      hasta: "2026-10-01",
    });
  });

  it("convierte la medianoche según America/Santiago y el inicio real en un día DST", () => {
    expect(inicioDelDiaEnFaena("2026-10-01")).toBe("2026-10-01T03:00:00.000Z");
    expect(inicioDelDiaEnFaena("2026-09-06")).toBe("2026-09-06T04:00:00.000Z");
  });
});
