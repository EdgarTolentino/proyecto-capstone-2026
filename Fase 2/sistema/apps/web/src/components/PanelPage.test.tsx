import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { Panel } from "../api/types";
import { PanelPage } from "./PanelPage";

const panel: Panel = {
  indicadores: [
    { clave: "hallazgos_abiertos", etiqueta: "Hallazgos abiertos", valor: 34, variacion: 0.12, serie: [12, 15, 9, 18] },
    { clave: "criticos_sin_revisar", etiqueta: "Críticos sin revisar", valor: 5, variacion: -0.2, serie: [8, 7, 6, 5] },
    { clave: "cumplimiento_epp", etiqueta: "Cumplimiento de EPP", valor: 92.5, unidad: "%", variacion: 0, serie: [] },
    { clave: "zona_mas_incumplimientos", etiqueta: "Zona con más incumplimientos", valor: "Excavación", variacion: null, serie: [] },
    { clave: "videos_procesados_hoy", etiqueta: "Videos procesados hoy", valor: 18, variacion: null, serie: [7, 9, 18] },
  ],
  tendencia: {},
  ranking_epp: [],
  criticos_recientes: [],
  cobertura: {},
};

it("presenta las cinco tarjetas con valor, variación y tendencia del contrato", () => {
  const navegar = vi.fn();
  render(<PanelPage panel={panel} isLoading={false} isError={false} sinPermiso={false} onRetry={vi.fn()} onNavigateHallazgos={navegar} />);

  const indicadores = screen.getByRole("region", { name: "Indicadores del panel" });
  const tarjetas = within(indicadores).getAllByRole("article");
  expect(tarjetas).toHaveLength(5);
  expect(within(indicadores).getAllByRole("heading", { level: 3 })).toHaveLength(5);

  expect(screen.getByRole("article", { name: "Hallazgos abiertos" })).toHaveTextContent("↑ +12% vs. período anterior");
  expect(screen.getByRole("article", { name: "Críticos sin revisar" })).toHaveTextContent("↓ −20% vs. período anterior");
  expect(screen.getByRole("article", { name: "Cumplimiento de EPP" })).toHaveTextContent("92.5%");
  expect(screen.getByRole("article", { name: "Zona con más incumplimientos" })).toHaveTextContent("Sin comparación");

  expect(screen.getByRole("img", { name: "Tendencia de Hallazgos abiertos: 12, 15, 9, 18" })).toHaveAttribute("viewBox", "0 0 60 20");
  expect(within(indicadores).getAllByText("Sin tendencia")).toHaveLength(2);

  fireEvent.click(screen.getByRole("button", { name: "Ver Hallazgos abiertos en Hallazgos" }));
  fireEvent.click(screen.getByRole("button", { name: "Ver Críticos sin revisar en Hallazgos" }));
  expect(navegar).toHaveBeenNthCalledWith(1, { vista: "por_revisar" });
  expect(navegar).toHaveBeenNthCalledWith(2, { vista: "por_revisar", severidad: 4 });
  expect(within(indicadores).getAllByRole("button")).toHaveLength(2);
});
