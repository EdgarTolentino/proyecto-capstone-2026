import { createElement } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Hallazgo } from "../api/types";
import { formatDuracion } from "../utils/format";
import { HallazgosGrid } from "./HallazgosGrid";

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: () => ({
    getTotalSize: () => 40,
    getVirtualItems: () => [{ index: 0, start: 0 }],
    scrollToIndex: vi.fn(),
  }),
}));

describe("formatDuracion", () => {
  it("muestra minutos y segundos en una sola línea", () => {
    expect(formatDuracion(192)).toBe("3 m 12 s");
    expect(formatDuracion(48)).toBe("48 s");
  });

  it("expone la fila activa y bloquea evidencia sin permiso", () => {
    const hallazgo = {
      id: 7,
      severidad: 4,
      epp_faltante: ["casco"],
      ts_inicio: "2026-09-07T12:00:00Z",
      duracion_s: 10,
      cuadros_confirmados: 5,
      confianza_media: 0.9,
    } as Hallazgo;
    render(createElement(HallazgosGrid, {
      hallazgos: [hallazgo],
      activoId: 7,
      seleccionados: new Set<number>(),
      permiteSeleccionar: false,
      permiteEvidencia: false,
      onActivate: vi.fn(),
      onOpen: vi.fn(),
      onSelect: vi.fn(),
      onSelectAll: vi.fn(),
    }));

    const grid = screen.getByRole("grid");
    expect(grid).toHaveAttribute("aria-activedescendant", "hallazgo-7");
    expect(grid).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("row", { name: /hallazgo 7/i })).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("button", { name: "Abrir evidencia del hallazgo 7" })).toBeDisabled();
  });
});
