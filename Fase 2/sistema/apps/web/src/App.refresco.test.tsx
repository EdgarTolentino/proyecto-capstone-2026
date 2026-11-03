import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
  obtenerSesion: vi.fn(async () => ({ permisos: ["ver_hallazgos", "ver_evidencia", "triar_hallazgos"] })),
  triarLote: vi.fn(async () => ({ aplicados: 0 })),
  triarHallazgo: vi.fn(async () => ({})),
  obtenerCatalogos: vi.fn(async () => ({ obras: [], turnos: [] })),
  obtenerPanel: vi.fn(),
  obtenerEstado: vi.fn(async () => ({})),
  obtenerCuadrosVivo: vi.fn(),
}));
vi.mock("./components/HallazgoFilters", () => ({ HallazgoFilters: () => null }));
vi.mock("./components/TriageTabs", () => ({ TriageTabs: () => null }));
vi.mock("./components/HallazgosGrid", () => ({
  HallazgosGrid: ({ hallazgos, activoId, onSelect, onActivate }: { hallazgos: { id: number }[]; activoId?: number; onSelect: (id: number, marcado: boolean) => void; onActivate: (id: number) => void }) => (
    <ul aria-label="Bandeja">
      <li>Activo {activoId ?? "ninguno"}</li>
      {hallazgos.map((h) => (
        <li key={h.id}>Hallazgo {h.id} <button onClick={() => onSelect(h.id, true)}>Seleccionar {h.id}</button> <button onClick={() => onActivate(h.id)}>Activar {h.id}</button></li>
      ))}
    </ul>
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

it("un hallazgo seleccionado que sale de la página no se cuenta ni se envía en el lote", async () => {
  vi.mocked(api.listarHallazgos)
    .mockResolvedValueOnce({ items: [{ id: 3 }, { id: 2 }, { id: 1 }], contadores: {} } as never)
    .mockResolvedValue({ items: [{ id: 4 }, { id: 3 }, { id: 2 }], contadores: {} } as never);
  iniciar("/hallazgos");
  await screen.findByText("Hallazgo 1");
  fireEvent.click(screen.getByRole("button", { name: "Seleccionar 1" }));
  fireEvent.click(screen.getByRole("button", { name: "Seleccionar 2" }));
  expect(await screen.findByText("2 seleccionados")).toBeVisible();

  await avanzar(INTERVALO_BANDEJA_MS);

  // El 1 salió de la página: queda solo el 2.
  expect(await screen.findByText("Hallazgo 4")).toBeVisible();
  expect(screen.queryByText("Hallazgo 1")).not.toBeInTheDocument();
  expect(screen.getByText("1 seleccionados")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /Confirmar/ }));
  await vi.waitFor(() => expect(api.triarLote).toHaveBeenCalledTimes(1));
  expect(vi.mocked(api.triarLote).mock.calls[0][0]).toEqual([2]);
});

it("la fila activa no se corre a la primera cada vez que llega un hallazgo nuevo", async () => {
  vi.mocked(api.listarHallazgos)
    .mockResolvedValueOnce({ items: [{ id: 2 }, { id: 1 }], contadores: {} } as never)
    .mockResolvedValue({ items: [{ id: 3 }, { id: 2 }, { id: 1 }], contadores: {} } as never);
  iniciar("/hallazgos");
  expect(await screen.findByText("Activo 2")).toBeVisible();

  await avanzar(INTERVALO_BANDEJA_MS);

  expect(await screen.findByText("Hallazgo 3")).toBeVisible();
  // Si la activa siguiera siendo «la primera», pasaría a 3 y la grilla saltaría al principio.
  expect(screen.getByText("Activo 2")).toBeVisible();
});

it("si la fila activa sale de la lista no se pasa sola a la primera: queda sin activa", async () => {
  vi.mocked(api.listarHallazgos)
    .mockResolvedValueOnce({ items: [{ id: 3 }, { id: 2 }, { id: 1 }], contadores: {} } as never)
    .mockResolvedValue({ items: [{ id: 4 }, { id: 3 }, { id: 2 }], contadores: {} } as never);
  iniciar("/hallazgos");
  await screen.findByText("Hallazgo 1");
  fireEvent.click(screen.getByRole("button", { name: "Activar 1" })); // la última de la página

  await avanzar(INTERVALO_BANDEJA_MS);

  expect(await screen.findByText("Hallazgo 4")).toBeVisible();
  // Pasar a «Activo 4» movería la grilla al principio y los atajos actuarían sobre otra fila.
  expect(screen.getByText("Activo ninguno")).toBeVisible();
});

it("el falso positivo se guarda sobre lo seleccionado al abrir el diálogo, aunque la lista cambie", async () => {
  vi.mocked(api.listarHallazgos)
    .mockResolvedValueOnce({ items: [{ id: 3 }, { id: 2 }, { id: 1 }], contadores: {} } as never)
    .mockResolvedValue({ items: [{ id: 4 }, { id: 3 }, { id: 2 }], contadores: {} } as never);
  iniciar("/hallazgos");
  await screen.findByText("Hallazgo 1");
  fireEvent.click(screen.getByRole("button", { name: "Seleccionar 1" }));
  fireEvent.click(within(screen.getByRole("toolbar")).getByRole("button", { name: "Falso positivo" }));
  const dialogo = await screen.findByRole("dialog");
  fireEvent.change(within(dialogo).getByRole("textbox"), { target: { value: "reflejo" } });

  await avanzar(INTERVALO_BANDEJA_MS); // el 1 sale de la página con el diálogo abierto
  expect(await screen.findByText("Hallazgo 4")).toBeVisible();
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Guardar decisión" }));

  await vi.waitFor(() => expect(api.triarLote).toHaveBeenCalledTimes(1));
  expect(vi.mocked(api.triarLote).mock.calls[0][0]).toEqual([1]);
  expect(api.triarHallazgo).not.toHaveBeenCalled();
});

it("un lote con omitidos lo dice con el motivo que devuelve la API", async () => {
  vi.mocked(api.listarHallazgos)
    .mockResolvedValueOnce({ items: [{ id: 3 }, { id: 2 }, { id: 1 }], contadores: {} } as never)
    .mockResolvedValue({ items: [{ id: 4 }, { id: 3 }, { id: 2 }], contadores: {} } as never);
  vi.mocked(api.triarLote).mockResolvedValue({ aplicados: 1, omitidos: [{ id: 1, motivo: "no existe" }] } as never);
  iniciar("/hallazgos");
  await screen.findByText("Hallazgo 1");
  fireEvent.click(screen.getByRole("button", { name: "Seleccionar 1" }));
  fireEvent.click(screen.getByRole("button", { name: "Seleccionar 2" }));
  fireEvent.click(within(screen.getByRole("toolbar")).getByRole("button", { name: "Falso positivo" }));
  fireEvent.change(within(await screen.findByRole("dialog")).getByRole("textbox"), { target: { value: "reflejo" } });
  await avanzar(INTERVALO_BANDEJA_MS); // el 1 sale de la página con el diálogo abierto
  await screen.findByText("Hallazgo 4");
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Guardar decisión" }));

  // Sin este texto, «1 decisiones guardadas» escondería que el otro no se aplicó.
  expect(await screen.findByText("1 decisiones guardadas. 1 omitidas: no existe.")).toBeInTheDocument();
});

it("Enter, c o x sin fila activa avisan en vez de callar", async () => {
  vi.mocked(api.listarHallazgos)
    .mockResolvedValueOnce({ items: [{ id: 3 }, { id: 2 }, { id: 1 }], contadores: {} } as never)
    .mockResolvedValue({ items: [{ id: 4 }, { id: 3 }, { id: 2 }], contadores: {} } as never);
  iniciar("/hallazgos");
  await screen.findByText("Hallazgo 1");
  fireEvent.click(screen.getByRole("button", { name: "Activar 1" }));
  await avanzar(INTERVALO_BANDEJA_MS); // la activa sale de la lista
  expect(await screen.findByText("Activo ninguno")).toBeVisible();

  fireEvent.keyDown(window, { key: "c" });

  expect(await screen.findByText("Ningún hallazgo activo: usa j o haz clic en una fila.")).toBeInTheDocument();
});
