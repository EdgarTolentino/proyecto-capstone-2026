import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { PanelFilters } from "./PanelFilters";

it("ofrece obra, fechas y turno y permite limpiarlos", () => {
  const cambiar = vi.fn();
  render(
    <PanelFilters
      filtros={{ obraId: 7, desde: "2026-09-01", hasta: "2026-09-30", turno: "A" }}
      catalogos={{
        obras: [{ id: 7, nombre: "Edificio Norte" }],
        turnos: [{ codigo: "A", etiqueta: "Turno A" }],
      }}
      onChange={cambiar}
    />,
  );

  expect(screen.getByRole("combobox", { name: "Obra" })).toHaveValue("7");
  expect(screen.getByLabelText("Desde")).toHaveAttribute("max", "2026-09-30");
  expect(screen.getByLabelText("Hasta")).toHaveAttribute("min", "2026-09-01");
  expect(screen.getByRole("combobox", { name: "Turno" })).toHaveValue("A");

  fireEvent.click(screen.getByRole("button", { name: "Limpiar filtros del panel" }));
  expect(cambiar).toHaveBeenCalledWith({ obraId: undefined, desde: undefined, hasta: undefined, turno: undefined });
});
