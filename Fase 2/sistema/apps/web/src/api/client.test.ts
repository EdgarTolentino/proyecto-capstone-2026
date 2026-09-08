import { afterEach, describe, expect, it, vi } from "vitest";

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
});
