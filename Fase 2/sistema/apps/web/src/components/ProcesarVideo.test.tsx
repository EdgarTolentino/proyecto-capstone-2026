import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../api/client";
import type { Catalogos, Pedido, Video } from "../api/types";
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
}));

afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers(); });

const MB = 1024 * 1024;
const CATALOGOS: Catalogos = { fuentes: [{ id: 3, nombre: "CAM-03" }, { id: 4, nombre: "CAM-04" }] };
const ENTRADA = {
  items: [
    { archivo: "CAM-03_08-00.mp4", bytes: 700 * MB, modificado: "2026-10-02T08:00:00Z", posible_duplicado: false },
    { archivo: "CAM-03_09-00.mp4", bytes: 2 * 1024 * MB, modificado: "2026-10-02T09:00:00Z", posible_duplicado: true },
  ],
};

function pedido(estado: Pedido["estado"], extra: Partial<Pedido> = {}): Pedido {
  return {
    id: 7,
    archivo: "CAM-03_08-00.mp4",
    fuente: { id: 3, nombre: "CAM-03" },
    estado,
    motivo: null,
    video_id: null,
    creado_en: "2026-10-08T10:00:00Z",
    ...extra,
  };
}

function video(id: number, archivo: string): Video {
  return { id, archivo, capture_ts_inicio: "2026-10-02T08:00:00Z", estado: "en_cola", intentos: 0 };
}

function renderizar(
  { puede = true, catalogos = CATALOGOS, catalogosError = false }: { puede?: boolean; catalogos?: Catalogos | null; catalogosError?: boolean } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <VideosPage puedeEditarReglas={puede} catalogos={catalogos ?? undefined} catalogosError={catalogosError} />
    </QueryClientProvider>,
  );
  return client;
}

function preparar(entrada: unknown = ENTRADA) {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [] });
  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [] });
  vi.mocked(api.listarEntradaVideos).mockResolvedValue(entrada as Awaited<ReturnType<typeof api.listarEntradaVideos>>);
}

async function abrir() {
  const boton = await screen.findByRole("button", { name: "Procesar video" });
  boton.focus();
  fireEvent.click(boton);
  return { boton, dialogo: await screen.findByRole("dialog", { name: "Procesar video" }) };
}

async function elegir(dialogo: HTMLElement, archivo = "CAM-03_08-00.mp4", camara = "3") {
  fireEvent.click(await within(dialogo).findByRole("radio", { name: new RegExp(archivo) }));
  fireEvent.change(within(dialogo).getByRole("combobox", { name: "Cámara" }), { target: { value: camara } });
}

// --- permiso y apertura ----------------------------------------------------------------------

it("sin el permiso editar_reglas no hay botón, ni panel, ni se piden los pedidos", async () => {
  preparar();
  renderizar({ puede: false });

  await screen.findByText("No hay videos en la cola.");
  expect(screen.queryByRole("button", { name: "Procesar video" })).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Pedidos de procesamiento" })).not.toBeInTheDocument();
  expect(api.listarPedidos).not.toHaveBeenCalled();
});

it("abre el diálogo con nombre accesible, foco dentro, archivos con tamaño legible y aviso de duplicado", async () => {
  preparar();
  renderizar();
  const { dialogo } = await abrir();

  expect(dialogo).toHaveAttribute("aria-modal", "true");
  expect(dialogo.contains(document.activeElement)).toBe(true);
  const primero = await within(dialogo).findByRole("radio", { name: /CAM-03_08-00\.mp4/ });
  expect(primero).toHaveAccessibleName(/700,0 MB/);
  expect(primero).not.toHaveAccessibleName(/duplicado/i);
  expect(within(dialogo).getByRole("radio", { name: /CAM-03_09-00\.mp4.*2,0 GB.*Posible duplicado/ })).toBeVisible();
  expect(within(dialogo).getByRole("option", { name: "CAM-04" })).toBeInTheDocument();
});

