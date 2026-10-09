import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { Video } from "../api/types";
import * as api from "../api/client";
import { INTERVALO_REFRESCO_MS } from "../api/videos";
import { VideosPage } from "./VideosPage";

vi.mock("../api/client", () => ({
  ApiError: class extends Error {
    constructor(message: string, public readonly status: number, public readonly codigo?: string) { super(message); }
  },
  listarVideos: vi.fn(),
  reprocesarVideo: vi.fn(),
  listarPedidos: vi.fn(),
  listarEntradaVideos: vi.fn(),
  pedirIngesta: vi.fn(),
  obtenerCuadrosVivo: vi.fn(),
}));

afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers(); });

function videoDePrueba(estado: Video["estado"]): Video {
  return {
    id: 22,
    archivo: "CAM-03_2026-10-02_08-00.mp4",
    capture_ts_inicio: "2026-10-02T08:00:00Z",
    estado,
    intentos: estado === "error" ? 3 : 0,
    error_motivo: estado === "error" ? "No se pudo leer el video" : null,
  };
}

it("muestra un video en error con cámara, intentos y motivo", async () => {
  const video: Video = {
    id: 22,
    archivo: "CAM-03_2026-10-02_08-00.mp4",
    fuente: { id: 3, nombre: "CAM-03" },
    capture_ts_inicio: "2026-10-02T08:00:00Z",
    estado: "error",
    intentos: 3,
    error_motivo: "No se pudo leer el video",
  };
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [video] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><VideosPage /></QueryClientProvider>);

  const tabla = await screen.findByRole("table", { name: "Cola de videos" });
  const fila = within(tabla).getByRole("row", { name: /CAM-03_2026-10-02_08-00\.mp4/ });
  expect(within(fila).getByText("CAM-03")).toBeVisible();
  expect(within(fila).getByText("Error").closest(".video-status")).toHaveClass("video-status--error");
  expect(within(fila).getByText("3")).toBeVisible();
  expect(within(fila).getByText("No se pudo leer el video")).toBeVisible();
  expect(api.listarVideos).toHaveBeenCalledWith(undefined);
});

it.each([
  ["en_cola", "En cola", "queued"],
  ["procesando", "Procesando", "processing"],
  ["reintentando", "Reintentando", "retrying"],
  ["listo", "Listo", "ready"],
  ["error", "Error", "error"],
] as const)("muestra el estado %s con texto y color", async (estado, nombre, clase) => {
  vi.mocked(api.listarVideos).mockResolvedValue({
    items: [{
      id: 22,
      archivo: "video.mp4",
      capture_ts_inicio: "2026-10-02T08:00:00Z",
      estado,
    }],
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><VideosPage /></QueryClientProvider>);

  expect((await screen.findByText(nombre)).closest(".video-status")).toHaveClass(`video-status--${clase}`);
});

it("no duplica videos ni sigue paginando si la API repite la página y el cursor", async () => {
  const video = videoDePrueba("listo");
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [video], siguiente_cursor: "cursor-1" })
    .mockResolvedValueOnce({ items: [video], siguiente_cursor: "cursor-1" });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><VideosPage /></QueryClientProvider>);

  fireEvent.click(await screen.findByRole("button", { name: "Cargar más videos" }));

  await waitFor(() => expect(api.listarVideos).toHaveBeenCalledTimes(2));
  expect(api.listarVideos).toHaveBeenNthCalledWith(2, "cursor-1");
  expect(screen.getAllByRole("row")).toHaveLength(2);
  expect(screen.queryByRole("button", { name: "Cargar más videos" })).not.toBeInTheDocument();
});

function renderizar(puedeEditarReglas = false) {
  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><VideosPage puedeEditarReglas={puedeEditarReglas} /></QueryClientProvider>);
  return client;
}

it("muestra el estado vacío cuando no hay videos", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [] });
  renderizar();

  expect(await screen.findByText("No hay videos en la cola.")).toBeVisible();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

it("muestra el error con opción de reintentar", async () => {
  vi.mocked(api.listarVideos).mockRejectedValueOnce(new api.ApiError("fallo", 500));
  renderizar();

  expect(await screen.findByText(/No fue posible cargar la cola de videos/)).toBeVisible();
  vi.mocked(api.listarVideos).mockResolvedValueOnce({ items: [videoDePrueba("listo")] });
  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(await screen.findByRole("table", { name: "Cola de videos" })).toBeVisible();
});

