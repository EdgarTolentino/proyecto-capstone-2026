import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useReporteFilters } from "./useReporteFilters";
import { rangoDefectoPanel } from "../api/fechas";

describe("useReporteFilters", () => {
  beforeEach(() => window.history.replaceState({}, "", "/reportes"));

  it("lee filtros válidos desde la URL y descarta área y fechas inválidas", () => {
    window.history.replaceState({}, "", "/reportes?area_id=7&desde=2026-09-01&hasta=2026-09-30&segmentacion=turno");
    const { result } = renderHook(() => useReporteFilters());

    expect(result.current.filtros).toEqual({ areaId: 7, desde: "2026-09-01", hasta: "2026-09-30", segmentacion: "turno" });

    window.history.replaceState({}, "", "/reportes?area_id=no&desde=2026-13-01&hasta=2026-02-30&segmentacion=rostro");
    act(() => window.dispatchEvent(new PopStateEvent("popstate")));

    expect(result.current.filtros).toEqual(rangoDefectoPanel());
    expect(new URL(window.location.href).searchParams.has("area_id")).toBe(false);
    expect(new URL(window.location.href).searchParams.has("segmentacion")).toBe(false);
  });

  it("actualiza los filtros en una URL compartible y restablece el rango por defecto", () => {
    const rango = rangoDefectoPanel();
    const { result } = renderHook(() => useReporteFilters());

    act(() => result.current.actualizar({ areaId: 3 }));
    expect(new URL(window.location.href).searchParams.get("area_id")).toBe("3");
    expect(result.current.filtros).toEqual({ ...rango, areaId: 3 });

    act(() => result.current.actualizar({ desde: "2026-09-01", hasta: "2026-09-30", segmentacion: "turno" }));
    expect(new URL(window.location.href).searchParams.get("desde")).toBe("2026-09-01");
    expect(result.current.filtros).toEqual({ areaId: 3, desde: "2026-09-01", hasta: "2026-09-30", segmentacion: "turno" });

    act(() => result.current.actualizar({ desde: undefined, hasta: undefined, areaId: undefined, segmentacion: undefined }));
    expect(result.current.filtros).toEqual(rango);
  });

  it("normaliza un rango invertido", () => {
    window.history.replaceState({}, "", "/reportes?desde=2026-09-30&hasta=2026-09-01");
    const { result } = renderHook(() => useReporteFilters());

    expect(result.current.filtros).toEqual(rangoDefectoPanel());
  });

  it("no modifica los filtros de otras secciones", () => {
    window.history.replaceState({}, "", "/?obra_id=2");
    const { result } = renderHook(() => useReporteFilters());

    expect(result.current.filtros).toEqual({});
    expect(window.location.search).toBe("?obra_id=2");
  });
});