it("Escape cierra el diálogo y devuelve el foco al botón que lo abrió", async () => {
  preparar();
  renderizar();
  const { boton } = await abrir();

  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(boton).toHaveFocus();
});

it("Tab queda dentro del diálogo en los dos sentidos", async () => {
  preparar();
  renderizar();
  const { dialogo } = await abrir();
  await within(dialogo).findByRole("radio", { name: /CAM-03_08-00/ });
  const cerrar = within(dialogo).getByRole("button", { name: "Cerrar" });
  const cancelar = within(dialogo).getByRole("button", { name: "Cancelar" });

  cancelar.focus(); // último control habilitado: «Procesar» está deshabilitado sin selección
  fireEvent.keyDown(cancelar, { key: "Tab" });
  expect(cerrar).toHaveFocus();
  fireEvent.keyDown(cerrar, { key: "Tab", shiftKey: true });
  expect(cancelar).toHaveFocus();
});

// --- lista de entrada ------------------------------------------------------------------------

it("con la carpeta vacía lo dice y no deja procesar", async () => {
  preparar({ items: [] });
  renderizar();
  const { dialogo } = await abrir();

  expect(await within(dialogo).findByText("No hay archivos en la carpeta de entrada.")).toBeVisible();
  expect(within(dialogo).getByRole("button", { name: "Procesar" })).toBeDisabled();
});

it.each([
  [new Error("x"), "No fue posible leer la carpeta de entrada."],
  [{ status: 409, codigo: "entrada_no_configurada" }, "El servidor no tiene configurada la carpeta de entrada."],
  [{ status: 403, codigo: "sin_permiso" }, "No tienes permiso para procesar videos."],
] as const)("si la lista de entrada falla (%j) lo dice en el diálogo y deja reintentar", async (falla, texto) => {
  preparar();
  const error = falla instanceof Error ? new api.ApiError("x", 500) : new api.ApiError("x", falla.status, falla.codigo);
  vi.mocked(api.listarEntradaVideos).mockRejectedValueOnce(error);
  renderizar();
  const { dialogo } = await abrir();

  expect(await within(dialogo).findByRole("alert")).toHaveTextContent(texto);
  expect(within(dialogo).queryByText("No hay archivos en la carpeta de entrada.")).not.toBeInTheDocument();
  fireEvent.click(within(dialogo).getByRole("button", { name: "Reintentar" }));
  expect(await within(dialogo).findByRole("radio", { name: /CAM-03_08-00/ })).toBeVisible();
  expect(within(dialogo).queryByRole("alert")).not.toBeInTheDocument();
});

it("la carpeta se lee de nuevo cada vez que se abre el diálogo", async () => {
  preparar();
  renderizar();
  const { dialogo } = await abrir();
  await within(dialogo).findByRole("radio", { name: /CAM-03_08-00/ });
  fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  await abrir();
  await waitFor(() => expect(api.listarEntradaVideos).toHaveBeenCalledTimes(2));
});

// --- cámaras ---------------------------------------------------------------------------------

it("si los catálogos fallan lo dice dentro del diálogo y no deja procesar", async () => {
  preparar();
  renderizar({ catalogos: null, catalogosError: true });
  const { dialogo } = await abrir();

  await within(dialogo).findByRole("radio", { name: /CAM-03_08-00/ });
  fireEvent.click(within(dialogo).getByRole("radio", { name: /CAM-03_08-00/ }));
  expect(within(dialogo).getByRole("alert")).toHaveTextContent("No fue posible cargar las cámaras");
  expect(within(dialogo).getByRole("combobox", { name: "Cámara" })).toBeDisabled();
  expect(within(dialogo).getByRole("button", { name: "Procesar" })).toBeDisabled();
});