it.each([401, 403])("muestra «sin permiso» ante un %i, sin ofrecer reintento", async (status) => {
  vi.mocked(api.listarVideos).mockRejectedValue(new api.ApiError("sin permiso", status));
  renderizar();

  expect(await screen.findByText("No tienes permiso para ver la cola de videos.")).toBeVisible();
  expect(screen.queryByText(/No fue posible cargar/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
});

it("muestra el error de «Cargar más» junto al botón y conserva la tabla", async () => {
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [videoDePrueba("listo")], siguiente_cursor: "cursor-1" })
    .mockRejectedValueOnce(new api.ApiError("fallo", 500));
  renderizar();

  fireEvent.click(await screen.findByRole("button", { name: "Cargar más videos" }));
  expect(await screen.findByText("No fue posible cargar más videos.")).toBeVisible();
  expect(screen.getByRole("table", { name: "Cola de videos" })).toBeVisible();
  expect(screen.queryByText(/No fue posible cargar la cola de videos/)).not.toBeInTheDocument();

  vi.mocked(api.listarVideos).mockResolvedValueOnce({ items: [{ ...videoDePrueba("error"), id: 23, archivo: "otro.mp4" }] });
  fireEvent.click(screen.getByRole("button", { name: "Reintentar cargar más" }));
  expect(await screen.findByText("otro.mp4")).toBeVisible();
  expect(api.listarVideos).toHaveBeenLastCalledWith("cursor-1");
  expect(screen.queryByText("No fue posible cargar más videos.")).not.toBeInTheDocument();
});

it.each([401, 403])("un %i en «Cargar más» no oculta la tabla ni ofrece reintento", async (status) => {
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [videoDePrueba("listo")], siguiente_cursor: "cursor-1" })
    .mockRejectedValueOnce(new api.ApiError("sin permiso", status));
  renderizar();

  fireEvent.click(await screen.findByRole("button", { name: "Cargar más videos" }));
  expect(await screen.findByText("No tienes permiso para ver más videos.")).toBeVisible();
  expect(screen.getByRole("table", { name: "Cola de videos" })).toBeVisible();
  expect(screen.queryByText("No tienes permiso para ver la cola de videos.")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Reintentar/ })).not.toBeInTheDocument();
});

it.each([
  [1, "1 video cargado"],
  [2, "2 videos cargados"],
])("resume %i video(s) con el número correcto", async (cantidad, texto) => {
  const items = Array.from({ length: cantidad }, (_, i) => ({ ...videoDePrueba("listo"), id: i + 1, archivo: `v${i}.mp4` }));
  vi.mocked(api.listarVideos).mockResolvedValue({ items });
  renderizar();

  expect(await screen.findByText(texto)).toBeVisible();
});

it.each([
  ["en_cola", false],
  ["procesando", false],
  ["listo", false],
  ["reintentando", true],
  ["error", true],
] as const)("en %s muestra el motivo del error: %s", async (estado, visible) => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [{ ...videoDePrueba(estado), error_motivo: "motivo anterior" }] });
  renderizar();

  await screen.findByRole("table", { name: "Cola de videos" });
  expect(screen.queryByText("motivo anterior") !== null).toBe(visible);
});

it("vuelve a pedir la cola cuando hay un video procesando y deja de pedirla al terminar", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [videoDePrueba("procesando")] })
    .mockResolvedValue({ items: [videoDePrueba("listo")] });
  renderizar();

  expect(await screen.findByText("Procesando")).toBeVisible();
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS);
  expect(await screen.findByText("Listo")).toBeVisible();
  const llamadas = vi.mocked(api.listarVideos).mock.calls.length;
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS * 3);
  expect(api.listarVideos).toHaveBeenCalledTimes(llamadas);
});

it.each([500, 401])("si el refresco falla con un %i, conserva la tabla, avisa sin tapar y deja de pedir", async (status) => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [videoDePrueba("procesando")] })
    .mockRejectedValue(new api.ApiError("fallo", status));
  renderizar();

  expect(await screen.findByText("Procesando")).toBeVisible();
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS);
  expect(await screen.findByText(/No fue posible actualizar la cola/)).toBeVisible();
  expect(screen.getByRole("table", { name: "Cola de videos" })).toBeVisible();
  expect(screen.queryByText(/No fue posible cargar la cola de videos/)).not.toBeInTheDocument();
  expect(screen.queryByText("No tienes permiso para ver la cola de videos.")).not.toBeInTheDocument();

  const llamadas = vi.mocked(api.listarVideos).mock.calls.length;
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS * 3);
  expect(api.listarVideos).toHaveBeenCalledTimes(llamadas);
});

