import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../api/client";
import { VistaProcesada } from "./VistaProcesada";

vi.mock("../api/client", () => ({
  ApiError: class extends Error {
    constructor(message: string, public readonly status: number) { super(message); }
  },
  listarVideos: vi.fn(),
}));
vi.mock("./VivoVideo", () => ({
  VivoVideo: ({ videoId, archivo }: { videoId: number; archivo: string }) => {
    useState(() => montajes.push(videoId)); // una entrada por instancia montada
    return <div data-testid="vivo">{`vivo ${videoId} ${archivo}`}</div>;
  },
}));

const video = (id: number, estado: "procesando" | "listo") => ({
  id,
  archivo: `trozo-${id}.mp4`,
  estado,
  capture_ts_inicio: "2026-10-01T12:00:00Z",
});

// `produccion`: la misma configuración que `main.tsx` (staleTime 15 s, un reintento).
function dibujar(produccion = false, existente?: QueryClient) {
  const cliente = existente ?? new QueryClient({
    defaultOptions: { queries: produccion ? { staleTime: 15_000, retry: 1 } : { retry: false } },
  });
  return render(<QueryClientProvider client={cliente}><VistaProcesada /></QueryClientProvider>);
}

beforeEach(() => {
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [] });
});
afterEach(cleanup);

it("rotula la vista con su retraso para que nadie crea que es el mismo instante que la cámara", () => {
  dibujar();
  expect(screen.getByRole("heading", { name: "Vista procesada (≈ 10 s de retraso)" })).toBeInTheDocument();
});

// Un mismo montaje y reloj falso: las transiciones ocurren por el refresco de la consulta.
const montajes: number[] = [];
const avanzar = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
const procesando = (...ids: number[]) => ({ items: ids.map((id) => video(id, "procesando")) });