it("mientras los catálogos cargan, el selector lo indica y está deshabilitado", async () => {
  preparar();
  renderizar({ catalogos: null });
  const { dialogo } = await abrir();

  const selector = within(dialogo).getByRole("combobox", { name: "Cámara" });
  expect(selector).toBeDisabled();
  expect(within(dialogo).getByRole("option", { name: "Cargando cámaras…" })).toBeInTheDocument();
  expect(within(dialogo).queryByRole("alert")).not.toBeInTheDocument();
});

it("sin cámaras configuradas lo dice y no deja procesar", async () => {
  preparar();
  renderizar({ catalogos: { fuentes: [] } });
  const { dialogo } = await abrir();

  await within(dialogo).findByRole("radio", { name: /CAM-03_08-00/ });
  expect(within(dialogo).getByRole("alert")).toHaveTextContent("No hay cámaras configuradas.");
  expect(within(dialogo).getByRole("button", { name: "Procesar" })).toBeDisabled();
});

// --- enviar ----------------------------------------------------------------------------------

it("«Procesar» exige archivo y cámara", async () => {
  preparar();
  renderizar();
  const { dialogo } = await abrir();
  const procesar = within(dialogo).getByRole("button", { name: "Procesar" });

  expect(procesar).toBeDisabled();
  fireEvent.click(await within(dialogo).findByRole("radio", { name: /CAM-03_08-00/ }));
  expect(procesar).toBeDisabled();
  fireEvent.change(within(dialogo).getByRole("combobox", { name: "Cámara" }), { target: { value: "3" } });
  expect(procesar).toBeEnabled();
  fireEvent.change(within(dialogo).getByRole("combobox", { name: "Cámara" }), { target: { value: "" } });
  expect(procesar).toBeDisabled();
});

it("elegir solo la cámara no habilita «Procesar»", async () => {
  preparar();
  renderizar();
  const { dialogo } = await abrir();
  await within(dialogo).findByRole("radio", { name: /CAM-03_08-00/ });

  fireEvent.change(within(dialogo).getByRole("combobox", { name: "Cámara" }), { target: { value: "3" } });

  expect(within(dialogo).getByRole("button", { name: "Procesar" })).toBeDisabled();
});

it("el anuncio de un pedido anterior se limpia al enviar otro", async () => {
  preparar();
  let resolver!: (p: Pedido) => void;
  vi.mocked(api.pedirIngesta)
    .mockResolvedValueOnce(pedido("pendiente"))
    .mockImplementation(() => new Promise((resolve) => { resolver = resolve; }));
  renderizar();
  const primero = await abrir();
  await elegir(primero.dialogo);
  fireEvent.click(within(primero.dialogo).getByRole("button", { name: "Procesar" }));
  const region = document.querySelector(".video-message");
  await waitFor(() => expect(region).toHaveTextContent(/quedó pedido/));

  const segundo = await abrir();
  await elegir(segundo.dialogo, "CAM-03_09-00.mp4");
  fireEvent.click(within(segundo.dialogo).getByRole("button", { name: "Procesar" }));

  await waitFor(() => expect(region).toBeEmptyDOMElement());
  resolver(pedido("pendiente", { archivo: "CAM-03_09-00.mp4" }));
  await waitFor(() => expect(region).toHaveTextContent(/CAM-03_09-00\.mp4 quedó pedido/));
});

it("un archivo con posible duplicado se puede pedir y avisa que lo decide el contenido", async () => {
  preparar();
  renderizar();
  const { dialogo } = await abrir();

  await elegir(dialogo, "CAM-03_09-00.mp4");

  expect(within(dialogo).getByText(/El servidor lo decide por su contenido/)).toBeVisible();
  expect(within(dialogo).getByRole("button", { name: "Procesar" })).toBeEnabled();
});