it("reintenta el refresco fallido y vuelve a mostrar los datos al día", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [videoDePrueba("procesando")] })
    .mockRejectedValueOnce(new api.ApiError("fallo", 500))
    .mockResolvedValue({ items: [videoDePrueba("listo")] });
  renderizar();

  await screen.findByText("Procesando");
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS);
  await screen.findByText(/No fue posible actualizar la cola/);
  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(await screen.findByText("Listo")).toBeVisible();
  expect(screen.queryByText(/No fue posible actualizar la cola/)).not.toBeInTheDocument();
});

it("mientras se refresca tras un error de «Cargar más», no anuncia un fallo que no ocurrió", async () => {
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [videoDePrueba("listo")], siguiente_cursor: "cursor-1" })
    .mockRejectedValueOnce(new api.ApiError("fallo", 500))
    .mockReturnValue(new Promise(() => undefined));
  const client = renderizar();

  fireEvent.click(await screen.findByRole("button", { name: "Cargar más videos" }));
  await screen.findByText("No fue posible cargar más videos.");
  void client.refetchQueries({ queryKey: ["videos"] });
  await waitFor(() => expect(api.listarVideos).toHaveBeenCalledTimes(3));

  expect(screen.queryByText(/No fue posible actualizar la cola/)).not.toBeInTheDocument();
  expect(screen.queryByText(/No fue posible cargar la cola de videos/)).not.toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Cola de videos" })).toBeVisible();
});

async function pulsarReprocesar(video: Video) {
  fireEvent.click(await screen.findByRole("button", { name: `Reprocesar ${video.archivo}` }));
  await waitFor(() => expect(api.reprocesarVideo).toHaveBeenCalledWith(video.id));
}

it("reprocesar un video listo recalcula sin GPU, lo comunica e invalida la lista", async () => {
  const video = videoDePrueba("listo");
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [video] });
  vi.mocked(api.reprocesarVideo).mockResolvedValue(video);
  renderizar(true);

  await pulsarReprocesar(video);
  expect(await screen.findByText(`Las reglas de ${video.archivo} se recalcularon sin usar la GPU.`)).toBeVisible();
  await waitFor(() => expect(api.listarVideos).toHaveBeenCalledTimes(2));
});

it("reprocesar un video en error lo devuelve a la cola e invalida la lista", async () => {
  const video = videoDePrueba("error");
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [video] })
    .mockResolvedValue({ items: [{ ...video, estado: "en_cola", intentos: 0, error_motivo: null }] });
  vi.mocked(api.reprocesarVideo).mockResolvedValue({ ...video, estado: "en_cola", intentos: 0, error_motivo: null });
  renderizar(true);

  await pulsarReprocesar(video);
  expect(await screen.findByText(`El video ${video.archivo} volvió a la cola.`)).toBeVisible();
  expect(await screen.findByText("En cola")).toBeVisible();
  expect(api.listarVideos).toHaveBeenCalledTimes(2);
});

it("si el trabajador lo tomó antes (409), avisa y actualiza la lista", async () => {
  const video = videoDePrueba("reintentando");
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [video] })
    .mockResolvedValue({ items: [{ ...video, estado: "procesando" }] });
  vi.mocked(api.reprocesarVideo).mockRejectedValue(new api.ApiError("conflicto", 409));
  renderizar(true);

  await pulsarReprocesar(video);
  expect(await screen.findByText(`El video ${video.archivo} ya se está procesando.`)).toBeVisible();
  expect(await screen.findByText("Procesando")).toBeVisible();
  expect(api.listarVideos).toHaveBeenCalledTimes(2);
});

it("si el reproceso falla con un 500, lo dice con el nombre del archivo y no recarga la lista", async () => {
  const video = videoDePrueba("error");
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [video] });
  vi.mocked(api.reprocesarVideo).mockRejectedValue(new api.ApiError("fallo", 500));
  renderizar(true);

  await pulsarReprocesar(video);
  expect(await screen.findByText(`No fue posible reprocesar ${video.archivo}. Intenta nuevamente.`)).toBeVisible();
  expect(api.listarVideos).toHaveBeenCalledTimes(1);
});

