import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { Hallazgo } from "../api/types";
import { HallazgosGrid } from "./HallazgosGrid";

// Con la grilla REAL (sin mockear el virtualizador). jsdom no calcula layout: se le da una
// ventana de 400 px y un `scrollTo` que mueve `scrollTop`, que es lo que hace el navegador.
function hallazgo(id: number): Hallazgo {
  return {
    id,
    severidad: 3,
    epp_faltante: ["casco"],
    ts_inicio: "2026-10-02T08:00:00Z",
    duracion_s: 5,
    cuadros_confirmados: 3,
    confianza_media: 0.9,
  } as Hallazgo;
}

const lista = (...ids: number[]) => ids.map(hallazgo);

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(400);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width: 800, height: 400, top: 0, left: 0, right: 800, bottom: 400, x: 0, y: 0, toJSON: () => ({}),
  });
  HTMLElement.prototype.scrollTo = function (this: HTMLElement, opciones?: ScrollToOptions | number) {
    if (typeof opciones === "object" && opciones.top !== undefined) this.scrollTop = opciones.top;
  } as typeof HTMLElement.prototype.scrollTo;
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function props(hallazgos: Hallazgo[], activoId: number) {
  return {
    hallazgos,
    activoId,
    seleccionados: new Set<number>(),
    permiteSeleccionar: true,
    permiteEvidencia: true,
    onActivate: vi.fn(),
    onOpen: vi.fn(),
    onSelect: vi.fn(),
    onSelectAll: vi.fn(),
  };
}

const ids = Array.from({ length: 200 }, (_, i) => 200 - i);

it("al llegar un hallazgo nuevo la vista de quien mira no se mueve", () => {
  const { container, rerender } = render(<HallazgosGrid {...props(lista(...ids), 200)} />);
  const viewport = container.querySelector<HTMLElement>(".grid-viewport")!;
  viewport.scrollTop = 3200; // la persona bajó con la rueda
  const scrollTo = vi.spyOn(HTMLElement.prototype, "scrollTo");

  rerender(<HallazgosGrid {...props(lista(201, ...ids.slice(0, -1)), 200)} />);

  expect(viewport.scrollTop).toBe(3200);
  expect(scrollTo).not.toHaveBeenCalled();
});

it("cuando cambia la fila activa (j/k) sí se pide llevarla a la vista", () => {
  const { rerender } = render(<HallazgosGrid {...props(lista(...ids), 200)} />);
  const scrollTo = vi.spyOn(HTMLElement.prototype, "scrollTo");

  rerender(<HallazgosGrid {...props(lista(...ids), 100)} />);

  expect(scrollTo).toHaveBeenCalledTimes(1);
});
