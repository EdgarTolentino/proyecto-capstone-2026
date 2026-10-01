import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import * as api from "./api/client";

vi.mock("./api/client", () => ({
  ApiError: class extends Error {},
  listarHallazgos: vi.fn(async () => ({ items: [{ id: 1 }, { id: 2 }], contadores: {} })),
  obtenerSesion: vi.fn(async () => ({ permisos: ["ver_hallazgos", "ver_evidencia", "triar_hallazgos"] })),
  obtenerCatalogos: vi.fn(async () => ({})),
  obtenerPanel: vi.fn(async () => ({
    indicadores: [
      { clave: "hallazgos_abiertos", etiqueta: "Hallazgos abiertos", valor: 4, variacion: 0.25, serie: [1, 2, 3] },
      { clave: "criticos_sin_revisar", etiqueta: "Críticos sin revisar", valor: 1, variacion: -0.5, serie: [2, 1] },
      { clave: "cumplimiento_epp", etiqueta: "Cumplimiento de EPP", valor: 92.5, unidad: "%", variacion: 0.1, serie: [] },
      { clave: "zona_mas_incumplimientos", etiqueta: "Zona con más incumplimientos", valor: "Sector norte", variacion: null, serie: [] },
      { clave: "videos_procesados_hoy", etiqueta: "Videos procesados hoy", valor: 8, variacion: null, serie: [1, 4, 8] },
    ],
    tendencia: { etiquetas: [], series: [] },
    ranking_epp: [],
    criticos_recientes: [],
    cobertura: {},
  })),
  obtenerEstado: vi.fn(async () => ({})),
  triarHallazgo: vi.fn(async () => ({})),
  triarLote: vi.fn(async () => ({})),
}));
vi.mock("./components/HallazgoFilters", () => ({ HallazgoFilters: () => null }));
vi.mock("./components/TriageTabs", () => ({ TriageTabs: () => null }));
vi.mock("./components/ReglasPage", () => ({ ReglasPage: () => <section><h2>Reglas de seguridad</h2></section> }));
vi.mock("./components/HallazgosGrid", () => ({
  HallazgosGrid: ({ onOpen, onSelect }: { onOpen: (id: number) => void; onSelect: (id: number, checked: boolean) => void }) => (
    <div data-testid="bandeja"><button onClick={() => onOpen(2)}>Abrir segundo</button><button onClick={() => onSelect(1, true)}>Seleccionar primero</button></div>
  ),
}));
vi.mock("./components/EvidenceDrawer", () => ({
  EvidenceDrawer: ({ hallazgoId, onClose, onFalsePositive }: { hallazgoId: number; onClose: () => void; onFalsePositive: () => void }) => (
    <section role="dialog"><span>Caso {hallazgoId}</span><button onClick={onClose}>Cerrar visor</button><button onClick={onFalsePositive}>Descartar abierto</button></section>
  ),
}));

afterEach(() => { cleanup(); vi.clearAllMocks(); window.history.replaceState({}, "", "/"); });

async function iniciar() {
  if (!window.location.pathname.startsWith("/hallazgos")) window.history.replaceState({}, "", "/hallazgos");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  await screen.findByTestId("bandeja");
}

it("usa la raíz como panel general y permite volver a la bandeja", async () => {
  window.history.replaceState({}, "", "/");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

  expect(await screen.findByRole("heading", { name: "Panel general" })).toBeVisible();
  expect(await screen.findByText("Hallazgos abiertos")).toBeVisible();
  expect(screen.getByRole("region", { name: "Indicadores del panel" }).querySelectorAll(".panel-indicator")).toHaveLength(5);
  expect(api.obtenerPanel).toHaveBeenCalledWith();
  expect(screen.getByRole("button", { name: "Panel general" })).toHaveAttribute("aria-current", "page");

  fireEvent.click(within(screen.getByRole("navigation", { name: "Navegación principal" })).getByRole("button", { name: /Hallazgos/ }));
  expect(await screen.findByTestId("bandeja")).toBeVisible();
  expect(window.location.pathname).toBe("/hallazgos");

  fireEvent.click(screen.getByRole("button", { name: "Panel general" }));
  expect(await screen.findByRole("heading", { name: "Panel general" })).toBeVisible();
  expect(window.location.pathname).toBe("/");
});

it("mantiene la misma bandeja y consulta al abrir y cerrar el visor", async () => {
  await iniciar();
  const grid = screen.getByTestId("bandeja");
  fireEvent.click(screen.getByText("Abrir segundo"));
  await screen.findByText("Caso 2");
  fireEvent.click(screen.getByText("Cerrar visor"));
  expect(screen.getByTestId("bandeja")).toBe(grid);
  expect(api.listarHallazgos).toHaveBeenCalledTimes(1);
});

it("el atajo c confirma el caso abierto, no la primera fila", async () => {
  await iniciar();
  fireEvent.click(screen.getByText("Abrir segundo"));
  fireEvent.keyDown(window, { key: "c" });
  await waitFor(() => expect(api.triarHallazgo).toHaveBeenCalledWith(2, { estado: "confirmado" }));
});

it("descartar desde el visor no modifica una selección anterior", async () => {
  await iniciar();
  fireEvent.click(screen.getByText("Seleccionar primero"));
  fireEvent.click(screen.getByText("Abrir segundo"));
  fireEvent.click(screen.getByText("Descartar abierto"));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Prueba de revisión" } });
  fireEvent.click(screen.getByText("Guardar decisión"));
  await waitFor(() => expect(api.triarHallazgo).toHaveBeenCalledWith(2, { estado: "falso_positivo", motivo: "Prueba de revisión" }));
  expect(api.triarLote).not.toHaveBeenCalled();
});

it("muestra el error de sesión y permite reintentar cuando falla /yo", async () => {
  window.history.replaceState({}, "", "/hallazgos");
  vi.mocked(api.obtenerSesion).mockRejectedValueOnce(new Error("sin red"));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

  expect(await screen.findByRole("alert")).toHaveTextContent("No fue posible cargar la sesión");
  expect(screen.getByRole("button", { name: "Reintentar" })).toBeEnabled();
  expect(api.listarHallazgos).not.toHaveBeenCalled();
});

it("navega a Reglas y permite volver a Hallazgos", async () => {
  window.history.replaceState({}, "", "/hallazgos?area_id=5");
  await iniciar();

  fireEvent.click(screen.getByRole("button", { name: "Reglas" }));
  expect(await screen.findByRole("heading", { name: "Reglas de seguridad" })).toBeVisible();
  expect(window.location.pathname).toBe("/reglas");

  fireEvent.click(within(screen.getByRole("navigation", { name: "Navegación principal" })).getByRole("button", { name: /Hallazgos/ }));
  expect(await screen.findByTestId("bandeja")).toBeVisible();
  expect(window.location.pathname).toBe("/hallazgos");
  expect(window.location.search).toBe("?area_id=5");
});