it("deshabilita el botón mientras el reproceso está pendiente", async () => {
  const video = videoDePrueba("listo");
  let resolver!: (resultado: Video) => void;
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [video] });
  vi.mocked(api.reprocesarVideo).mockImplementation(() => new Promise((resolve) => { resolver = resolve; }));
  renderizar(true);

  await pulsarReprocesar(video);
  const boton = screen.getByRole("button", { name: `Reprocesar ${video.archivo}` });
  expect(boton).toBeDisabled();
  fireEvent.click(boton);
  expect(api.reprocesarVideo).toHaveBeenCalledTimes(1);

  resolver(video);
  await waitFor(() => expect(boton).not.toBeDisabled());
});

it.each([
  ["en_cola", false],
  ["procesando", false],
  ["reintentando", true],
  ["listo", true],
  ["error", true],
] as const)("en %s ofrece reprocesar: %s", async (estado, permiteReproceso) => {
  const video = videoDePrueba(estado);
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [video] });
  renderizar(true);

  const tabla = await screen.findByRole("table", { name: "Cola de videos" });
  const boton = screen.queryByRole("button", { name: `Reprocesar ${video.archivo}` });
  expect(boton !== null).toBe(permiteReproceso);
  const [cabecera, fila] = within(tabla).getAllByRole("row");
  expect(fila.querySelectorAll("th, td")).toHaveLength(cabecera.querySelectorAll("th, td").length);
  expect(within(cabecera).getByText("Acciones")).toBeInTheDocument();
});

it("sin el permiso editar_reglas no hay columna Acciones ni botón Reprocesar", async () => {
  const video = videoDePrueba("listo");
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [video] });
  renderizar(false);

  const tabla = await screen.findByRole("table", { name: "Cola de videos" });
  expect(within(tabla).queryByText("Acciones")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: `Reprocesar ${video.archivo}` })).not.toBeInTheDocument();
});

it("el mensaje vive en una región status siempre montada y se limpia al reprocesar de nuevo", async () => {
  const video = videoDePrueba("listo");
  let resolver!: (resultado: Video) => void;
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [video] });
  vi.mocked(api.reprocesarVideo)
    .mockResolvedValueOnce(video)
    .mockImplementation(() => new Promise((resolve) => { resolver = resolve; }));
  renderizar(true);

  await screen.findByRole("table", { name: "Cola de videos" });
  const region = document.querySelector(".video-message");
  expect(region).toHaveAttribute("role", "status");
  expect(region).toBeEmptyDOMElement();

  await pulsarReprocesar(video);
  const recalculo = `Las reglas de ${video.archivo} se recalcularon sin usar la GPU.`;
  await waitFor(() => expect(region).toHaveTextContent(recalculo));
  await waitFor(() => expect(screen.getByRole("button", { name: `Reprocesar ${video.archivo}` })).not.toBeDisabled());

  fireEvent.click(screen.getByRole("button", { name: `Reprocesar ${video.archivo}` }));
  await waitFor(() => expect(region).toBeEmptyDOMElement());
  resolver(video);
  await waitFor(() => expect(region).toHaveTextContent(recalculo));
});

it.each([401, 403])("si el reproceso responde %i, dice que falta permiso y no recarga la lista", async (status) => {
  const video = videoDePrueba("error");
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [video] });
  vi.mocked(api.reprocesarVideo).mockRejectedValue(new api.ApiError("sin permiso", status));
  renderizar(true);

  await pulsarReprocesar(video);
  expect(await screen.findByText("No tienes permiso para reprocesar videos.")).toBeVisible();
  expect(api.listarVideos).toHaveBeenCalledTimes(1);
});

it("si el video ya no existe (404), lo dice y actualiza la lista", async () => {
  const video = videoDePrueba("error");
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [video] })
    .mockResolvedValue({ items: [] });
  vi.mocked(api.reprocesarVideo).mockRejectedValue(new api.ApiError("no encontrado", 404));
  renderizar(true);

  await pulsarReprocesar(video);
  expect(await screen.findByText(`El video ${video.archivo} ya no existe.`)).toBeVisible();
  expect(await screen.findByText("No hay videos en la cola.")).toBeVisible();
});

it("sin acción posible, la celda Acciones muestra un guion", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [videoDePrueba("en_cola")] });
  renderizar(true);

  const tabla = await screen.findByRole("table", { name: "Cola de videos" });
  const [, fila] = within(tabla).getAllByRole("row");
  const celdas = fila.querySelectorAll("td");
  expect(celdas[celdas.length - 1]).toHaveTextContent("—");
});

// --- Avance de un video procesando -------------------------------------------------------------

