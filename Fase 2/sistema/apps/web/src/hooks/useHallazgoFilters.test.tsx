import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useHallazgoFilters } from "./useHallazgoFilters";

describe("useHallazgoFilters", () => {
  beforeEach(() => window.history.replaceState({}, "", "/hallazgos"));

  it("guarda los filtros en la URL para poder compartirlos", () => {
    const { result } = renderHook(() => useHallazgoFilters());

    act(() => result.current.actualizar({ severidad: "4", areaId: "5" }));

    expect(window.location.search).toContain("severidad=4");
    expect(window.location.search).toContain("area_id=5");
    expect(result.current.filtros.severidad).toBe("4");
  });

  it("abre un hallazgo mediante un enlace directo", () => {
    window.history.replaceState({}, "", "/hallazgos?hallazgo=4821");
    const { result } = renderHook(() => useHallazgoFilters());

    expect(result.current.filtros.hallazgoId).toBe(4821);
  });
});