it("al pedir, manda el archivo y la cámara elegidos, cierra, anuncia, muestra el pedido y devuelve el foco", async () => {
  preparar();
  vi.mocked(api.pedirIngesta).mockResolvedValue(pedido("pendiente"));
  renderizar();
  const { boton, dialogo } = await abrir();
  await elegir(dialogo, "CAM-03_08-00.mp4", "4");
  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [pedido("pendiente", { fuente: { id: 4, nombre: "CAM-04" } })] });

  fireEvent.click(within(dialogo).getByRole("button", { name: "Procesar" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(api.pedirIngesta).toHaveBeenCalledWith({ archivo: "CAM-03_08-00.mp4", fuente_id: 4 });
  expect(await screen.findByText(/El archivo CAM-03_08-00\.mp4 quedó pedido/)).toBeVisible();
  const panel = await screen.findByRole("region", { name: "Pedidos de procesamiento" });
  expect(within(panel).getByText("Pedido pendiente")).toBeVisible();
  expect(within(panel).getByText("CAM-04")).toBeVisible();
  expect(boton).toHaveFocus();
});

it("con el pedido en vuelo el botón queda deshabilitado y un segundo clic no envía otro", async () => {
  preparar();
  let resolver!: (p: Pedido) => void;
  vi.mocked(api.pedirIngesta).mockImplementation(() => new Promise((resolve) => { resolver = resolve; }));
  renderizar();
  const { dialogo } = await abrir();
  await elegir(dialogo);

  const procesar = within(dialogo).getByRole("button", { name: "Procesar" });
  fireEvent.click(procesar);
  const enviando = await within(dialogo).findByRole("button", { name: "Enviando…" });
  expect(enviando).toBeDisabled();
  fireEvent.click(enviando);
  expect(api.pedirIngesta).toHaveBeenCalledTimes(1);

  resolver(pedido("pendiente"));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

async function pedirYAnunciar() {
  preparar();
  vi.mocked(api.pedirIngesta).mockResolvedValue(pedido("pendiente"));
  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [pedido("pendiente")] });
  renderizar();
  const { dialogo } = await abrir();
  await elegir(dialogo);
  fireEvent.click(within(dialogo).getByRole("button", { name: "Procesar" }));
  await screen.findByText(/El archivo CAM-03_08-00\.mp4 quedó pedido/);
}

it.each(["registrado", "rechazado"] as const)("el aviso «quedó pedido» se va cuando el pedido pasa a %s", async (estado) => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  await pedirYAnunciar();

  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [pedido(estado)] });
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS + 500);

  await waitFor(() => expect(screen.queryByText(/quedó pedido/)).not.toBeInTheDocument());
  expect(document.querySelector(".video-message")).toBeEmptyDOMElement();
});

it("el aviso «quedó pedido» se mantiene mientras el pedido siga pendiente o tomado", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  await pedirYAnunciar();

  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [pedido("tomado")] });
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS + 500);

  expect(await screen.findByText("Registrando")).toBeVisible();
  expect(screen.getByText(/El archivo CAM-03_08-00\.mp4 quedó pedido/)).toBeVisible();
});

it("al registrarse el pedido no se borra un aviso distinto que ya lo reemplazó", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  preparar();
  vi.mocked(api.listarVideos).mockResolvedValue({
    items: [{ ...video(22, "otro.mp4"), estado: "error", intentos: 3, error_motivo: "fallo" }],
  });
  vi.mocked(api.pedirIngesta).mockResolvedValue(pedido("pendiente"));
  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [pedido("pendiente")] });
  vi.mocked(api.reprocesarVideo).mockResolvedValue({ ...video(22, "otro.mp4"), estado: "en_cola" });
  renderizar();
  const { dialogo } = await abrir();
  await elegir(dialogo);
  fireEvent.click(within(dialogo).getByRole("button", { name: "Procesar" }));
  await screen.findByText(/quedó pedido/);
  fireEvent.click(await screen.findByRole("button", { name: "Reprocesar otro.mp4" }));
  await screen.findByText("El video otro.mp4 volvió a la cola.");

  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [pedido("registrado")] });
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS + 500);
  await screen.findByText("Registrado");

  expect(screen.getByText("El video otro.mp4 volvió a la cola.")).toBeVisible();
});

