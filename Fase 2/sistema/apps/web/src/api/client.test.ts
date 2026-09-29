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
});
