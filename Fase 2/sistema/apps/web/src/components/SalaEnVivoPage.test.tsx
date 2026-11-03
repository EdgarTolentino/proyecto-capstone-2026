import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../api/client";
import { AppShell } from "./AppShell";
import { SalaEnVivoPage } from "./SalaEnVivoPage";

vi.mock("../api/client", () => ({
  ApiError: class extends Error {
    constructor(message: string, public readonly status: number) { super(message); }
  },
  listarHallazgos: vi.fn(),
  listarVideos: vi.fn(),
}));
vi.mock("../hooks/useEspejoWhep", () => ({
  useEspejoWhep: () => ({ estado: espejo, videoRef: { current: null } }),
}));
vi.mock("./EvidenceDrawer", () => ({
  EvidenceDrawer: ({ hallazgoId, permiteTriar }: { hallazgoId: number; permiteTriar: boolean }) => (
    <aside role="dialog">{`visor H-${hallazgoId} triar=${permiteTriar}`}</aside>
  ),
}));

let espejo: "conectando" | "en_vivo" | "apagada";
const hallazgo = (id: number) => ({ id, severidad: 3, epp_faltante: ["casco"], ts_inicio: "2026-10-01T12:00:00Z" });

function dibujar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={cliente}><SalaEnVivoPage /></QueryClientProvider>);
}

beforeEach(() => {
  espejo = "en_vivo";
  vi.mocked(api.listarHallazgos).mockResolvedValue({ items: [], contadores: {} } as never);
  vi.mocked(api.listarVideos).mockResolvedValue({ items: [] });
});
afterEach(cleanup);

it("rotula la cámara y la vista procesada para que nadie crea que son el mismo instante", async () => {
  dibujar();
  expect(screen.getByRole("heading", { name: "Cámara en vivo" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Vista procesada (≈ 10 s de retraso)" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Hallazgos recientes" })).toBeInTheDocument();
});

it("con la cámara apagada lo dice, y no afirma que haya imagen", () => {
  espejo = "apagada";
  dibujar();
  expect(screen.getByText("Cámara apagada")).toBeInTheDocument();
  expect(screen.getByLabelText("Imagen de la cámara", { selector: "video" })).not.toBeVisible();
});


it("muestra solo los hallazgos más recientes y un clic abre el visor de evidencia sin triage", async () => {
  vi.mocked(api.listarHallazgos).mockResolvedValue({
    items: Array.from({ length: 12 }, (_, i) => hallazgo(100 - i)),
    contadores: {},
  } as never);
  dibujar();
  await screen.findByRole("button", { name: /H-100/ });
  const lista = screen.getByRole("list");
  expect(within(lista).getAllByRole("button")).toHaveLength(8);
  expect(screen.queryByText("H-92")).not.toBeInTheDocument(); // el noveno ya no entra
  await userEvent.click(within(lista).getByRole("button", { name: /H-99/ }));
  expect(screen.getByRole("dialog")).toHaveTextContent("visor H-99 triar=false");
});

it("sin hallazgos lo dice", async () => {
  dibujar();
  await waitFor(() => expect(screen.getByText("Aún no hay hallazgos.")).toBeInTheDocument());
});

// ── La pestaña ───────────────────────────────────────────────────────────────────────────────────
const sesion = (permisos: string[]) => ({ permisos }) as never;
const shell = (permisos: string[]) =>
  render(<AppShell seccion="panel" sesion={sesion(permisos)} onNavigate={vi.fn()}><div /></AppShell>);

it("la pestaña «Sala en vivo» aparece con ver_evidencia", () => {
  shell(["ver_hallazgos", "ver_evidencia"]);
  expect(screen.getByRole("button", { name: /Sala en vivo/ })).toBeInTheDocument();
});

it.each([[["ver_hallazgos"]], [[]]])("sin ver_evidencia (%j) la pestaña ni aparece", (permisos) => {
  shell(permisos);
  expect(screen.queryByRole("button", { name: /Sala en vivo/ })).not.toBeInTheDocument();
});

it("sin sesión cargada tampoco aparece", () => {
  render(<AppShell seccion="panel" onNavigate={vi.fn()}><div /></AppShell>);
  expect(screen.queryByRole("button", { name: /Sala en vivo/ })).not.toBeInTheDocument();
});

it.each([
  [401, "Sesión no válida"],
  [403, "No tienes permiso para ver los hallazgos"],
])("si /hallazgos responde %i dice «%s», deja de consultar y ofrece «Reintentar»", async (estado, texto) => {
  vi.useFakeTimers();
  try {
    vi.mocked(api.listarHallazgos).mockRejectedValueOnce(new api.ApiError("no", estado));
    dibujar();
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(screen.getByText(texto)).toBeInTheDocument();
    expect(screen.queryByText("No fue posible consultar los hallazgos")).not.toBeInTheDocument();
    const consultas = vi.mocked(api.listarHallazgos).mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
    expect(vi.mocked(api.listarHallazgos).mock.calls.length).toBe(consultas); // ni refresco ni reintento
    act(() => screen.getByRole("button", { name: "Reintentar" }).click());
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(vi.mocked(api.listarHallazgos).mock.calls.length).toBe(consultas + 1);
    expect(screen.queryByText(texto)).not.toBeInTheDocument();
    expect(screen.getByText("Aún no hay hallazgos.")).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

it("otro fallo de /hallazgos sale como error genérico, sin botón «Reintentar»", async () => {
  vi.mocked(api.listarHallazgos).mockRejectedValue(new api.ApiError("caído", 503));
  dibujar();
  // un reintento (1 s de espera) antes de dar el error
  expect(await screen.findByText("No fue posible consultar los hallazgos", {}, { timeout: 3_000 })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
});