function videoProcesando(segundos: number): Video {
  return {
    ...videoDePrueba("procesando"),
    avance: {
      fase: "analizando",
      segundos,
      total_segundos: 300,
      velocidad: 0.8,
      ultimo: { persona: 3, casco: 2, chaleco: 1 },
      actualizado: "2026-10-08T10:00:00Z",
    },
  };
}

it("la fila procesando muestra barra y KPI del cuadro actual; las demás filas no", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({
    items: [
      videoProcesando(150),
      { ...videoDePrueba("listo"), id: 23, archivo: "otro.mp4", avance: null },
      { ...videoDePrueba("en_cola"), id: 24, archivo: "cola.mp4" },
    ],
  });
  renderizar();

  const tabla = await screen.findByRole("table", { name: "Cola de videos" });
  const filas = within(tabla).getAllByRole("row");
  const procesando = filas.find((fila) => within(fila).queryByText("Procesando")) as HTMLElement;
  expect(within(procesando).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "150");
  expect(within(procesando).getByText("2:30 de 5:00 (50 %)")).toBeVisible();
  expect(within(procesando).getByText("En el cuadro actual: 3 personas, 2 cascos, 1 chaleco.")).toBeVisible();
  expect(within(tabla).getAllByRole("progressbar")).toHaveLength(1);
});

it("un video procesando sin avance publicado dice «Procesando…» y no dibuja barra", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [{ ...videoDePrueba("procesando"), avance: null }] });
  renderizar();

  expect(await screen.findByText("Procesando…")).toBeVisible();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});

it("un avance viejo en un video que ya no está procesando no se dibuja", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [{ ...videoProcesando(150), estado: "listo" }] });
  renderizar();

  await screen.findByText("Listo");
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  expect(screen.queryByText(/En el cuadro actual/)).not.toBeInTheDocument();
});

// Los milisegundos van escritos en cada test: comparar contra la constante de producción no
// detectaría que alguien la cambiara.
it("con un video procesando vuelve a pedir la cola cada 3000 ms, ni antes ni después", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [videoProcesando(150)] });
  renderizar();

  await screen.findByText("2:30 de 5:00 (50 %)");
  const inicial = vi.mocked(api.listarVideos).mock.calls.length;
  await vi.advanceTimersByTimeAsync(2500);
  expect(api.listarVideos).toHaveBeenCalledTimes(inicial);
  await vi.advanceTimersByTimeAsync(1000);
  expect(api.listarVideos).toHaveBeenCalledTimes(inicial + 1);
  await vi.advanceTimersByTimeAsync(3000);
  expect(api.listarVideos).toHaveBeenCalledTimes(inicial + 2);
});

it("la barra avanza cuando llega un avance nuevo", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [videoProcesando(150)] })
    .mockResolvedValue({ items: [videoProcesando(210)] });
  renderizar();

  await screen.findByText("2:30 de 5:00 (50 %)");
  await vi.advanceTimersByTimeAsync(3500);
  expect(await screen.findByText("3:30 de 5:00 (70 %)")).toBeVisible();
  expect(screen.queryByText("2:30 de 5:00 (50 %)")).not.toBeInTheDocument();
});

it.each(["en_cola", "reintentando"] as const)("con un video %s sigue pidiendo la cola cada 10000 ms", async (estado) => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [videoDePrueba(estado)] });
  renderizar();

  await screen.findByRole("table", { name: "Cola de videos" });
  const inicial = vi.mocked(api.listarVideos).mock.calls.length;
  await vi.advanceTimersByTimeAsync(9000);
  expect(api.listarVideos).toHaveBeenCalledTimes(inicial);
  await vi.advanceTimersByTimeAsync(2000);
  expect(api.listarVideos).toHaveBeenCalledTimes(inicial + 1);
});

it("al pasar de procesando a listo quita la barra y deja de pedir cada 3 s", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [videoProcesando(150)] })
    .mockResolvedValue({ items: [{ ...videoDePrueba("listo"), avance: null }] });
  renderizar();

  await screen.findByRole("progressbar");
  await vi.advanceTimersByTimeAsync(3500);
  expect(await screen.findByText("Listo")).toBeVisible();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  expect(screen.queryByText(/En el cuadro actual/)).not.toBeInTheDocument();
  const llamadas = vi.mocked(api.listarVideos).mock.calls.length;
  await vi.advanceTimersByTimeAsync(30_000);
  expect(api.listarVideos).toHaveBeenCalledTimes(llamadas);
});