it("si se cierra el diálogo con el pedido en vuelo, el éxito igual se anuncia en la página", async () => {
  preparar();
  let resolver!: (p: Pedido) => void;
  vi.mocked(api.pedirIngesta).mockImplementation(() => new Promise((resolve) => { resolver = resolve; }));
  renderizar();
  const { dialogo } = await abrir();
  await elegir(dialogo);
  fireEvent.click(within(dialogo).getByRole("button", { name: "Procesar" }));
  await within(dialogo).findByRole("button", { name: "Enviando…" });

  fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [pedido("pendiente")] });
  resolver(pedido("pendiente"));

  expect(await screen.findByText(/El archivo CAM-03_08-00\.mp4 quedó pedido/)).toBeVisible();
  expect(await screen.findByRole("region", { name: "Pedidos de procesamiento" })).toBeVisible();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("si se cierra el diálogo con el pedido en vuelo, el fallo se anuncia en la página y no reabre nada", async () => {
  preparar();
  let rechazar!: (e: unknown) => void;
  vi.mocked(api.pedirIngesta).mockImplementation(() => new Promise((_resolve, reject) => { rechazar = reject; }));
  renderizar();
  const { dialogo } = await abrir();
  await elegir(dialogo);
  fireEvent.click(within(dialogo).getByRole("button", { name: "Procesar" }));
  await within(dialogo).findByRole("button", { name: "Enviando…" });
  fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  rechazar(new api.ApiError("x", 409, "pedido_existente"));

  const region = document.querySelector(".video-message");
  await waitFor(() => expect(region).toHaveTextContent("El archivo CAM-03_08-00.mp4 ya tiene un pedido en curso."));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it.each([
  [409, "fuente_inactiva", "La cámara elegida está inactiva."],
  [409, "pedido_existente", "El archivo CAM-03_08-00.mp4 ya tiene un pedido en curso."],
  [409, "entrada_no_configurada", "El servidor no tiene configurada la carpeta de entrada."],
  [404, "archivo_no_encontrado", "El archivo CAM-03_08-00.mp4 ya no está en la carpeta de entrada."],
  [404, "fuente_no_encontrada", "La cámara elegida ya no existe."],
  [422, "peticion_invalida", "El nombre del archivo no es válido."],
  [403, "sin_permiso", "No tienes permiso para procesar videos."],
  [500, undefined, "No fue posible pedir el procesamiento de CAM-03_08-00.mp4. Intenta nuevamente."],
  [409, "codigo_que_no_existe", "No fue posible pedir el procesamiento de CAM-03_08-00.mp4. Intenta nuevamente."],
] as const)("el error %i %s se explica dentro del diálogo, que sigue abierto y se puede reintentar", async (status, codigo, texto) => {
  preparar();
  vi.mocked(api.pedirIngesta).mockRejectedValue(new api.ApiError("texto crudo del servidor", status, codigo));
  renderizar();
  const { dialogo } = await abrir();
  await elegir(dialogo);

  fireEvent.click(within(dialogo).getByRole("button", { name: "Procesar" }));

  expect(await within(dialogo).findByRole("alert")).toHaveTextContent(texto);
  expect(screen.queryByText("texto crudo del servidor")).not.toBeInTheDocument();
  expect(within(dialogo).getByRole("button", { name: "Procesar" })).toBeEnabled();
  expect(document.querySelector(".video-message")).toBeEmptyDOMElement();
});

it.each(["archivo_no_encontrado", "pedido_existente"])("el error %s vuelve a leer la carpeta y los pedidos", async (codigo) => {
  preparar();
  vi.mocked(api.pedirIngesta).mockRejectedValue(new api.ApiError("x", codigo === "pedido_existente" ? 409 : 404, codigo));
  renderizar();
  const { dialogo } = await abrir();
  await elegir(dialogo);
  const entradas = vi.mocked(api.listarEntradaVideos).mock.calls.length;
  const pedidos = vi.mocked(api.listarPedidos).mock.calls.length;

  fireEvent.click(within(dialogo).getByRole("button", { name: "Procesar" }));

  await within(dialogo).findByRole("alert");
  await waitFor(() => expect(api.listarEntradaVideos).toHaveBeenCalledTimes(entradas + 1));
  await waitFor(() => expect(api.listarPedidos).toHaveBeenCalledTimes(pedidos + 1));
});

it("un error anterior no queda en el diálogo al abrirlo de nuevo", async () => {
  preparar();
  vi.mocked(api.pedirIngesta).mockRejectedValue(new api.ApiError("x", 500));
  renderizar();
  const { dialogo } = await abrir();
  await elegir(dialogo);
  fireEvent.click(within(dialogo).getByRole("button", { name: "Procesar" }));
  await within(dialogo).findByRole("alert");
  fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  const { dialogo: otro } = await abrir();

  await within(otro).findByRole("radio", { name: /CAM-03_08-00/ });
  expect(within(otro).queryByRole("alert")).not.toBeInTheDocument();
});

// --- panel de pedidos ------------------------------------------------------------------------

it("al recargar con un pedido pendiente lo muestra encima de la tabla y sigue vigilándolo", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [{ ...video(1, "otro.mp4"), estado: "listo" }] });
  vi.mocked(api.listarPedidos)
    .mockResolvedValueOnce({ items: [pedido("pendiente")] })
    .mockResolvedValue({ items: [pedido("tomado")] });
  renderizar();

  const panel = await screen.findByRole("region", { name: "Pedidos de procesamiento" });
  const tabla = await screen.findByRole("table", { name: "Cola de videos" });
  expect(panel.compareDocumentPosition(tabla) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(within(panel).getByText("Pedido pendiente")).toBeVisible();

  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS);
  expect(await within(panel).findByText("Registrando")).toBeVisible();
  expect(within(panel).queryByText("Pedido pendiente")).not.toBeInTheDocument();
});

