import { afterEach, describe, expect, it, vi } from "vitest";

import type { ReglaEntrada } from "./types";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("cliente API", () => {
  it("resuelve una VITE_API_URL relativa y centraliza la autorización", async () => {
    vi.stubEnv("VITE_API_URL", "/api/v1");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ permisos: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { obtenerSesion } = await import("./client");

    await obtenerSesion();

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://localhost:3000/api/v1/yo");
    expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer demo");
  });

  it("entra con la cuenta de VITE_API_TOKEN cuando está definida", async () => {
    vi.stubEnv("VITE_API_TOKEN", "mortega");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ permisos: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { obtenerSesion } = await import("./client");

    await obtenerSesion();

    const [, options] = fetchMock.mock.calls[0];
    expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer mortega");
  });

  it("pide los cuadros en vivo con el desde, el Bearer en la cabecera, sin token en la URL ni caché", async () => {
    vi.stubEnv("VITE_API_TOKEN", "mortega");
    const cuerpo = { cuadros: [{ seq: 7, posicion_s: 0.25, jpeg: "AAAA" }], ultimo_seq: 7 };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(cuerpo), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    const { obtenerCuadrosVivo } = await import("./client");
    const controlador = new AbortController();

    const resultado = await obtenerCuadrosVivo(88, 6, controlador.signal);

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:4010/videos/88/vivo/cuadros?desde=6");
    expect(String(url)).not.toContain("mortega");
    expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer mortega");
    expect(options?.cache).toBe("no-store");
    expect(options?.signal).toBe(controlador.signal);
    expect(resultado).toEqual(cuerpo);
  });

  it.each([401, 403, 404, 500])("los cuadros en vivo con un %i lanzan ApiError con ese status", async (status) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status }));
    const { ApiError, obtenerCuadrosVivo } = await import("./client");

    const error = await obtenerCuadrosVivo(88, 0).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as { status: number }).status).toBe(status);
  });

  it("no considera pospuesto dentro de Descartados", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        items: [
          { id: 1, estado: "falso_positivo" },
          { id: 2, estado: "duplicado" },
          { id: 3, estado: "pospuesto" },
        ],
        contadores: { descartado: 2 },
      }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    const { listarHallazgos } = await import("./client");

    const pagina = await listarHallazgos({ vista: "descartados" });

    expect(pagina.items.map((item) => item.id)).toEqual([1, 2]);
    expect(pagina.contadores?.descartado).toBe(pagina.items.length);
  });

  it("envía area_id al consultar las reglas por área", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { listarReglas } = await import("./client");

    await listarReglas("5");

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:4010/reglas?area_id=5");
  });

  it("consulta el panel con sus filtros y conserva la respuesta tipada", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ indicadores: [], tendencia: {}, ranking_epp: [], criticos_recientes: [], cobertura: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { obtenerPanel } = await import("./client");

    const panel = await obtenerPanel({
      desde: "2026-10-01T00:00:00Z",
      hasta: "2026-10-01T23:59:59Z",
      turno: "A",
      obraId: 7,
    });

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:4010/panel?desde=2026-10-01T00%3A00%3A00Z&hasta=2026-10-01T23%3A59%3A59Z&turno=A&obra_id=7");
    expect(new Headers(options?.headers).get("Authorization")).toBe("Bearer demo");
    expect(panel.indicadores).toEqual([]);
  });

  it("consulta el panel sin query cuando no hay filtros", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ indicadores: [], tendencia: {}, ranking_epp: [], criticos_recientes: [], cobertura: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { obtenerPanel } = await import("./client");

    await obtenerPanel();

    expect(String(fetchMock.mock.calls[0][0])).toBe("http://127.0.0.1:4010/panel");
  });

  it("convierte las fechas del selector en límites completos del día", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ indicadores: [], tendencia: {}, ranking_epp: [], criticos_recientes: [], cobertura: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { obtenerPanel } = await import("./client");

    await obtenerPanel({ desde: "2026-10-01", hasta: "2026-10-02" });

    const url = new URL(String(fetchMock.mock.calls[0][0]));
    expect(url.searchParams.get("desde")).toBe("2026-10-01T03:00:00.000Z");
    expect(url.searchParams.get("hasta")).toBe("2026-10-03T03:00:00.000Z");
  });

  it("usa el inicio del día siguiente como límite exclusivo del rango de Hallazgos", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ items: [], contadores: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { listarHallazgos } = await import("./client");

    await listarHallazgos({ vista: "todos", desde: "2026-10-01", hasta: "2026-10-01" });

    const url = new URL(String(fetchMock.mock.calls[0][0]));
    expect(url.searchParams.get("desde")).toBe("2026-10-01T03:00:00.000Z");
    expect(url.searchParams.get("hasta")).toBe("2026-10-02T03:00:00.000Z");
  });

  it("resuelve una medianoche inexistente por cambio de hora en la faena", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ indicadores: [], tendencia: {}, ranking_epp: [], criticos_recientes: [], cobertura: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { obtenerPanel } = await import("./client");

    await obtenerPanel({ desde: "2026-09-06", hasta: "2026-09-06" });

    const url = new URL(String(fetchMock.mock.calls[0][0]));
    expect(url.searchParams.get("desde")).toBe("2026-09-06T04:00:00.000Z");
    expect(url.searchParams.get("hasta")).toBe("2026-09-07T03:00:00.000Z");
  });

  it("ignora fechas imposibles en las consultas de Panel y Hallazgos", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ items: [], contadores: {}, indicadores: [], tendencia: {}, ranking_epp: [], criticos_recientes: [], cobertura: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { listarHallazgos, obtenerPanel } = await import("./client");

    await obtenerPanel({ desde: "2026-13-01", hasta: "2026-02-30" });
    await listarHallazgos({ vista: "todos", desde: "2026-13-01", hasta: "2026-02-30" });

    for (const [url] of fetchMock.mock.calls) {
      expect(new URL(String(url)).searchParams.has("desde")).toBe(false);
      expect(new URL(String(url)).searchParams.has("hasta")).toBe(false);
    }
  });

  it("crea, versiona y simula reglas con los endpoints del contrato", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ id: 12, version: 1, hallazgos_estimados: 0 }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    const { actualizarRegla, crearRegla, simularRegla } = await import("./client");
    const entrada: ReglaEntrada = { nombre: "Casco", area_id: 3, epp_exigido: ["casco"], confirmacion_segundos: 2, cierre_segundos: 3, confianza_minima: 0.45, severidad: 2, activa: true, base_licitud: "obligacion_legal", finalidad_declarada: "Prevención", retencion_dias: 30 };

    await crearRegla(entrada);
    await actualizarRegla(12, entrada);
    await simularRegla(12, { desde: "2026-08-29", hasta: "2026-09-28", regla: entrada });

    expect(fetchMock.mock.calls.map(([url, options]) => [String(url), options?.method, options?.body])).toEqual([
      ["http://127.0.0.1:4010/reglas", "POST", JSON.stringify(entrada)],
      ["http://127.0.0.1:4010/reglas/12", "PUT", JSON.stringify(entrada)],
      ["http://127.0.0.1:4010/reglas/12/simular", "POST", JSON.stringify({ desde: "2026-08-29", hasta: "2026-09-28", regla: entrada })],
    ]);
  });

  it("pide la entrada y los pedidos, y envía el pedido de ingesta con su cuerpo", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async () => new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    const { listarEntradaVideos, listarPedidos, pedirIngesta } = await import("./client");

    await listarEntradaVideos();
    await listarPedidos();
    await pedirIngesta({ archivo: "CAM-03 ñ.mp4", fuente_id: 3 });

    expect(fetchMock.mock.calls.map(([url, options]) => [String(url), options?.method ?? "GET", options?.body])).toEqual([
      ["http://127.0.0.1:4010/videos/entrada", "GET", undefined],
      ["http://127.0.0.1:4010/videos/pedidos", "GET", undefined],
      ["http://127.0.0.1:4010/videos", "POST", JSON.stringify({ archivo: "CAM-03 ñ.mp4", fuente_id: 3 })],
    ]);
  });

  it("expone el código del error para distinguir los 409", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ codigo: "pedido_existente", mensaje: "Ya hay un pedido" }), { status: 409, headers: { "Content-Type": "application/json" } }),
    );
    const { ApiError, pedirIngesta } = await import("./client");

    const error = await pedirIngesta({ archivo: "a.mp4", fuente_id: 1 }).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, codigo: "pedido_existente", message: "Ya hay un pedido" });
  });

  it("sin cuerpo JSON o con un código que no es texto, el error queda sin código", async () => {
    const respuestas = [new Response("no es json", { status: 502 }), new Response(JSON.stringify({ codigo: 7, mensaje: "x" }), { status: 409 })];
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => respuestas.shift() as Response);
    const { listarPedidos } = await import("./client");

    for (const status of [502, 409]) {
      const error = await listarPedidos().catch((e: unknown) => e);
      expect(error).toMatchObject({ status, codigo: undefined });
    }
  });
});
