import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../api/client";
import type { Hallazgo } from "../api/types";
import { EvidenceDrawer } from "./EvidenceDrawer";

vi.mock("../api/client", () => ({ obtenerHallazgo: vi.fn() }));

afterEach(() => { cleanup(); vi.resetAllMocks(); });

function abrir(hallazgoId: number, cola: number[]) {
  vi.mocked(api.obtenerHallazgo).mockResolvedValue({
    id: hallazgoId,
    severidad: 3,
    epp_faltante: ["casco"],
    area: { nombre: "Área" },
    zona: { nombre: "Zona" },
    ts_inicio: "2026-10-02T08:00:00Z",
    duracion_s: 5,
    evidencias: [],
    por_que_se_disparo: { regla_nombre: "Regla", regla_version: 1, epp_exigido: ["casco"], valores_observados: "—" },
    tecnicos: {},
    linea_tiempo: {},
    fuente: { nombre: "Cámara" },
    descripcion_automatica: null,
    aviso_legal: "",
  } as never);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EvidenceDrawer
        hallazgoId={hallazgoId}
        cola={cola.map((id) => ({ id }) as Hallazgo)}
        permiteTriar
        onClose={vi.fn()}
        onMove={vi.fn()}
        onTriage={vi.fn()}
        onFalsePositive={vi.fn()}
        isUpdating={false}
      />
    </QueryClientProvider>,
  );
}

it("muestra el lugar del hallazgo abierto en la cola", async () => {
  abrir(2, [3, 2, 1]);

  expect(await screen.findByText("2 de 3 en la cola")).toBeVisible();
  expect(screen.getByRole("button", { name: "Hallazgo anterior" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Hallazgo siguiente" })).toBeEnabled();
});

it("si el hallazgo abierto ya no está en la lista, no inventa un lugar ni vecinos", async () => {
  abrir(9, [4, 3, 2]); // llegaron otros y el 9 salió de la página

  expect(await screen.findByText("Fuera de la lista actual")).toBeVisible();
  expect(screen.queryByText(/de 3 en la cola/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Hallazgo anterior" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Hallazgo siguiente" })).toBeDisabled();
});