it("cuando el pedido pasa a registrado, la tabla de videos se pone al día y el panel deja de refrescar", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [] })
    .mockResolvedValue({ items: [{ ...video(9, "CAM-03_08-00.mp4"), estado: "listo" }] });
  vi.mocked(api.listarPedidos)
    .mockResolvedValueOnce({ items: [pedido("pendiente")] })
    .mockResolvedValue({ items: [pedido("registrado", { video_id: 9 })] });
  renderizar();
  await screen.findByText("Pedido pendiente");
  expect(await screen.findByText("No hay videos en la cola.")).toBeVisible();

  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS);

  const tabla = await screen.findByRole("table", { name: "Cola de videos" });
  expect(within(tabla).getByText("CAM-03_08-00.mp4")).toBeVisible();
  expect(screen.getByText("Registrado")).toBeVisible();
  const llamadas = vi.mocked(api.listarPedidos).mock.calls.length;
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS * 3);
  expect(api.listarPedidos).toHaveBeenCalledTimes(llamadas);
});

it("un pedido que ya llega registrado tras pedirlo también actualiza la tabla", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [] })
    .mockResolvedValue({ items: [{ ...video(9, "nuevo.mp4"), estado: "listo" }] });
  vi.mocked(api.listarPedidos)
    .mockResolvedValueOnce({ items: [] })
    .mockResolvedValue({ items: [pedido("registrado", { id: 8, archivo: "nuevo.mp4", video_id: 9 })] });
  const client = renderizar();
  await screen.findByText("No hay videos en la cola.");

  await client.invalidateQueries({ queryKey: ["videos-pedidos"] });

  expect(await screen.findByRole("table", { name: "Cola de videos" })).toBeVisible();
});

it("al cargar la página con pedidos ya registrados no vuelve a pedir la tabla de videos", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [{ ...video(9, "a.mp4"), estado: "listo" }] });
  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [pedido("registrado", { video_id: 9 })] });
  renderizar();

  await screen.findByText("Registrado");
  await screen.findByRole("table", { name: "Cola de videos" });
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(api.listarVideos).toHaveBeenCalledTimes(1);
});

