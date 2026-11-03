import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import App from "./App";
import * as api from "./api/client";
import { INTERVALO_BANDEJA_MS } from "./api/videos";

// La bandeja y el panel se refrescan solos: durante la demostración entran hallazgos mientras
// la pantalla está abierta. Estas pruebas miran lo que se VE, no que se llamara la consulta.
vi.mock("./api/client", () => ({
  ApiError: class extends Error {
    constructor(message: string, public readonly status: number) { super(message); }
  },
  listarHallazgos: vi.fn(),
  listarVideos: vi.fn(async () => ({ items: [] })),
  listarPedidos: vi.fn(async () => ({ items: [] })),
  listarEntradaVideos: vi.fn(async () => ({ items: [] })),
  obtenerSesion: vi.fn(async () => ({ permisos: ["ver_hallazgos", "ver_evidencia"] })),
  obtenerCatalogos: vi.fn(async () => ({ obras: [], turnos: [] })),
  obtenerPanel: vi.fn(),
  obtenerEstado: vi.fn(async () => ({})),
  obtenerCuadrosVivo: vi.fn(),
}));
vi.mock("./components/HallazgoFilters", () => ({ HallazgoFilters: () => null }));
vi.mock("./components/TriageTabs", () => ({ TriageTabs: () => null }));
vi.mock("./components/HallazgosGrid", () => ({
  HallazgosGrid: ({ hallazgos }: { hallazgos: { id: number }[] }) => (
    <ul aria-label="Bandeja">{hallazgos.map((h) => <li key={h.id}>Hallazgo {h.id}</li>)}</ul>
  ),
}));

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  vi.useRealTimers();
  focusManager.setFocused(undefined);
  window.history.replaceState({}, "", "/");
});

function iniciar(ruta: string) {
  window.history.replaceState({}, "", ruta);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
}

const avanzar = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

it("un hallazgo que entra después aparece en la bandeja sin recargar", async () => {
  vi.mocked(api.listarHallazgos)
    .mockResolvedValueOnce({ items: [{ id: 1 }], contadores: {} } as never)
    .mockResolvedValue({ items: [{ id: 2 }, { id: 1 }], contadores: {} } as never);
  iniciar("/hallazgos");

  expect(await screen.findByText("Hallazgo 1")).toBeVisible();
  expect(screen.queryByText("Hallazgo 2")).not.toBeInTheDocument();

  await avanzar(INTERVALO_BANDEJA_MS);

  expect(await screen.findByText("Hallazgo 2")).toBeVisible();
  expect(screen.getByText("Hallazgo 1")).toBeVisible();
});

it("con la pestaña oculta la bandeja no consulta, y al volver se pone al día", async () => {
  vi.mocked(api.listarHallazgos)
    .mockResolvedValueOnce({ items: [{ id: 1 }], contadores: {} } as never)
    .mockResolvedValue({ items: [{ id: 2 }, { id: 1 }], contadores: {} } as never);
  iniciar("/hallazgos");
  await screen.findByText("Hallazgo 1");

  act(() => focusManager.setFocused(false));
  await avanzar(INTERVALO_BANDEJA_MS * 3);
  expect(screen.queryByText("Hallazgo 2")).not.toBeInTheDocument();
  expect(api.listarHallazgos).toHaveBeenCalledTimes(1);

  act(() => focusManager.setFocused(true));
  expect(await screen.findByText("Hallazgo 2")).toBeVisible();
});

it("el panel muestra el valor nuevo de un indicador sin recargar", async () => {
  const panel = (valor: number) => ({
    indicadores: [{ clave: "hallazgos_abiertos", etiqueta: "Hallazgos abiertos", valor, variacion: null, serie: [] }],
    tendencia: { etiquetas: [], series: [] },
    ranking_epp: [],
    criticos_recientes: [],
    cobertura: {},
  });
  vi.mocked(api.obtenerPanel)
    .mockResolvedValueOnce(panel(4) as never)
    .mockResolvedValue(panel(5) as never);
  iniciar("/");

  const indicadores = await screen.findByRole("region", { name: "Indicadores del panel" });
  expect(indicadores).toHaveTextContent(/Hallazgos abiertos\s*4/);

  await avanzar(INTERVALO_BANDEJA_MS);

  await vi.waitFor(() => expect(indicadores).toHaveTextContent(/Hallazgos abiertos\s*5/));
});
