import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { Video } from "../api/types";
import * as api from "../api/client";
import { VideosPage } from "./VideosPage";

vi.mock("../api/client", () => ({
    ApiError: class extends Error {
        constructor(message: string, public readonly status: number) { super(message); }
    },
    listarVideos: vi.fn(),
}));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

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
    expect(within(fila).getByRole("status", { name: "Estado: Error" })).toHaveClass("video-status--error");
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

    expect(await screen.findByRole("status", { name: `Estado: ${nombre}` })).toHaveClass(`video-status--${clase}`);
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
