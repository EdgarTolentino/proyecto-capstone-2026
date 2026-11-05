import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { Reporte, TipoReporte } from "../api/types";
import { ReportesPage } from "./ReportesPage";

const reporte: Reporte = {
  tipo: "ranking-epp",
  segmentacion: "epp",
  filas: [
    { etiqueta: "casco", valor: 10, n: 10, datos_insuficientes: false },
    { etiqueta: "chaleco", valor: 999, n: 999, datos_insuficientes: true },
  ],
};
const props = {
  reporte,
  tipo: "ranking-epp" as TipoReporte,
  filtros: { desde: "2026-09-01", hasta: "2026-09-30" },
  catalogos: { areas: [{ id: 3, nombre: "Excavación" }] },
  isLoading: false,
  isError: false,
  sinPermiso: false,
  onRetry: vi.fn(),
  onChangeTipo: vi.fn(),
  onChangeFilters: vi.fn(),
  onDownloadCsv: vi.fn(async () => "etiqueta,valor,n"),
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("muestra el ranking sin exponer conteos suprimidos ni n", () => {
  render(<ReportesPage {...props} />);
  const grafico = screen.getByRole("region", { name: "Gráfico de incumplimientos por EPP" });
  expect(within(grafico).getByText("10")).toBeVisible();
  expect(within(grafico).getByText("Datos insuficientes")).toBeVisible();
  expect(within(grafico).queryByText("999")).not.toBeInTheDocument();
  const tabla = screen.getByRole("table", { name: "Detalle del reporte: Incumplimientos por EPP" });
  expect(within(tabla).queryByText("999")).not.toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Por EPP" })).toHaveAttribute("aria-selected", "true");
});

it("propaga filtros y permite restablecerlos", () => {
  render(<ReportesPage {...props} />);
  const filtros = screen.getByRole("group", { name: "Filtros de reportes" });
  fireEvent.change(within(filtros).getByLabelText("Desde"), { target: { value: "2026-09-05" } });
  fireEvent.change(within(filtros).getByRole("combobox", { name: "Área" }), { target: { value: "3" } });
  fireEvent.change(within(filtros).getByRole("combobox", { name: "Segmentar por" }), { target: { value: "zona" } });
  fireEvent.click(screen.getByRole("tab", { name: "Por zona" }));
  fireEvent.click(within(filtros).getByRole("button", { name: "Restablecer filtros de reportes" }));
  expect(props.onChangeFilters).toHaveBeenNthCalledWith(1, { desde: "2026-09-05" });
  expect(props.onChangeFilters).toHaveBeenNthCalledWith(2, { areaId: 3 });
  expect(props.onChangeFilters).toHaveBeenNthCalledWith(3, { segmentacion: "zona" });
  expect(props.onChangeTipo).toHaveBeenCalledWith("zonas");
  expect(props.onChangeFilters).toHaveBeenNthCalledWith(4, { desde: undefined, hasta: undefined, areaId: undefined, segmentacion: undefined });
});

it("muestra error, permiso, vacío y error de exportación", async () => {
  const { rerender } = render(<ReportesPage {...props} isError />);
  expect(screen.getByRole("alert")).toHaveTextContent("No fue posible cargar el reporte");
  rerender(<ReportesPage {...props} reporte={undefined} sinPermiso />);
  expect(screen.getByRole("alert")).toHaveTextContent("No tienes permiso para ver reportes");
  rerender(<ReportesPage {...props} reporte={{ tipo: "ranking-epp", filas: [] }} />);
  expect(screen.getByRole("status")).toHaveTextContent("No hay información");
  const onDownloadCsv = vi.fn().mockRejectedValue(new Error("Exportación temporalmente no disponible."));
  rerender(<ReportesPage {...props} onDownloadCsv={onDownloadCsv} />);
  fireEvent.click(screen.getByRole("button", { name: "Exportar CSV" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Exportación temporalmente no disponible.");
});
