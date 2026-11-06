import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, descargarReporteCsv, obtenerReporte } from "../api/client";
import type { Reporte } from "../api/types";
import { ReporteDotacion } from "./ReporteDotacion";

vi.mock("../api/client", () => ({
  ApiError: class extends Error {
    constructor(message: string, public readonly status: number) { super(message); }
  },
  descargarReporteCsv: vi.fn(),
  obtenerReporte: vi.fn(),
}));

function respuesta(filas: Reporte["filas"]): Reporte {
  return { tipo: "dotacion", segmentacion: "turno", filas };
}

function montar(props: { desde?: string; hasta?: string; areaId?: number } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReporteDotacion {...props} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ReporteDotacion", () => {
  it("consulta solo fecha y área, con segmentación fija por turno", async () => {
    vi.mocked(obtenerReporte).mockResolvedValue(respuesta([{
      etiqueta: "Excavación · Turno A", valor: 12.34, n: 25, datos_insuficientes: false,
      dotacion: { total: 40, hombres: 25, mujeres: 15, otro: 0, datos_insuficientes: false },
    }]));

    montar({ desde: "2026-10-01", hasta: "2026-10-07", areaId: 3 });

    expect(await screen.findByText("12,3 por cada 100 trabajadores")).toBeVisible();
    expect(screen.getByText("≈ 25")).toBeVisible();
    expect(screen.getByText("40 personas")).toBeVisible();
    expect(screen.getByText("Hombres: 25 · Mujeres: 15 · Otro: 0")).toBeVisible();
    expect(obtenerReporte).toHaveBeenCalledWith("dotacion", {
      desde: "2026-10-01", hasta: "2026-10-07", areaId: 3, segmentacion: "turno",
    });
    vi.mocked(descargarReporteCsv).mockResolvedValue("etiqueta,valor");
    fireEvent.click(screen.getByRole("button", { name: "Exportar CSV" }));
    await waitFor(() => expect(descargarReporteCsv).toHaveBeenCalledWith("dotacion", {
      desde: "2026-10-01", hasta: "2026-10-07", areaId: 3, segmentacion: "turno",
    }));
  });

  it.each([
    ["n_insuficiente", "Menos de 5 incumplimientos"],
    ["sin_dotacion", "Sin dotación registrada"],
    ["dotacion_insuficiente", "Dotación menor a 5 personas"],
    ["dotacion_incompleta", "Faltan días de dotación en el período"],
  ] as const)("explica la supresión %s sin mostrarla como cero", async (razon, explicacion) => {
    vi.mocked(obtenerReporte).mockResolvedValue(respuesta([{
      etiqueta: razon, valor: null, n: null, datos_insuficientes: true, razon,
      dotacion: { total: null, hombres: null, mujeres: null, otro: null, datos_insuficientes: true },
    }]));

    montar();

    const fila = await screen.findByRole("row", { name: new RegExp(razon) });
    expect(within(fila).getByText(`Datos insuficientes — ${explicacion}`)).toBeVisible();
    expect(within(fila).queryByText(/0 por cada 100/)).not.toBeInTheDocument();
  });

  it("oculta la composición completa si falta uno de sus grupos", async () => {
    vi.mocked(obtenerReporte).mockResolvedValue(respuesta([{
      etiqueta: "Turno B", valor: null, n: null, datos_insuficientes: true,
      razon: "n_insuficiente", dotacion: { total: 15, hombres: 9, mujeres: null, otro: 0, datos_insuficientes: true },
    }]));

    montar();

    expect(await screen.findByText("No se muestra para proteger a grupos de menos de 5 personas")).toBeVisible();
    expect(screen.queryByText(/Hombres: 9/)).not.toBeInTheDocument();
  });

  it("mantiene las filas anteriores y avisa mientras cambia un filtro", async () => {
    let resolver: ((reporte: Reporte) => void) | undefined;
    const pendiente = new Promise<Reporte>((resolve) => { resolver = resolve; });
    vi.mocked(obtenerReporte)
      .mockResolvedValueOnce(respuesta([{
        etiqueta: "Turno anterior", valor: 8, n: 5, datos_insuficientes: false,
        dotacion: { total: 20, hombres: 10, mujeres: 10, otro: 0, datos_insuficientes: false },
      }]))
      .mockReturnValueOnce(pendiente);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const vista = render(<QueryClientProvider client={client}><ReporteDotacion areaId={1} /></QueryClientProvider>);
    expect(await screen.findByText("Turno anterior")).toBeVisible();

    vista.rerender(<QueryClientProvider client={client}><ReporteDotacion areaId={2} /></QueryClientProvider>);

    expect(screen.getByText("Turno anterior")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("Actualizando datos");
    resolver?.(respuesta([]));
    await waitFor(() => expect(screen.queryByText("Turno anterior")).not.toBeInTheDocument());
    expect(await screen.findByText("No hay información de dotación para los filtros seleccionados.")).toBeVisible();
    vi.mocked(obtenerReporte).mockReturnValueOnce(new Promise(() => undefined));
    vista.rerender(<QueryClientProvider client={client}><ReporteDotacion areaId={3} /></QueryClientProvider>);
    expect(screen.getByRole("status")).toHaveTextContent("Actualizando datos");
  });

  it("distingue carga, falta de permiso, error y resultado vacío", async () => {
    vi.mocked(obtenerReporte).mockImplementationOnce(() => new Promise(() => undefined));
    const carga = montar({ areaId: 1 });
    expect(screen.getByRole("status")).toHaveTextContent("Cargando reporte de dotación");
    expect(screen.getByRole("button", { name: "Exportar CSV" })).toBeDisabled();
    carga.unmount();

    vi.mocked(obtenerReporte).mockRejectedValueOnce(new ApiError("Prohibido", 403));
    const permiso = montar({ areaId: 2 });
    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso");
    expect(screen.getByRole("button", { name: "Exportar CSV" })).toBeDisabled();
    permiso.unmount();

    vi.mocked(obtenerReporte).mockRejectedValueOnce(new Error("Servidor no disponible"));
    const error = montar({ areaId: 3 });
    expect(await screen.findByRole("alert")).toHaveTextContent("No fue posible cargar");
    expect(screen.getByRole("button", { name: "Exportar CSV" })).toBeDisabled();
    error.unmount();

    vi.mocked(obtenerReporte).mockResolvedValueOnce(respuesta([]));
    montar({ areaId: 4 });
    expect(await screen.findByText("No hay información de dotación para los filtros seleccionados.")).toBeVisible();
  });
});
