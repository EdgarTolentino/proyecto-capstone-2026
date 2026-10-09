import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { AvanceVideo as Avance } from "../api/types";
import { AvanceVideo } from "./AvanceVideo";

afterEach(cleanup);

function avanceDePrueba(cambios: Partial<Avance> = {}): Avance {
  return {
    fase: "analizando",
    segundos: 150,
    total_segundos: 300,
    velocidad: 0.8,
    ultimo: { persona: 3, casco: 2, chaleco: 1 },
    actualizado: "2026-10-08T10:00:00Z",
    ...cambios,
  };
}

function mostrar(avance: Avance | null | undefined) {
  render(<AvanceVideo avance={avance} archivo="v.mp4" />);
}

describe("con el total conocido", () => {
  it("muestra la barra con sus valores accesibles y el texto visible", () => {
    mostrar(avanceDePrueba());

    const barra = screen.getByRole("progressbar", { name: "Avance de v.mp4" });
    expect(barra).toHaveAttribute("aria-valuemin", "0");
    expect(barra).toHaveAttribute("aria-valuemax", "300");
    expect(barra).toHaveAttribute("aria-valuenow", "150");
    expect(barra).toHaveAttribute("aria-valuetext", "2 minutos 30 segundos de 5 minutos");
    expect(screen.getByText("2:30 de 5:00 (50 %)")).toBeVisible();
  });

  it("el porcentaje no sube a 100 % antes de terminar (299,9 de 300 → 99 %)", () => {
    mostrar(avanceDePrueba({ segundos: 299.9 }));

    expect(screen.getByText("4:59 de 5:00 (99 %)")).toBeVisible();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "299");
  });

  it("al inicio marca 0 % y al final 100 %", () => {
    mostrar(avanceDePrueba({ segundos: 0 }));
    expect(screen.getByText("0:00 de 5:00 (0 %)")).toBeVisible();
    cleanup();
    mostrar(avanceDePrueba({ segundos: 300 }));
    expect(screen.getByText("5:00 de 5:00 (100 %)")).toBeVisible();
  });

  it("si los segundos pasan del total, la barra no se sale: queda en el total", () => {
    mostrar(avanceDePrueba({ segundos: 320 }));

    expect(screen.getByText("5:00 de 5:00 (100 %)")).toBeVisible();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "300");
  });

  it.each([-5, Number.NaN, Number.POSITIVE_INFINITY])("un valor inválido (%s) cuenta como 0", (segundos) => {
    mostrar(avanceDePrueba({ segundos }));

    expect(screen.getByText("0:00 de 5:00 (0 %)")).toBeVisible();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });

  it("dice las horas cuando el video las tiene", () => {
    mostrar(avanceDePrueba({ segundos: 3723, total_segundos: 7200 }));

    expect(screen.getByText("1:02:03 de 2:00:00 (51 %)")).toBeVisible();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "1 hora 2 minutos 3 segundos de 2 horas");
  });
});

describe("sin el total", () => {
  it.each([null, 0, -1, Number.NaN])("con total %s la barra es indeterminada y solo dice el tiempo transcurrido", (total) => {
    mostrar(avanceDePrueba({ total_segundos: total }));

    const barra = screen.getByRole("progressbar");
    expect(barra).not.toHaveAttribute("aria-valuenow");
    expect(barra).not.toHaveAttribute("aria-valuemax");
    expect(barra).toHaveAttribute("aria-valuetext", "2 minutos 30 segundos transcurridos");
    expect(screen.getByText("2:30 transcurridos")).toBeVisible();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });
});

describe("al guardar", () => {
  it("la barra queda completa y dice «Guardando resultados…»", () => {
    mostrar(avanceDePrueba({ fase: "guardando", segundos: 290 }));

    const barra = screen.getByRole("progressbar");
    expect(barra).toHaveAttribute("aria-valuenow", "300");
    expect(barra).toHaveAttribute("aria-valuemax", "300");
    expect(barra).toHaveAttribute("aria-valuetext", "Guardando resultados");
    expect(screen.getByText("Guardando resultados…")).toBeVisible();
    expect(screen.queryByText(/de 5:00/)).not.toBeInTheDocument();
    expect(screen.queryByText(/tiempo real/)).not.toBeInTheDocument();
  });

  it("sin total conocido también queda completa, con valor", () => {
    mostrar(avanceDePrueba({ fase: "guardando", total_segundos: null, segundos: 120 }));

    const barra = screen.getByRole("progressbar");
    expect(barra).toHaveAttribute("aria-valuenow", "120");
    expect(barra).toHaveAttribute("aria-valuemax", "120");
  });
});