it("entre trozos: A procesando → ninguno (cartel) → B, por el refresco y con el mismo montaje", async () => {
  vi.useFakeTimers();
  try {
    montajes.length = 0;
    let respuesta = procesando(8);
    vi.mocked(api.listarVideos).mockImplementation(async () => respuesta);
    dibujar();
    await avanzar(0);
    expect(screen.getByTestId("vivo")).toHaveTextContent("vivo 8 trozo-8.mp4");
    expect(screen.queryByText("Esperando el siguiente trozo…")).not.toBeInTheDocument();

    respuesta = { items: [video(8, "listo")] }; // el trozo terminó: ya no hay uno procesando
    const consultas = () => vi.mocked(api.listarVideos).mock.calls.length;
    const antes = consultas();
    await avanzar(999); // aún no toca refrescar (1 s)
    expect(consultas()).toBe(antes);
    expect(screen.getByTestId("vivo")).toBeInTheDocument();
    await avanzar(1);
    expect(consultas()).toBe(antes + 1); // el refresco llegó justo al segundo
    await avanzar(50); // lo que tarda en pintarse la respuesta
    expect(screen.getByText("Esperando el siguiente trozo…")).toBeInTheDocument();
    expect(screen.queryByTestId("vivo")).not.toBeInTheDocument();

    respuesta = procesando(9);
    await avanzar(1_000);
    expect(screen.getByTestId("vivo")).toHaveTextContent("vivo 9 trozo-9.mp4");
    expect(montajes).toEqual([8, 9]); // cada trozo es una instancia nueva (key por id)
    expect(screen.queryByText("Esperando el siguiente trozo…")).not.toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

it("si el video sigue siendo el mismo, el refresco no lo vuelve a montar ni muestra el cartel", async () => {
  vi.useFakeTimers();
  try {
    montajes.length = 0;
    vi.mocked(api.listarVideos).mockImplementation(async () => procesando(8));
    dibujar();
    await avanzar(0);
    await avanzar(3_000);
    expect(vi.mocked(api.listarVideos).mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(montajes).toEqual([8]);
    expect(screen.queryByText("Esperando el siguiente trozo…")).not.toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

it("si un trozo sigue a otro sin hueco, el nuevo es una instancia nueva (la vista de A no se arrastra a B)", async () => {
  vi.useFakeTimers();
  try {
    montajes.length = 0;
    let respuesta = procesando(8);
    vi.mocked(api.listarVideos).mockImplementation(async () => respuesta);
    dibujar();
    await avanzar(0);
    respuesta = procesando(9);
    await avanzar(1_050);
    expect(screen.getByTestId("vivo")).toHaveTextContent("vivo 9");
    expect(montajes).toEqual([8, 9]);
  } finally {
    vi.useRealTimers();
  }
});

it("pide solo los videos `procesando` al servidor, y no los 200 más nuevos", async () => {
  dibujar();
  await waitFor(() => expect(api.listarVideos).toHaveBeenCalled());
  expect(api.listarVideos).toHaveBeenCalledWith(undefined, "procesando");
});

it("si la consulta de videos falla lo dice, y no lo disfraza de «esperando el siguiente trozo»", async () => {
  vi.mocked(api.listarVideos).mockRejectedValue(new api.ApiError("caído", 503));
  dibujar();
  expect(await screen.findByText("No fue posible consultar los videos")).toBeInTheDocument();
  expect(screen.queryByText("Esperando el siguiente trozo…")).not.toBeInTheDocument();
});

// ── Fallos de la consulta de videos ──────────────────────────────────────────────────────────────
it("durante la carga inicial dice «Consultando…»", async () => {
  vi.mocked(api.listarVideos).mockReturnValue(new Promise(() => undefined));
  dibujar();
  expect(await screen.findByText("Consultando…")).toBeInTheDocument();
  expect(screen.queryByText("Esperando el siguiente trozo…")).not.toBeInTheDocument();
});

it.each([
  [401, "Sesión no válida"],
  [403, "No tienes permiso para ver los videos"],
])("con %i dice «%s» y deja de consultar", async (estado, texto) => {
  vi.useFakeTimers();
  try {
    vi.mocked(api.listarVideos).mockRejectedValue(new api.ApiError("no", estado));
    dibujar(true);
    await avanzar(50);
    expect(screen.getByText(texto)).toBeInTheDocument();
    expect(screen.queryByText("No fue posible consultar los videos")).not.toBeInTheDocument();
    const consultas = vi.mocked(api.listarVideos).mock.calls.length;
    await avanzar(10_000);
    expect(vi.mocked(api.listarVideos).mock.calls.length).toBe(consultas); // ni refresco ni reintento
    expect(screen.getByText(texto)).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

it("con 503 persistente y el reintento de producción, el aviso no desaparece entre consultas", async () => {
  vi.useFakeTimers();
  try {
    vi.mocked(api.listarVideos).mockRejectedValue(new api.ApiError("caído", 503));
    dibujar(true);
    for (const segundo of [1, 2, 3, 4, 5]) {
      await avanzar(segundo === 1 ? 1_050 : 1_000);
      expect(screen.getByText("No fue posible consultar los videos"), `segundo ${segundo}`).toBeInTheDocument();
      expect(screen.queryByText("Consultando…")).not.toBeInTheDocument();
    }
    // y cuando por fin responde bien, el aviso se va
    vi.mocked(api.listarVideos).mockResolvedValue({ items: [] });
    await avanzar(3_000);
    expect(screen.queryByText("No fue posible consultar los videos")).not.toBeInTheDocument();
    expect(screen.getByText("Esperando el siguiente trozo…")).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

it("si se sale y se vuelve con el primer GET pendiente y luego llega un 401, la página nueva lo dice", async () => {
  vi.useFakeTimers();
  try {
    const cliente = new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: 1 } } });
    let rechazar: (e: Error) => void = () => undefined;
    vi.mocked(api.listarVideos).mockReturnValue(new Promise((_, no) => { rechazar = no; }));
    const primera = dibujar(true, cliente);
    await avanzar(50);
    primera.unmount();
    dibujar(true, cliente);
    await avanzar(50);
    expect(screen.getByText("Consultando…")).toBeInTheDocument();
    rechazar(new api.ApiError("no", 401));
    await avanzar(50);
    expect(screen.getByText("Sesión no válida")).toBeInTheDocument();
    expect(screen.queryByText("Consultando…")).not.toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

it("tras un 401, «Reintentar» vuelve a consultar y, si ya responde bien, vuelve el cartel y el refresco", async () => {
  vi.useFakeTimers();
  try {
    vi.mocked(api.listarVideos).mockRejectedValueOnce(new api.ApiError("no", 401));
    vi.mocked(api.listarVideos).mockResolvedValue({ items: [] });
    dibujar(true);
    await avanzar(50);
    expect(screen.getByText("Sesión no válida")).toBeInTheDocument();
    await avanzar(5_000);
    expect(api.listarVideos).toHaveBeenCalledTimes(1); // sigue parado hasta que alguien reintente
    act(() => screen.getByRole("button", { name: "Reintentar" }).click());
    await avanzar(50);
    expect(api.listarVideos).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Sesión no válida")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
    expect(screen.getByText("Esperando el siguiente trozo…")).toBeInTheDocument();
    await avanzar(1_000);
    expect(api.listarVideos).toHaveBeenCalledTimes(3); // y el refresco de cada segundo volvió
  } finally {
    vi.useRealTimers();
  }
});

it("un fallo pasajero no borra el último video bueno: se ve el aviso y el video sigue", async () => {
  vi.useFakeTimers();
  try {
    vi.mocked(api.listarVideos).mockResolvedValueOnce(procesando(8));
    vi.mocked(api.listarVideos).mockRejectedValue(new api.ApiError("caído", 503));
    dibujar(true);
    await avanzar(50);
    expect(screen.getByTestId("vivo")).toBeInTheDocument();
    await avanzar(1_000);
    expect(screen.getByText("No fue posible consultar los videos")).toBeInTheDocument();
    expect(screen.getByTestId("vivo")).toHaveTextContent("vivo 8");
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument(); // solo con 401/403
  } finally {
    vi.useRealTimers();
  }
});
