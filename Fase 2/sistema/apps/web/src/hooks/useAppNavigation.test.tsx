import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";

import { useAppNavigation } from "./useAppNavigation";
import { useHallazgoFilters } from "./useHallazgoFilters";
import { usePanelFilters } from "./usePanelFilters";

beforeEach(() => window.history.replaceState({}, "", "/?desde=2026-09-01&hasta=2026-09-07&turno=A&obra_id=2&inventado=x"));

it("abre Hallazgos con filtros válidos y conserva solo los compatibles", () => {
  const { result } = renderHook(() => ({ navegacion: useAppNavigation(), hallazgos: useHallazgoFilters(), panel: usePanelFilters() }));

  act(() => result.current.navegacion.navegarHallazgos({ vista: "todos", severidad: 4, epp: "casco" }));

  const parametros = new URL(window.location.href).searchParams;
  expect(window.location.pathname).toBe("/hallazgos");
  expect([...parametros.keys()].sort()).toEqual(["desde", "epp", "hasta", "obra_no_filtrada", "severidad", "turno", "vista"]);
  expect(parametros.get("obra_id")).toBeNull();
  expect(parametros.get("obra_no_filtrada")).toBe("2");
  expect(parametros.get("inventado")).toBeNull();
  expect(result.current.hallazgos.filtros).toEqual(expect.objectContaining({ vista: "todos", severidad: "4", epp: "casco", desde: "2026-09-01", hasta: "2026-09-07", turno: "A" }));

  act(() => result.current.navegacion.navegar("panel"));
  expect(`${window.location.pathname}${window.location.search}`).toBe("/?desde=2026-09-01&hasta=2026-09-07&turno=A&obra_id=2");
  expect(result.current.panel.filtros).toEqual({ desde: "2026-09-01", hasta: "2026-09-07", turno: "A", obraId: 2 });

  act(() => result.current.navegacion.navegarHallazgos({ vista: "todos", severidad: 4, hallazgoId: 4821 }));
  expect(window.location.search).toContain("hallazgo=4821");
  expect(window.location.search).not.toContain("epp=");
});

it("sincroniza los filtros visibles al ir desde el panel a Hallazgos desde la barra", () => {
  window.history.replaceState({}, "", "/?desde=2026-09-01&hasta=2026-09-07&turno=A&obra_id=2");
  const { result } = renderHook(() => ({ navegacion: useAppNavigation(), hallazgos: useHallazgoFilters(), panel: usePanelFilters() }));

  act(() => result.current.navegacion.navegar("hallazgos"));

  expect(window.location.pathname).toBe("/hallazgos");
  expect(window.location.search).toContain("desde=2026-09-01");
  expect(window.location.search).toContain("hasta=2026-09-07");
  expect(window.location.search).toContain("turno=A");
  expect(result.current.hallazgos.filtros).toEqual(expect.objectContaining({ desde: "2026-09-01", hasta: "2026-09-07", turno: "A" }));

  act(() => result.current.navegacion.navegar("panel"));

  expect(result.current.panel.filtros).toEqual({ desde: "2026-09-01", hasta: "2026-09-07", turno: "A", obraId: 2 });
});

it("lleva al panel las fechas y el turno compatibles de un enlace a Hallazgos", () => {
  window.history.replaceState({}, "", "/hallazgos?desde=2026-09-01&hasta=2026-09-07&turno=A&severidad=4");
  const { result } = renderHook(() => useAppNavigation());

  act(() => result.current.navegar("panel"));

  expect(`${window.location.pathname}${window.location.search}`).toBe("/?desde=2026-09-01&hasta=2026-09-07&turno=A");
});