describe("sin avance publicado", () => {
  it.each([null, undefined])("con avance %s dice «Procesando…» y no dibuja barra", (avance) => {
    mostrar(avance);

    expect(screen.getByText("Procesando…")).toBeVisible();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});

describe("lo detectado en el cuadro actual", () => {
  it("lo rotula como cuadro actual y no como total", () => {
    mostrar(avanceDePrueba());

    expect(screen.getByText("En el cuadro actual: 3 personas, 2 cascos, 1 chaleco.")).toBeVisible();
    expect(screen.queryByText(/total/i)).not.toBeInTheDocument();
  });

  it("usa el singular con 1 y el plural con 0", () => {
    mostrar(avanceDePrueba({ ultimo: { persona: 1, casco: 0, chaleco: 2 } }));

    expect(screen.getByText("En el cuadro actual: 1 persona, 0 cascos, 2 chalecos.")).toBeVisible();
  });

  it("con `ultimo` nulo dice que no hay datos y no inventa conteos", () => {
    mostrar(avanceDePrueba({ ultimo: null }));

    expect(screen.getByText("Sin datos del cuadro actual.")).toBeVisible();
    expect(screen.queryByText(/personas?,/)).not.toBeInTheDocument();
  });

  it.each([-1, 1.5, Number.NaN])("un conteo inválido (%s) no se muestra", (valor) => {
    mostrar(avanceDePrueba({ ultimo: { persona: valor, casco: 2, chaleco: 1 } }));

    expect(screen.getByText("Sin datos del cuadro actual.")).toBeVisible();
    expect(screen.queryByText(/En el cuadro actual/)).not.toBeInTheDocument();
  });
});

describe("velocidad", () => {
  it.each([
    [0.8, "0,8× tiempo real"],
    [1, "1,0× tiempo real"], // tiempo real justo
    [2.5, "2,5× tiempo real"],
    [0, "0,0× tiempo real"], // medida, y es cero
  ])("con velocidad %s se muestra «%s»", (velocidad, texto) => {
    mostrar(avanceDePrueba({ velocidad }));

    expect(screen.getByText(texto)).toBeVisible();
  });

  it.each([null, -1, Number.NaN])("con velocidad %s no se muestra", (velocidad) => {
    mostrar(avanceDePrueba({ velocidad }));

    expect(screen.queryByText(/tiempo real/)).not.toBeInTheDocument();
    expect(screen.getByText("2:30 de 5:00 (50 %)")).toBeVisible();
  });
});

describe("hora de publicación", () => {
  it("si es nula no rompe nada, y si viene no se muestra", () => {
    mostrar(avanceDePrueba({ actualizado: null }));
    expect(screen.getByText("2:30 de 5:00 (50 %)")).toBeVisible();
    cleanup();
    mostrar(avanceDePrueba({ actualizado: "2026-10-08T10:00:00Z" }));
    expect(screen.queryByText(/2026|10:00/)).not.toBeInTheDocument();
  });
});

describe("con un total menor que un segundo", () => {
  it("lo accesible dice lo mismo que lo visible: el porcentaje, no 0 de 0 segundos", () => {
    mostrar(avanceDePrueba({ segundos: 0.25, total_segundos: 0.5 }));

    expect(screen.getByText("0:00 de 0:00 (50 %)")).toBeVisible();
    const barra = screen.getByRole("progressbar");
    expect(barra).toHaveAttribute("aria-valuemax", "100");
    expect(barra).toHaveAttribute("aria-valuenow", "50");
    expect(barra).toHaveAttribute("aria-valuetext", "50 %");
  });

  it.each([
    [0, 0.75, "0"],
    [0.75, 0.75, "100"],
    [0.875, 0.75, "100"],
  ])("en los extremos: %s de %s s marca %s por ciento", (segundos, total, esperado) => {
    mostrar(avanceDePrueba({ segundos, total_segundos: total }));

    const barra = screen.getByRole("progressbar");
    expect(barra).toHaveAttribute("aria-valuenow", esperado);
    expect(barra).toHaveAttribute("aria-valuetext", `${esperado} %`);
  });

  it("con un total de justo 1 s vuelve a usar segundos", () => {
    mostrar(avanceDePrueba({ segundos: 0.5, total_segundos: 1 }));

    const barra = screen.getByRole("progressbar");
    expect(barra).toHaveAttribute("aria-valuemax", "1");
    expect(barra).toHaveAttribute("aria-valuenow", "0");
    expect(barra).toHaveAttribute("aria-valuetext", "0 segundos de 1 segundo");
  });
});
