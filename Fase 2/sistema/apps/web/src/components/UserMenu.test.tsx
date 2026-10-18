import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import type { Sesion } from "../api/types";
import { UserMenu } from "./UserMenu";

const sesion: Sesion = { id: 0, nombre: "Miguel Ortega", rol: "administrador", permisos: [] };
afterEach(cleanup);

describe("Menú de usuario", () => {
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
    expect(screen.getByRole("button", { name: "Ayuda" })).toHaveFocus();
    expect(screen.getByRole("region")).toBeVisible();
    await user.tab();
    expect(screen.getByRole("button", { name: "Fuera" })).toHaveFocus();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it.each(["Escape", "botón"])("abre el popup de Ayuda sin navegar y cierra con %s", async (cierre) => {
    const user = userEvent.setup();
    const ubicacion = window.location.href;
    render(<UserMenu sesion={sesion} />);
    const boton = screen.getByRole("button", { name: /Menú de usuario/ });
    await user.click(boton);
    await user.tab();
    expect(screen.getByRole("button", { name: "Ayuda" })).toHaveFocus();
    await user.keyboard("{Enter}");
    const dialogo = screen.getByRole("dialog", { name: "Ayuda" });
    expect(dialogo).toHaveAttribute("aria-modal", "true");
    expect(within(dialogo).getByText("Llámanos al +56 9 XXXX XXXX. Estamos las 24 horas para ayudarte.")).toBeVisible();
    expect(within(dialogo).getByText("Mensaje de demostración · Número ficticio.")).toBeVisible();
    expect(window.location.href).toBe(ubicacion);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    const cerrar = within(dialogo).getByRole("button", { name: "Cerrar ayuda" });
    expect(cerrar).toHaveFocus();
    await user.tab();
    expect(cerrar).toHaveFocus();
    await user.tab({ shift: true });
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
