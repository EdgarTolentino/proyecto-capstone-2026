import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import { EvidenceDrawer } from "./EvidenceDrawer";

import type { Sesion } from "../api/types";
import { UserMenu } from "./UserMenu";

const sesion: Sesion = { id: 0, nombre: "Miguel Ortega", rol: "administrador", permisos: [] };
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Menú de usuario", () => {
  it("mantiene foco, Tab y Escape en la Guía si el historial vuelve a montar el visor detrás", async () => {
    vi.spyOn(api, "obtenerHallazgo").mockImplementation(() => new Promise(() => {}));
    const user = userEvent.setup();
    const client = new QueryClient();
    const cerrarVisor = vi.fn();
    const vista = (visor: boolean) => <QueryClientProvider client={client}>
      <UserMenu sesion={sesion} />
      {visor && <EvidenceDrawer hallazgoId={1} cola={[]} permiteTriar={false} isUpdating={false} onClose={cerrarVisor} onMove={vi.fn()} onTriage={vi.fn()} onFalsePositive={vi.fn()} />}
    </QueryClientProvider>;
    const { rerender } = render(vista(false));
    await user.click(screen.getByRole("button", { name: /Menú de usuario/ }));
    await user.click(screen.getByRole("button", { name: "Guía rápida" }));
    // Reproduce el montaje que hace popstate al volver a una URL con hallazgo_id.
    rerender(vista(true));
    const cerrarGuia = screen.getByRole("button", { name: "Cerrar guía rápida" });
    expect(cerrarGuia).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Siguiente" })).toHaveFocus();
    await user.tab();
    expect(cerrarGuia).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Primeros pasos en Guardián EPP" })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "H-1" })).toBeVisible();
    expect(cerrarVisor).not.toHaveBeenCalled();
  });
  it("muestra el enlace al manual PDF de GitHub en una pestaña nueva", async () => {
    const user = userEvent.setup();
    render(<UserMenu sesion={sesion} />);
    await user.click(screen.getByRole("button", { name: /Menú de usuario/ }));
    const manual = within(screen.getByRole("region", { name: "Datos del usuario" })).getByRole("link", { name: "Manual de usuario (PDF)" });
    expect(manual).toBeVisible();
    expect(manual).toHaveAttribute("href", "https://github.com/EdgarTolentino/proyecto-capstone-2026/blob/main/Fase%202/Evidencias%20Proyecto/Evidencias%20de%20documentaci%C3%B3n/Manual%20de%20Usuario.pdf");
    expect(manual).toHaveAttribute("target", "_blank");
    expect(manual).toHaveAttribute("rel", "noopener noreferrer");
    await user.tab();
    await user.tab();
    expect(manual).toHaveFocus();
  });

  it("recorre las cuatro tarjetas, vuelve atrás y reinicia después de Finalizar", async () => {
    const user = userEvent.setup();
    render(<UserMenu sesion={sesion} />);
    const abrir = async () => {
      await user.click(screen.getByRole("button", { name: /Menú de usuario/ }));
      await user.click(screen.getByRole("button", { name: "Guía rápida" }));
    };
    await abrir();
    expect(screen.getByText("1 de 4")).toBeVisible();
    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByRole("heading", { name: "Procesa un video" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(screen.getByText("2 de 4")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Revisa los hallazgos" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Anterior" }));
    expect(screen.getByText("1 de 4")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(screen.getByText("3 de 4")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Valida la evidencia" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(screen.getByText("4 de 4")).toBeVisible();
    expect(screen.getByRole("heading", { name: "¿Necesitas ayuda?" })).toBeVisible();
    expect(screen.getByText("Consulta el Manual de usuario (PDF) desde la cabecera. El documento se abre en GitHub y requiere conexión a internet.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Siguiente" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Finalizar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Menú de usuario/ })).toHaveFocus();
    await abrir();
    expect(screen.getByText("1 de 4")).toBeVisible();
  });

  it("abre Guía rápida cuando el ratón no enfoca botones por defecto", async () => {
    const user = userEvent.setup();
    render(<UserMenu sesion={sesion} />);
    const usuario = screen.getByRole("button", { name: /Menú de usuario/ });
    await user.click(usuario);
    const ayuda = screen.getByRole("button", { name: "Guía rápida" });
    // Simula el comportamiento de un navegador que desenfoca el control actual
    // al pulsar otro botón sin darle foco. Un mousedown cancelado evita ese paso.
    if (fireEvent.mouseDown(ayuda)) fireEvent.blur(usuario, { relatedTarget: null });
    fireEvent.mouseUp(ayuda);
    fireEvent.click(ayuda);
    expect(screen.getByRole("dialog", { name: "Primeros pasos en Guardián EPP" })).toBeVisible();
  });

  it("enfoca el botón al abrir con clic aunque el navegador no lo enfoque automáticamente", async () => {
    const user = userEvent.setup();
    render(<UserMenu sesion={sesion} />);
    const boton = screen.getByRole("button", { name: /Menú de usuario/ });
    // fireEvent reproduce un clic que no mueve el foco por defecto.
    fireEvent.click(boton);
    expect(screen.getByRole("region")).toBeVisible();
    expect(boton).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("region")).toBeVisible();
  });

  it("abre con Enter, muestra los datos recibidos y cierra con Escape devolviendo el foco", async () => {
    const user = userEvent.setup();
    render(<UserMenu sesion={sesion} />);
    const boton = screen.getByRole("button", { name: "Menú de usuario: Miguel Ortega" });
    expect(boton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("region", { name: "Datos del usuario" })).not.toBeInTheDocument();
    await user.tab();
    await user.keyboard("{Enter}");
    const panel = screen.getByRole("region", { name: "Datos del usuario" });
    expect(within(panel).getByText("Miguel Ortega")).toBeVisible();
    expect(within(panel).getByText("administrador")).toBeVisible();
    expect(boton).toHaveAttribute("aria-expanded", "true");
    expect(boton).toHaveAttribute("aria-controls", panel.id);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    expect(boton).toHaveAttribute("aria-expanded", "false");
    expect(boton).toHaveFocus();
  });

  it.each(["administrador", "prevencionista", "supervisor", "auditor"] as const)("muestra el rol %s de la sesión", async (rol) => {
    const user = userEvent.setup();
    render(<UserMenu sesion={{ ...sesion, rol }} />);
    await user.click(screen.getByRole("button"));
    expect(within(screen.getByRole("region")).getByText(rol)).toBeVisible();
  });

  it("permite alternar con espacio y cierra al pulsar fuera o mover el foco fuera", async () => {
    const user = userEvent.setup();
    render(<><UserMenu sesion={sesion} /><button>Fuera</button></>);
    const boton = screen.getByRole("button", { name: /Menú de usuario/ });
    await user.tab();
    await user.keyboard(" ");
    expect(screen.getByRole("region")).toBeVisible();
    await user.keyboard(" ");
    expect(boton).toHaveAttribute("aria-expanded", "false");
    await user.click(boton);
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    await user.click(boton);
    await user.tab();
    expect(screen.getByRole("button", { name: "Guía rápida" })).toHaveFocus();
    expect(screen.getByRole("region")).toBeVisible();
    await user.tab();
    expect(screen.getByRole("link", { name: "Manual de usuario (PDF)" })).toHaveFocus();
    expect(screen.getByRole("region")).toBeVisible();
    await user.tab();
    expect(screen.getByRole("button", { name: "Fuera" })).toHaveFocus();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it.each(["Escape", "botón"])("abre Guía rápida sin navegar y cierra con %s", async (cierre) => {
    const user = userEvent.setup();
    const ubicacion = window.location.href;
    render(<UserMenu sesion={sesion} />);
    const boton = screen.getByRole("button", { name: /Menú de usuario/ });
    await user.click(boton);
    await user.tab();
    expect(screen.getByRole("button", { name: "Guía rápida" })).toHaveFocus();
    await user.keyboard("{Enter}");
    const dialogo = screen.getByRole("dialog", { name: "Primeros pasos en Guardián EPP" });
    expect(dialogo).toHaveAttribute("aria-modal", "true");
    expect(within(dialogo).getByRole("heading", { name: "Procesa un video" })).toBeVisible();
    expect(window.location.href).toBe(ubicacion);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    const cerrar = within(dialogo).getByRole("button", { name: "Cerrar guía rápida" });
    expect(cerrar).toHaveFocus();
    await user.tab({ shift: true });
    expect(within(dialogo).getByRole("button", { name: "Siguiente" })).toHaveFocus();
    await user.tab();
    expect(cerrar).toHaveFocus();
    if (cierre === "Escape") await user.keyboard("{Escape}");
    else await user.click(cerrar);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(boton).toHaveFocus();
  });

  it.each([false, true])("muestra el estado real sin sesión (error=%s), sin datos inventados", (sesionError) => {
    render(<UserMenu sesionError={sesionError} />);
    expect(screen.getByRole("status")).toHaveTextContent(sesionError ? "Sesión no disponible" : "Cargando sesión…");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("muestra que el nombre vacío no está disponible", async () => {
    const user = userEvent.setup();
    render(<UserMenu sesion={{ ...sesion, nombre: " " }} />);
    await user.click(screen.getByRole("button", { name: "Menú de usuario: Nombre no disponible" }));
    expect(within(screen.getByRole("region")).getByText("Nombre no disponible")).toBeVisible();
  });

  it("retira los datos del menú si la sesión deja de estar disponible", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<UserMenu sesion={sesion} />);
    await user.click(screen.getByRole("button"));
    expect(screen.getByRole("region")).toBeVisible();
    rerender(<UserMenu sesion={sesion} sesionError />);
    expect(screen.getByRole("status")).toHaveTextContent("Sesión no disponible");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});