it("al pasar de procesando a reintentando baja al ritmo de 10 s y quita la barra", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [videoProcesando(240)] })
    .mockResolvedValue({ items: [{ ...videoDePrueba("reintentando"), avance: null }] });
  renderizar();

  await screen.findByRole("progressbar");
  await vi.advanceTimersByTimeAsync(3500);
  expect(await screen.findByText("Reintentando")).toBeVisible();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  const llamadas = vi.mocked(api.listarVideos).mock.calls.length;
  await vi.advanceTimersByTimeAsync(7000);
  expect(api.listarVideos).toHaveBeenCalledTimes(llamadas);
  await vi.advanceTimersByTimeAsync(4000);
  expect(api.listarVideos).toHaveBeenCalledTimes(llamadas + 1);
});

// --- Vista del modelo (ventana en vivo) -----------------------------------------------------------

function renderizarVivo({ editar = false, evidencia = false }: { editar?: boolean; evidencia?: boolean }) {
  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [] });
  vi.mocked(api.obtenerCuadrosVivo).mockRejectedValue(new api.ApiError("sin cuadro", 404));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <VideosPage puedeEditarReglas={editar} puedeVerEvidencia={evidencia} />
    </QueryClientProvider>,
  );
}

it("con ver_evidencia, un video procesando muestra la vista del modelo debajo de su fila, a todo el ancho", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [videoProcesando(150)] });
  renderizarVivo({ evidencia: true });

  const vista = await screen.findByRole("region", { name: "Vista del modelo de CAM-03_2026-10-02_08-00.mp4" });
  expect(await within(vista).findByText("Esperando el primer cuadro…")).toBeVisible();
  expect(api.obtenerCuadrosVivo).toHaveBeenCalledWith(22, 0, expect.any(AbortSignal));
  const fila = vista.closest("tr") as HTMLTableRowElement;
  expect(fila.previousElementSibling).toHaveTextContent("Procesando");
  expect(fila.previousElementSibling).toHaveTextContent("2:30 de 5:00 (50 %)");
  expect(fila.querySelector("td")).toHaveAttribute("colspan", "5");
});

it("con editar_reglas la fila de la vista ocupa seis columnas", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [videoProcesando(150)] });
  renderizarVivo({ evidencia: true, editar: true });

  const vista = await screen.findByRole("region", { name: /Vista del modelo de/ });
  expect(vista.closest("td")).toHaveAttribute("colspan", "6");
});

it("sin ver_evidencia no aparece la vista del modelo y no se pide ningún cuadro", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [videoProcesando(150)] });
  renderizarVivo({ evidencia: false });

  await screen.findByText("2:30 de 5:00 (50 %)");
  expect(screen.queryByRole("region", { name: /Vista del modelo/ })).not.toBeInTheDocument();
  expect(api.obtenerCuadrosVivo).not.toHaveBeenCalled();
});

it("el administrador (editar_reglas sin ver_evidencia) no ve la vista del modelo", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [videoProcesando(150)] });
  renderizarVivo({ editar: true, evidencia: false });

  await screen.findByText("2:30 de 5:00 (50 %)");
  expect(screen.queryByRole("region", { name: /Vista del modelo/ })).not.toBeInTheDocument();
  expect(api.obtenerCuadrosVivo).not.toHaveBeenCalled();
});

it.each(["listo", "en_cola", "reintentando", "error"] as const)("con un video %s no aparece la vista del modelo ni se pide cuadro", async (estado) => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [videoDePrueba(estado)] });
  renderizarVivo({ evidencia: true });

  await screen.findByRole("table", { name: "Cola de videos" });
  expect(screen.queryByRole("region", { name: /Vista del modelo/ })).not.toBeInTheDocument();
  expect(api.obtenerCuadrosVivo).not.toHaveBeenCalled();
});

it("al pasar de procesando a listo la vista del modelo desaparece y se deja de pedir", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [videoProcesando(150)] })
    .mockResolvedValue({ items: [{ ...videoDePrueba("listo"), avance: null }] });
  renderizarVivo({ evidencia: true });

  await screen.findByRole("region", { name: /Vista del modelo/ });
  await vi.advanceTimersByTimeAsync(3500);
  expect(await screen.findByText("Listo")).toBeVisible();
  expect(screen.queryByRole("region", { name: /Vista del modelo/ })).not.toBeInTheDocument();
  const llamadas = vi.mocked(api.obtenerCuadrosVivo).mock.calls.length;
  await vi.advanceTimersByTimeAsync(10_000);
  expect(api.obtenerCuadrosVivo).toHaveBeenCalledTimes(llamadas);
});
