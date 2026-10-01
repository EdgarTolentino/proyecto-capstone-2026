import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

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

afterEach(cleanup);

it("presenta las cinco tarjetas con valor, variación y tendencia del contrato", () => {
  const navegar = vi.fn();
  const { container } = render(<PanelPage panel={panel} isLoading={false} isError={false} sinPermiso={false} onRetry={vi.fn()} onNavigateHallazgos={navegar} />);

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
  expect(container.querySelectorAll("[data-panel-band]")).toHaveLength(3);
});

it("presenta la carga sin exponer datos anteriores", () => {
  const { container } = render(<PanelPage panel={panel} isLoading isError={false} sinPermiso={false} onRetry={vi.fn()} onNavigateHallazgos={vi.fn()} />);

  expect(screen.getByRole("main")).toHaveAttribute("aria-busy", "true");
  expect(screen.getByRole("status")).toHaveTextContent("Cargando panel…");
  expect(container.querySelectorAll("[data-panel-band]")).toHaveLength(0);
});

it("presenta el error, oculta datos anteriores y permite reintentar", () => {
  const reintentar = vi.fn();
  const { container } = render(<PanelPage panel={panel} isLoading={false} isError sinPermiso={false} onRetry={reintentar} onNavigateHallazgos={vi.fn()} />);

  expect(screen.getByRole("alert")).toHaveTextContent("No fue posible cargar el panel general.");
  expect(container.querySelectorAll("[data-panel-band]")).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(reintentar).toHaveBeenCalledOnce();
});

it("prioriza la falta de permiso y no muestra datos conservados", () => {
  const { container } = render(<PanelPage panel={panel} isLoading={false} isError={false} sinPermiso onRetry={vi.fn()} onNavigateHallazgos={vi.fn()} />);

  expect(screen.getByRole("alert")).toHaveTextContent("No tienes permiso para ver el panel general.");
  expect(container.querySelectorAll("[data-panel-band]")).toHaveLength(0);
});

it("presenta un estado vacío único cuando el contrato no contiene información", () => {
  const panelVacio: Panel = {
    indicadores: [],
    tendencia: {},
    ranking_epp: [],
    criticos_recientes: [],
    cobertura: {},
  };
  const { container } = render(<PanelPage panel={panelVacio} isLoading={false} isError={false} sinPermiso={false} onRetry={vi.fn()} onNavigateHallazgos={vi.fn()} />);

  expect(screen.getByRole("status")).toHaveTextContent("No hay información disponible para el período seleccionado.");
  expect(container.querySelectorAll("[data-panel-band]")).toHaveLength(0);
});

it("activa la primera tarjeta navegable usando solo el teclado", async () => {
  const navegar = vi.fn();
  const usuario = userEvent.setup();
  render(<PanelPage panel={panel} isLoading={false} isError={false} sinPermiso={false} onRetry={vi.fn()} onNavigateHallazgos={navegar} />);

  await usuario.tab();
  expect(screen.getByRole("button", { name: "Ver Hallazgos abiertos en Hallazgos" })).toHaveFocus();
  await usuario.keyboard("{Enter}");
  expect(navegar).toHaveBeenCalledWith({ vista: "por_revisar" });
});
