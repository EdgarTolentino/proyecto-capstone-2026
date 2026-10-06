import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import * as api from "./api/client";

vi.mock("./api/client", () => ({
  ApiError: class extends Error {
    constructor(message: string, public readonly status: number) { super(message); }
  },
  listarHallazgos: vi.fn(async () => ({ items: [{ id: 1 }, { id: 2 }], contadores: {} })),
  listarVideos: vi.fn(async () => ({ items: [] })),
  reprocesarVideo: vi.fn(async () => ({ estado: "listo" })),
  obtenerSesion: vi.fn(async () => ({ permisos: ["ver_hallazgos", "ver_evidencia", "triar_hallazgos"] })),
  obtenerCatalogos: vi.fn(async () => ({
    obras: [{ id: 7, nombre: "Edificio Norte" }, { id: 8, nombre: "Edificio Sur" }],
    turnos: [{ codigo: "A", etiqueta: "Turno A" }, { codigo: "B", etiqueta: "Turno B" }],
  })),
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
  window.history.replaceState({}, "", "/?obra_id=7&desde=2026-09-01&hasta=2026-09-30&turno=A");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

  expect(await screen.findByRole("heading", { name: "Panel general" })).toBeVisible();
  expect(await screen.findByText("Hallazgos abiertos")).toBeVisible();
  expect(screen.getByRole("region", { name: "Indicadores del panel" }).querySelectorAll(".panel-indicator")).toHaveLength(5);
  await waitFor(() => expect(api.obtenerPanel).toHaveBeenCalledWith({ obraId: 7, desde: "2026-09-01", hasta: "2026-09-30", turno: "A" }));
  expect(screen.getByRole("button", { name: "Panel general" })).toHaveAttribute("aria-current", "page");

  fireEvent.click(screen.getByRole("button", { name: "Ver Hallazgos abiertos en Hallazgos" }));
  expect(await screen.findByTestId("bandeja")).toBeVisible();
  expect(window.location.pathname).toBe("/hallazgos");
  expect(window.location.search).toContain("desde=2026-09-01");
  expect(window.location.search).toContain("hasta=2026-09-30");
  expect(window.location.search).toContain("turno=A");
  expect(window.location.search).not.toContain("obra_id=");
  expect(screen.getByText(/no ofrece filtro por obra/)).toBeVisible();
  await waitFor(() => expect(api.listarHallazgos).toHaveBeenCalledWith(expect.objectContaining({ desde: "2026-09-01", hasta: "2026-09-30", turno: "A" })));

  fireEvent.click(screen.getByRole("button", { name: "Panel general" }));
  expect(await screen.findByRole("heading", { name: "Panel general" })).toBeVisible();
  expect(window.location.pathname).toBe("/");
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Obra" })).toHaveValue("7"));
  await waitFor(() => expect(api.obtenerPanel).toHaveBeenLastCalledWith({ obraId: 7, desde: "2026-09-01", hasta: "2026-09-30", turno: "A" }));
});

it("lleva fecha y turno a Hallazgos al navegar desde la barra", async () => {
  window.history.replaceState({}, "", "/?desde=2026-09-01&hasta=2026-09-30&turno=A");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

  await screen.findByRole("heading", { name: "Panel general" });
  fireEvent.click(within(screen.getByRole("navigation", { name: "Navegación principal" })).getByRole("button", { name: /Hallazgos/ }));

  await screen.findByTestId("bandeja");
  expect(window.location.pathname).toBe("/hallazgos");
  expect(window.location.search).toBe("?desde=2026-09-01&hasta=2026-09-30&turno=A");
  await waitFor(() => expect(api.listarHallazgos).toHaveBeenCalledWith(expect.objectContaining({ desde: "2026-09-01", hasta: "2026-09-30", turno: "A" })));
});

it("restaura los filtros del panel y vuelve a consultar al cambiarlos", async () => {
  window.history.replaceState({}, "", "/?obra_id=7&desde=2026-09-01&hasta=2026-09-30&turno=A");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

  await waitFor(() => expect(screen.getByRole("combobox", { name: "Obra" })).toHaveValue("7"));
  expect(screen.getByLabelText("Desde")).toHaveValue("2026-09-01");
  expect(screen.getByLabelText("Hasta")).toHaveValue("2026-09-30");
  expect(screen.getByRole("combobox", { name: "Turno" })).toHaveValue("A");
  await waitFor(() => expect(api.obtenerPanel).toHaveBeenCalledWith({ obraId: 7, desde: "2026-09-01", hasta: "2026-09-30", turno: "A" }));

  fireEvent.change(screen.getByRole("combobox", { name: "Obra" }), { target: { value: "8" } });
  fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2026-09-08" } });
  fireEvent.change(screen.getByLabelText("Hasta"), { target: { value: "2026-10-01" } });
  fireEvent.change(screen.getByRole("combobox", { name: "Turno" }), { target: { value: "B" } });

  expect(window.location.search).toBe("?obra_id=8&desde=2026-09-08&hasta=2026-10-01&turno=B");
  await waitFor(() => expect(api.obtenerPanel).toHaveBeenLastCalledWith({ obraId: 8, desde: "2026-09-08", hasta: "2026-10-01", turno: "B" }));
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

it("muestra sin permiso si GET /panel responde 401 o 403", async () => {
  vi.mocked(api.obtenerPanel).mockRejectedValueOnce(new api.ApiError("sin permiso", 403));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

  expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para ver el panel general.");
  expect(screen.queryByText("No fue posible cargar el panel general.")).not.toBeInTheDocument();
});

it("mantiene los indicadores anteriores mientras carga el nuevo filtro", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  const indicador = await screen.findByRole("article", { name: "Hallazgos abiertos" });
  expect(indicador).toHaveTextContent("4");

  let resolver!: (panel: Awaited<ReturnType<typeof api.obtenerPanel>>) => void;
  vi.mocked(api.obtenerPanel).mockImplementationOnce(() => new Promise((resolve) => { resolver = resolve; }));
  fireEvent.change(screen.getByRole("combobox", { name: "Obra" }), { target: { value: "8" } });

  await waitFor(() => expect(api.obtenerPanel).toHaveBeenLastCalledWith(expect.objectContaining({ obraId: 8 })));
  expect(screen.getByRole("article", { name: "Hallazgos abiertos" })).toHaveTextContent("4");

  resolver({
    indicadores: [{ clave: "hallazgos_abiertos", etiqueta: "Hallazgos abiertos", valor: 9, variacion: 0, serie: [] }],
    tendencia: {}, ranking_epp: [], criticos_recientes: [], cobertura: {},
  });
  await waitFor(() => expect(screen.getByRole("article", { name: "Hallazgos abiertos" })).toHaveTextContent("9"));
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

it("abre la cola de videos desde la navegación y consulta listarVideos", async () => {
  window.history.replaceState({}, "", "/");
  vi.mocked(api.listarVideos).mockResolvedValueOnce({
    items: [{
      id: 22,
      archivo: "video.mp4",
      capture_ts_inicio: "2026-10-02T08:00:00Z",
      estado: "listo",
    }],
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

  await screen.findByRole("heading", { name: "Panel general" });
  fireEvent.click(screen.getByRole("button", { name: "Videos" }));

  expect(await screen.findByRole("heading", { name: "Cola de videos" })).toBeVisible();
  expect(window.location.pathname).toBe("/videos");
  expect(screen.getByRole("button", { name: "Videos" })).toHaveAttribute("aria-current", "page");
  await waitFor(() => expect(api.listarVideos).toHaveBeenCalledWith(undefined));
  expect(await screen.findByText("video.mp4")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Reprocesar video.mp4" })).not.toBeInTheDocument();
  expect(api.reprocesarVideo).not.toHaveBeenCalled();
});

it("con el permiso editar_reglas, la cola ofrece reprocesar", async () => {
  window.history.replaceState({}, "", "/videos");
  vi.mocked(api.obtenerSesion).mockResolvedValueOnce({ permisos: ["ver_hallazgos", "editar_reglas"] } as Awaited<ReturnType<typeof api.obtenerSesion>>);
  vi.mocked(api.listarVideos).mockResolvedValueOnce({
    items: [{ id: 22, archivo: "video.mp4", capture_ts_inicio: "2026-10-02T08:00:00Z", estado: "listo" }],
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);

  expect(await screen.findByRole("button", { name: "Reprocesar video.mp4" })).toBeVisible();
});