it("un pedido rechazado muestra su motivo y no mantiene el refresco", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [] });
  vi.mocked(api.listarPedidos).mockResolvedValue({
    items: [pedido("rechazado", { motivo: "Ya registrado como CAM-01." })],
  });
  renderizar();

  const panel = await screen.findByRole("region", { name: "Pedidos de procesamiento" });
  expect(within(panel).getByText("Rechazado")).toBeVisible();
  expect(within(panel).getByText("Ya registrado como CAM-01.")).toBeVisible();
  const llamadas = vi.mocked(api.listarPedidos).mock.calls.length;
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS * 3);
  expect(api.listarPedidos).toHaveBeenCalledTimes(llamadas);
});

it("un pedido rechazado sin motivo no deja el espacio vacío", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [] });
  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [pedido("rechazado", { motivo: null })] });
  renderizar();

  expect(await screen.findByText("Sin motivo informado.")).toBeVisible();
});

it("si el refresco de los pedidos falla, conserva el panel, avisa y deja de pedir", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [] });
  vi.mocked(api.listarPedidos)
    .mockResolvedValueOnce({ items: [pedido("pendiente")] })
    .mockRejectedValue(new api.ApiError("fallo", 500));
  renderizar();
  await screen.findByText("Pedido pendiente");

  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS);

  expect(await screen.findByText(/No fue posible cargar los pedidos de procesamiento/)).toBeVisible();
  expect(screen.getByText("Pedido pendiente")).toBeVisible();
  const llamadas = vi.mocked(api.listarPedidos).mock.calls.length;
  await vi.advanceTimersByTimeAsync(INTERVALO_REFRESCO_MS * 3);
  expect(api.listarPedidos).toHaveBeenCalledTimes(llamadas);
});

it("si los pedidos no se pueden cargar lo avisa sin tapar la tabla y permite reintentar", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [{ ...video(1, "a.mp4"), estado: "listo" }] });
  vi.mocked(api.listarPedidos).mockRejectedValueOnce(new api.ApiError("x", 500));
  renderizar();

  expect(await screen.findByText(/No fue posible cargar los pedidos de procesamiento/)).toBeVisible();
  expect(screen.getByRole("table", { name: "Cola de videos" })).toBeVisible();
  vi.mocked(api.listarPedidos).mockResolvedValueOnce({ items: [pedido("pendiente")] });
  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(await screen.findByText("Pedido pendiente")).toBeVisible();
  expect(screen.queryByText(/No fue posible cargar los pedidos/)).not.toBeInTheDocument();
});

// --- correcciones de la revisión ---------------------------------------------------------------

it("si la primera respuesta de los pedidos ya trae uno registrado que la tabla no tiene, la tabla se pone al día", async () => {
  vi.mocked(api.listarVideos)
    .mockResolvedValueOnce({ items: [] })
    .mockResolvedValue({ items: [{ ...video(9, "CAM-03_08-00.mp4"), estado: "listo" }] });
  vi.mocked(api.listarPedidos).mockResolvedValue({ items: [pedido("registrado", { video_id: 9 })] });
  renderizar();

  expect(await screen.findByText("Registrado")).toBeVisible();
  const tabla = await screen.findByRole("table", { name: "Cola de videos" });
  expect(within(tabla).getByText("CAM-03_08-00.mp4")).toBeVisible();
  expect(screen.queryByText("No hay videos en la cola.")).not.toBeInTheDocument();
});

