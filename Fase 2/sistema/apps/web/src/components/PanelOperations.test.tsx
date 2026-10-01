import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import type { Hallazgo } from "../api/types";
import { PanelOperations } from "./PanelOperations";

afterEach(cleanup);

function hallazgo(id: number): Hallazgo {
  return {
    id,
    area: { id: 3, nombre: "Excavación" },
    zona: { id: 11, nombre: "Borde norte" },
    fuente: { id: 1, nombre: "CAM-01" },
    epp_faltante: ["casco"],
    severidad: 4,
    ts_inicio: `2026-09-${String(id).padStart(2, "0")}T10:14:07-03:00`,
    duracion_s: 12,
    cuadros_confirmados: 60,
    confianza_media: 0.91,
    estado: "por_revisar",
    aviso_legal: "Indicio automatizado. Requiere validación humana.",
  };
}

it("limita los críticos a ocho y detalla las fuentes sin cobertura", () => {
  render(
    <PanelOperations
      criticos={Array.from({ length: 9 }, (_item, indice) => hallazgo(indice + 1))}
      cobertura={{
        fuentes_activas: 3,
        fuentes_totales: 4,
        sin_cobertura: [{ fuente: { id: 4, nombre: "CAM-04" }, motivo: "requiere_recalibracion", desde: "2026-09-01T08:00:00-03:00" }],
      }}
    />,
  );

  const criticos = screen.getByRole("list", { name: "Hallazgos críticos recientes" });
  expect(within(criticos).getAllByRole("listitem")).toHaveLength(8);
  expect(within(criticos).getByText(/Hallazgo #8/)).toBeVisible();
  expect(within(criticos).queryByText(/Hallazgo #9/)).not.toBeInTheDocument();

  expect(screen.getByRole("progressbar", { name: "3 de 4 fuentes activas" })).toHaveValue(3);
  const sinCobertura = screen.getByRole("list", { name: "Fuentes sin cobertura" });
  expect(sinCobertura).toHaveTextContent("CAM-04");
  expect(sinCobertura).toHaveTextContent("Requiere recalibración");
});

it("explica el estado vacío y confirma la cobertura completa", () => {
  render(<PanelOperations criticos={[]} cobertura={{ fuentes_activas: 4, fuentes_totales: 4, sin_cobertura: [] }} />);

  expect(screen.getByText("No hay hallazgos críticos en el período.")).toBeVisible();
  expect(screen.getByText("Cobertura completa")).toBeVisible();
  expect(screen.queryByRole("list", { name: "Fuentes sin cobertura" })).not.toBeInTheDocument();
});
