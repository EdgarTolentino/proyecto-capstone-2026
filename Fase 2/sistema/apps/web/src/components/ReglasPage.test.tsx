import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../api/client";
import type { Catalogos, Regla } from "../api/types";
import { ReglasPage } from "./ReglasPage";

vi.mock("../api/client", () => ({ listarReglas: vi.fn() }));

const catalogos: Catalogos = {
  areas: [
    { id: 3, nombre: "Excavación y Fundaciones" },
    { id: 5, nombre: "Bodega de Materiales" },
  ],
};

const reglas: Regla[] = [
  {
    id: 12,
    version: 3,
    nombre: "Casco obligatorio — Excavación",
    area_id: 3,
    epp_exigido: ["casco"],
    confirmacion_segundos: 2,
    cierre_segundos: 3,
    confianza_minima: 0.45,
    severidad: 3,
    activa: true,
    base_licitud: "obligacion_legal",
    finalidad_declarada: "Prevención de lesiones",
    retencion_dias: 30,
  },
  {
    id: 15,
    version: 1,
    nombre: "Chaleco en bodega",
    area_id: 5,
    epp_exigido: ["chaleco"],
    confirmacion_segundos: 1,
    cierre_segundos: 3,
    confianza_minima: 0.45,
    severidad: 2,
    activa: false,
    base_licitud: "obligacion_legal",
    finalidad_declarada: "Prevención de atropellos",
    retencion_dias: 30,
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReglasPage catalogos={catalogos} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("muestra nombre, área, estado y versión de cada regla", async () => {
  vi.mocked(api.listarReglas).mockResolvedValue(reglas);
  renderPage();

  expect(await screen.findByRole("cell", { name: "Excavación y Fundaciones" })).toBeVisible();
  expect(screen.getByRole("rowheader", { name: "Casco obligatorio — Excavación" })).toBeVisible();
  expect(screen.getByText("Activa")).toBeVisible();
  expect(screen.getByText("Inactiva")).toBeVisible();
  expect(screen.getByText("Versión 3")).toBeVisible();
});

it("vuelve a consultar el endpoint con el área seleccionada", async () => {
  vi.mocked(api.listarReglas).mockResolvedValue(reglas);
  renderPage();
  await screen.findByRole("table", { name: "Listado de reglas de seguridad" });

  fireEvent.change(screen.getByRole("combobox", { name: "Área" }), { target: { value: "5" } });

  await waitFor(() => expect(api.listarReglas).toHaveBeenLastCalledWith("5"));
});

it("muestra los estados de carga y lista vacía", async () => {
  let resolver: (reglas: Regla[]) => void = () => undefined;
  vi.mocked(api.listarReglas).mockImplementation(() => new Promise((resolve) => { resolver = resolve; }));
  renderPage();

  expect(screen.getByRole("status")).toHaveTextContent("Cargando reglas");
  resolver([]);
  expect(await screen.findByText("No hay reglas para el área seleccionada.")).toBeVisible();
});

it("muestra el error y permite reintentar", async () => {
  vi.mocked(api.listarReglas).mockRejectedValueOnce(new Error("sin red")).mockResolvedValueOnce([]);
  renderPage();

  expect(await screen.findByRole("alert")).toHaveTextContent("No fue posible cargar las reglas");
  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(await screen.findByText("No hay reglas para el área seleccionada.")).toBeVisible();
  expect(api.listarReglas).toHaveBeenCalledTimes(2);
});
