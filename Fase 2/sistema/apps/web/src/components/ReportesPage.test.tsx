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
  isRefreshing: false,
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
  expect(within(grafico).getByText("≈ 10")).toBeVisible();
  expect(within(grafico).getByText("Datos insuficientes")).toBeVisible();
  expect(within(grafico).queryByText("999")).not.toBeInTheDocument();
  const tabla = screen.getByRole("table", { name: "Detalle del reporte: Incumplimientos por EPP" });
  expect(within(tabla).getByText("≈ 10")).toBeVisible();
  expect(within(tabla).queryByText("999")).not.toBeInTheDocument();
  expect(within(tabla).queryByRole("columnheader", { name: /^n$/i })).not.toBeInTheDocument();
  expect(screen.getByText(/cifras se redondean a múltiplos de 5/)).toBeVisible();
  expect(screen.getByRole("tab", { name: "Por EPP" })).toHaveAttribute("aria-selected", "true");
});

it("muestra el mapa de calor y la tendencia diaria sin revelar celdas suprimidas", () => {
  const { rerender } = render(<ReportesPage {...props} tipo="mapa-calor" reporte={{
    tipo: "mapa-calor",
    filas: [
      { etiqueta: "Zona norte · 08h", valor: 10, n: 10, datos_insuficientes: false },
      { etiqueta: "Zona norte · 09h", valor: 999, n: 999, datos_insuficientes: true },
    ],
  }} />);
  expect(screen.getByRole("cell", { name: "Zona norte, 08h: ≈ 10" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "Zona norte, 09h: Datos insuficientes" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "Zona norte, 10h: 0" })).toBeVisible();

  rerender(<ReportesPage {...props} tipo="mapa-calor" reporte={{
    tipo: "mapa-calor",
    filas: [
      { etiqueta: "Zona norte · 08h", valor: 10, n: 10, datos_insuficientes: false },
      { etiqueta: "Andamio Fachada Norte", valor: 25, n: 25, datos_insuficientes: false },
    ],
  }} />);
  expect(screen.getByRole("status")).toHaveTextContent("etiquetas compatibles");
  expect(screen.queryByRole("table", { name: /celdas ocultas/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("table", { name: /Detalle del reporte/ })).not.toBeInTheDocument();

  rerender(<ReportesPage {...props} tipo="tendencia" filtros={{ ...props.filtros, segmentacion: "turno" }} reporte={{
    tipo: "tendencia",
    filas: [
      { etiqueta: "Turno A · 2026-09-01", valor: 10, n: 10, datos_insuficientes: false },
      { etiqueta: "Turno B · 2026-09-01", valor: 999, n: 999, datos_insuficientes: true },
      { etiqueta: "Turno C · 2026-09-01", valor: null, n: 5, datos_insuficientes: false },
    ],
  }} />);
  const tendencia = screen.getByRole("region", { name: "Gráfico de tendencia diaria por turno" });
  expect(within(tendencia).getByText("≈ 10")).toBeVisible();
  expect(within(tendencia).getAllByText("Datos insuficientes")).toHaveLength(2);
  expect(within(tendencia).queryByText("999")).not.toBeInTheDocument();
  expect(tendencia.querySelectorAll(".reportes-ranking__bar")).toHaveLength(1);
});

it("trata un valor nulo como datos insuficientes aunque la fila no esté marcada", () => {
  const reporteNulo: Reporte = {
    tipo: "ranking-epp",
    filas: [{ etiqueta: "casco", valor: null, n: 5, datos_insuficientes: false }],
  };
  render(<ReportesPage {...props} reporte={reporteNulo} />);

  const grafico = screen.getByRole("region", { name: "Gráfico de incumplimientos por EPP" });
  expect(within(grafico).getByText("Datos insuficientes")).toBeVisible();
  expect(grafico.querySelector(".reportes-ranking__bar")).toBeNull();
  expect(screen.getByRole("table").querySelector("tbody")).toHaveTextContent("Datos insuficientes");
  expect(screen.queryByText(/^0$/)).not.toBeInTheDocument();
});

it("muestra la carga del filtro nuevo mientras conserva el reporte anterior", () => {
  render(<ReportesPage {...props} isRefreshing />);

  expect(screen.getByRole("status")).toHaveTextContent("Cargando reporte actualizado");
  expect(screen.getByRole("main", { name: "Reportes" })).toHaveAttribute("aria-busy", "true");
  expect(screen.getByRole("table")).toBeVisible();
  expect(screen.getByRole("button", { name: "Exportar CSV" })).toBeDisabled();
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