it("un pedido registrado que la tabla nunca muestra no hace pedir la tabla una y otra vez", async () => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [] });
  let n = 0;
  vi.mocked(api.listarPedidos).mockImplementation(async () => ({
    items: [pedido("registrado", { video_id: 9, creado_en: `2026-10-08T10:00:0${++n % 10}Z` })],
  }));
  const client = renderizar();
  await screen.findByText("Registrado");
  await screen.findByText("No hay videos en la cola.");

  for (let i = 0; i < 3; i += 1) await client.invalidateQueries({ queryKey: ["videos-pedidos"] });
  await new Promise((resolve) => setTimeout(resolve, 50));

  expect(vi.mocked(api.listarPedidos).mock.calls.length).toBeGreaterThanOrEqual(4);
  expect(vi.mocked(api.listarVideos).mock.calls.length).toBeLessThanOrEqual(2);
});

it("la respuesta de un pedido anterior no cierra ni toca el diálogo de una apertura nueva", async () => {
  preparar();
  let resolver!: (p: Pedido) => void;
  vi.mocked(api.pedirIngesta).mockImplementation(() => new Promise((resolve) => { resolver = resolve; }));
  renderizar();
  const primero = await abrir();
  await elegir(primero.dialogo);
  fireEvent.click(within(primero.dialogo).getByRole("button", { name: "Procesar" }));
  await within(primero.dialogo).findByRole("button", { name: "Enviando…" });
  fireEvent.click(within(primero.dialogo).getByRole("button", { name: "Cancelar" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  const { dialogo } = await abrir();
  await elegir(dialogo, "CAM-03_09-00.mp4", "4");
  resolver(pedido("pendiente"));

  await screen.findByText(/El archivo CAM-03_08-00\.mp4 quedó pedido/);
  expect(screen.getByRole("dialog", { name: "Procesar video" })).toBeVisible();
  expect(within(dialogo).getByRole("radio", { name: /CAM-03_09-00/ })).toBeChecked();
  expect(within(dialogo).getByRole("combobox", { name: "Cámara" })).toHaveValue("4");
});

it("el fallo de un pedido anterior no aparece dentro del diálogo de una apertura nueva", async () => {
  preparar();
  let rechazar!: (e: unknown) => void;
  vi.mocked(api.pedirIngesta).mockImplementation(() => new Promise((_resolve, reject) => { rechazar = reject; }));
  renderizar();
  const primero = await abrir();
  await elegir(primero.dialogo);
  fireEvent.click(within(primero.dialogo).getByRole("button", { name: "Procesar" }));
  await within(primero.dialogo).findByRole("button", { name: "Enviando…" });
  fireEvent.click(within(primero.dialogo).getByRole("button", { name: "Cancelar" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  const { dialogo } = await abrir();
  rechazar(new api.ApiError("x", 409, "pedido_existente"));

  const region = document.querySelector(".video-message");
  await waitFor(() => expect(region).toHaveTextContent("El archivo CAM-03_08-00.mp4 ya tiene un pedido en curso."));
  expect(within(dialogo).queryByRole("alert")).not.toBeInTheDocument();
});

it("Shift+Tab nada más abrir el diálogo no deja escapar el foco", async () => {
  preparar();
  renderizar();
  const { dialogo } = await abrir();
  await within(dialogo).findByRole("radio", { name: /CAM-03_08-00/ });
  expect(document.activeElement).toBe(dialogo);

  const seguiaElEvento = fireEvent.keyDown(document.activeElement as Element, { key: "Tab", shiftKey: true });

  expect(seguiaElEvento).toBe(false); // el diálogo tomó el Tab y evitó el salto del navegador
  expect(dialogo.contains(document.activeElement)).toBe(true);
  expect(document.activeElement).not.toBe(dialogo);
});

it.each([401, 403])("un %d al leer los pedidos dice que no hay permiso y no ofrece reintentar", async (status) => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [{ ...video(1, "a.mp4"), estado: "listo" }] });
  vi.mocked(api.listarPedidos).mockRejectedValue(new api.ApiError("x", status));
  renderizar();

  expect(await screen.findByText("No tienes permiso para ver los pedidos de procesamiento.")).toBeVisible();
  expect(screen.queryByText(/No fue posible cargar los pedidos/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Cola de videos" })).toBeVisible();
});
