import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { usePanelFilters } from "./usePanelFilters";
import { rangoDefectoPanel } from "../api/fechas";

describe("usePanelFilters", () => {
  beforeEach(() => window.history.replaceState({}, "", "/"));

  it("restaura los filtros válidos desde la URL", () => {
    window.history.replaceState({}, "", "/?obra_id=7&desde=2026-09-01&hasta=2026-09-30&turno=A");

    const { result } = renderHook(() => usePanelFilters());

    expect(result.current.filtros).toEqual({
      obraId: 7,
      desde: "2026-09-01",
      hasta: "2026-09-30",
      turno: "A",
    });
  });

  it("actualiza y elimina filtros en una URL compartible", () => {
    const rango = rangoDefectoPanel();
    const { result } = renderHook(() => usePanelFilters());

    act(() => result.current.actualizar({ obraId: 3, turno: "B" }));
    expect(window.location.search).toBe(`?desde=${rango.desde}&hasta=${rango.hasta}&obra_id=3&turno=B`);

    act(() => result.current.actualizar({ obraId: undefined }));
    expect(window.location.search).toBe(`?desde=${rango.desde}&hasta=${rango.hasta}&turno=B`);
    expect(result.current.filtros).toEqual({ desde: rango.desde, hasta: rango.hasta, turno: "B" });
  });

  it("descarta fechas e identificadores inválidos", () => {
    window.history.replaceState({}, "", "/?obra_id=no&desde=2026-13-01&hasta=2026-09-30");

    const { result } = renderHook(() => usePanelFilters());

    expect(result.current.filtros).toEqual({ hasta: "2026-09-30" });
    expect(window.location.search).toBe("?hasta=2026-09-30");
  });

  it("usa un rango explícito de siete días calendario cuando se abre el panel sin fechas", () => {
    const rango = rangoDefectoPanel();
    const { result } = renderHook(() => usePanelFilters());

    expect(result.current.filtros).toEqual(rango);
    expect(new URL(window.location.href).searchParams.get("desde")).toBe(rango.desde);
    expect(new URL(window.location.href).searchParams.get("hasta")).toBe(rango.hasta);
  });

  it.each(["/videos", "/hallazgos", "/reglas"])("no agrega las fechas del panel a la URL de %s", (ruta) => {
    window.history.replaceState({}, "", ruta);

    renderHook(() => usePanelFilters());

    expect(window.location.pathname).toBe(ruta);
    expect(window.location.search).toBe("");
  });
});
