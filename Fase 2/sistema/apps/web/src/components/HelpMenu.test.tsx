import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { AppShell } from "./AppShell";
import { HelpMenu } from "./HelpMenu";

afterEach(cleanup);

describe("Ayuda global", () => {
  it.each(["panel", "hallazgos", "videos", "reglas"] as const)("mantiene Ayuda en %s con sesión, sin sesión y con error", async (seccion) => {
    const user = userEvent.setup();
    for (const props of [{ sesion: { id: 0, nombre: "", rol: "auditor" as const, permisos: [] } }, {}, { sesionError: true }]) {
      const { unmount } = render(<AppShell {...props} seccion={seccion} onNavigate={() => {}}><main /></AppShell>);
      const boton = screen.getByRole("button", { name: "Ayuda" });
      expect(boton).toBeVisible();
      expect(boton).toHaveTextContent("?");
      expect(boton).toHaveAttribute("title", "Ayuda");
      await user.click(boton);
      expect(screen.getAllByRole("link", { name: "Manual de usuario" })).toHaveLength(1);
      expect(screen.getAllByRole("button", { name: "Guía rápida" })).toHaveLength(1);
      unmount();
    }
  });

  it("alterna con Enter y espacio, cierra con Escape, al salir con Tab y al pulsar fuera", async () => {
    const user = userEvent.setup();
    render(<><HelpMenu /><button>Fuera</button></>);
    const boton = screen.getByRole("button", { name: "Ayuda" });
    await user.tab();
    await user.keyboard("{Enter}");
    const panel = screen.getByRole("region");
    expect(boton).toHaveAttribute("aria-expanded", "true");
    expect(boton).toHaveAttribute("aria-controls", panel.id);
    await user.keyboard(" ");
    expect(boton).toHaveAttribute("aria-expanded", "false");
    await user.keyboard(" ");
    await user.tab();
    expect(screen.getByRole("link")).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(boton).toHaveFocus();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    await user.click(boton);
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Guía rápida" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Fuera" })).toHaveFocus();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    await user.click(boton);
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("muestra el enlace al manual PDF de GitHub en una pestaña nueva", async () => {
    const user = userEvent.setup();
    render(<HelpMenu />);
    await user.click(screen.getByRole("button", { name: "Ayuda" }));
    const manual = within(screen.getByRole("region", { name: "Opciones de ayuda" })).getByRole("link", { name: "Manual de usuario" });
    expect(manual).toBeVisible();
    expect(manual).toHaveAttribute("href", "https://github.com/EdgarTolentino/proyecto-capstone-2026/blob/main/Fase%202/Evidencias%20Proyecto/Evidencias%20de%20documentaci%C3%B3n/Manual%20de%20Usuario.pdf");
    expect(manual).toHaveAttribute("target", "_blank");
    expect(manual).toHaveAttribute("rel", "noopener noreferrer");
    await user.tab();
    expect(manual).toHaveFocus();
  });

  it("recorre las cuatro tarjetas, vuelve atrás y reinicia después de Finalizar", async () => {
    const user = userEvent.setup();
    render(<HelpMenu />);
    const abrir = async () => {
      await user.click(screen.getByRole("button", { name: "Ayuda" }));
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
    expect(screen.getByText("Llámanos al +56 9 XXXX XXXX. Estamos las 24 horas para ayudarte.")).toBeVisible();
    expect(screen.getByText("Mensaje de demostración · Número ficticio.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Siguiente" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Finalizar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ayuda" })).toHaveFocus();
    await abrir();
    expect(screen.getByText("1 de 4")).toBeVisible();
  });

  it("abre Guía rápida cuando el ratón no enfoca botones por defecto", async () => {
    const user = userEvent.setup();
    render(<HelpMenu />);
    const usuario = screen.getByRole("button", { name: "Ayuda" });
    await user.click(usuario);
    const ayuda = screen.getByRole("button", { name: "Guía rápida" });
    // Simula el comportamiento de un navegador que desenfoca el control actual
    // al pulsar otro botón sin darle foco. Un mousedown cancelado evita ese paso.
    if (fireEvent.mouseDown(ayuda)) fireEvent.blur(usuario, { relatedTarget: null });
    fireEvent.mouseUp(ayuda);
    fireEvent.click(ayuda);
    expect(screen.getByRole("dialog", { name: "Primeros pasos en Guardián EPP" })).toBeVisible();
  });

  it.each(["Escape", "botón"])("abre Guía rápida sin navegar y cierra con %s", async (cierre) => {
    const user = userEvent.setup();
    const ubicacion = window.location.href;
    render(<HelpMenu />);
    const boton = screen.getByRole("button", { name: "Ayuda" });
    await user.click(boton);
    await user.tab();
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
});
