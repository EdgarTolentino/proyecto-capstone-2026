import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../api/client";
import type { Catalogos, Regla } from "../api/types";
import { ReglasPage } from "./ReglasPage";

vi.mock("../api/client", () => ({ listarReglas: vi.fn(), crearRegla: vi.fn(), actualizarRegla: vi.fn(), simularRegla: vi.fn(), ApiError: class extends Error {} }));

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

function renderPage(puedeEditar = true) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReglasPage catalogos={catalogos} puedeEditar={puedeEditar} />
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

  fireEvent.change(screen.getAllByRole("combobox", { name: "Área" })[0], { target: { value: "5" } });

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

it("crea una regla con los valores requeridos", async () => {
  vi.mocked(api.listarReglas).mockResolvedValue([]);
  vi.mocked(api.crearRegla).mockResolvedValue({ ...reglas[0], id: 20, version: 1 });
  renderPage();
  await screen.findByText("No hay reglas para el área seleccionada.");
  fireEvent.click(screen.getByRole("button", { name: "Nueva regla" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Nombre" }), { target: { value: "Casco en bodega" } });
  fireEvent.change(screen.getAllByRole("combobox", { name: "Área" })[0], { target: { value: "5" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "casco" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Finalidad declarada" }), { target: { value: "Prevenir lesiones" } });
  fireEvent.click(screen.getByRole("button", { name: "Crear regla" }));
  await waitFor(() => expect(api.crearRegla).toHaveBeenCalledWith(expect.objectContaining({ nombre: "Casco en bodega", area_id: 5, epp_exigido: ["casco"], finalidad_declarada: "Prevenir lesiones", confirmacion_segundos: 2 })));
});

it("guarda la edición mediante una nueva versión", async () => {
  vi.mocked(api.listarReglas).mockResolvedValue(reglas);
  vi.mocked(api.actualizarRegla).mockResolvedValue({ ...reglas[0], version: 4 });
  renderPage();
  await screen.findByRole("table", { name: "Listado de reglas de seguridad" });
  fireEvent.click(screen.getAllByRole("button", { name: "Editar" })[0]);
  expect(screen.getByRole("textbox", { name: /Nombre/ })).toBeDisabled();
  expect(screen.getByRole("combobox", { name: /Área Inmutable al editar/ })).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "Finalidad declarada" }), { target: { value: "Nueva finalidad" } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar nueva versión" }));
  await waitFor(() => expect(api.actualizarRegla).toHaveBeenCalledWith(12, expect.objectContaining({ finalidad_declarada: "Nueva finalidad" })));
});

it("mantiene la consulta sin controles de edición cuando falta el permiso", async () => {
  vi.mocked(api.listarReglas).mockResolvedValue(reglas);
  renderPage(false);
  await screen.findByRole("table", { name: "Listado de reglas de seguridad" });
  expect(screen.queryByRole("button", { name: "Nueva regla" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
  expect(screen.getByText("Vista de consulta")).toBeVisible();
});

it("simula los cambios actuales sin guardar una nueva versión", async () => {
  vi.mocked(api.listarReglas).mockResolvedValue(reglas);
  vi.mocked(api.simularRegla).mockResolvedValue({ hallazgos_estimados: 38, contra_version_vigente: { actuales: 47, variacion: -9 }, alertas_por_turno_estimadas: 3.2 });
  renderPage();
  await screen.findByRole("table", { name: "Listado de reglas de seguridad" });
  fireEvent.click(screen.getAllByRole("button", { name: "Editar" })[0]);
  fireEvent.change(screen.getByRole("textbox", { name: "Finalidad declarada" }), { target: { value: "Simulación sin guardar" } });
  fireEvent.click(screen.getByRole("button", { name: "Simular sobre últimos 30 días" }));
  await waitFor(() => expect(api.simularRegla).toHaveBeenCalledWith(12, expect.objectContaining({ regla: expect.objectContaining({ finalidad_declarada: "Simulación sin guardar" }) })));
  expect(await screen.findByText("Habría generado 38 hallazgos.")).toBeVisible();
  expect(screen.getByText("Variación frente a la versión vigente: -9.")).toBeVisible();
});

it("informa el error de simulación y conserva el editor", async () => {
  vi.mocked(api.listarReglas).mockResolvedValue(reglas);
  vi.mocked(api.simularRegla).mockRejectedValue(new Error("sin red"));
  renderPage();
  await screen.findByRole("table", { name: "Listado de reglas de seguridad" });
  fireEvent.click(screen.getAllByRole("button", { name: "Editar" })[0]);
  fireEvent.click(screen.getByRole("button", { name: "Simular sobre últimos 30 días" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos ejecutar la simulación");
  expect(screen.getByRole("heading", { name: "Editar regla" })).toBeVisible();
  expect(api.actualizarRegla).not.toHaveBeenCalled();
});

it("requiere seleccionar al menos un EPP antes de crear", async () => {
  vi.mocked(api.listarReglas).mockResolvedValue([]);
  renderPage();
  await screen.findByText("No hay reglas para el área seleccionada.");
  fireEvent.click(screen.getByRole("button", { name: "Nueva regla" }));
  expect(screen.getByRole("button", { name: "Crear regla" })).toBeDisabled();
});
