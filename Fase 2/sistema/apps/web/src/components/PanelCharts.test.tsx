import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { PanelCharts } from "./PanelCharts";

it("muestra solo cuatro series y el top cinco de EPP más Otros", () => {
  const tendencia = {
    etiquetas: ["L", "M", "M", "J", "V", "S", "D"],
    series: [
      { severidad: 4 as const, valores: [5, 4, 6, 3, 7, 2, 4] },
      { severidad: 3 as const, valores: [3, 2, 4, 5, 3, 1, 2] },
      { severidad: 2 as const, valores: [2, 3, 1, 2, 4, 3, 2] },
      { severidad: 1 as const, valores: [1, 1, 2, 1, 2, 1, 1] },
      { severidad: 4 as const, valores: [9, 9, 9, 9, 9, 9, 9] },
    ],
  };
  const rankingEpp = [
    { epp: "casco", total: 61 },
    { epp: "chaleco", total: 42 },
    { epp: "lentes", total: 30 },
    { epp: "guantes", total: 25 },
    { epp: "arnes", total: 18 },
    { epp: "calzado", total: 12 },
    { epp: "otros", total: 7 },
  ];

  const { container } = render(<PanelCharts tendencia={tendencia} rankingEpp={rankingEpp} />);

  expect(container.querySelectorAll(".panel-chart")).toHaveLength(2);
  expect(screen.getByRole("region", { name: "Tendencia semanal por severidad" })).toBeVisible();
  expect(container.querySelectorAll(".panel-trend__line")).toHaveLength(4);
  expect(screen.getByRole("table", { name: "Datos de tendencia semanal por severidad" })).toHaveTextContent("Crítica");
  expect(screen.getByRole("table", { name: "Datos de tendencia semanal por severidad" })).toHaveTextContent("Baja");

  const ranking = screen.getByRole("list", { name: "Ranking de EPP incumplido" });
  expect(within(ranking).getAllByRole("listitem")).toHaveLength(6);
  expect(within(ranking).getByText("Otros")).toBeVisible();
  expect(within(ranking).queryByText("Calzado")).not.toBeInTheDocument();
});
