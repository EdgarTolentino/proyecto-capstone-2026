import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { usePanelFilters } from "./usePanelFilters";

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
    const { result } = renderHook(() => usePanelFilters());

    act(() => result.current.actualizar({ obraId: 3, turno: "B" }));
    expect(window.location.search).toBe("?obra_id=3&turno=B");

    act(() => result.current.actualizar({ obraId: undefined }));
    expect(window.location.search).toBe("?turno=B");
    expect(result.current.filtros).toEqual({ turno: "B" });
  });

  it("descarta fechas e identificadores inválidos", () => {
    window.history.replaceState({}, "", "/?obra_id=no&desde=01-09-2026&hasta=2026-09-30");

    const { result } = renderHook(() => usePanelFilters());

    expect(result.current.filtros).toEqual({ hasta: "2026-09-30" });
  });
});
