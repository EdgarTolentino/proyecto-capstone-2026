import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import type { Sesion } from "../api/types";
import { HelpMenu } from "./HelpMenu";
import { UserMenu } from "./UserMenu";

const sesion: Sesion = { id: 0, nombre: "Miguel", rol: "auditor", permisos: [] };
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const cabecera = (activa: boolean, error = false) => <><UserMenu sesion={activa ? sesion : undefined} sesionError={error} /><HelpMenu /></>;
async function abrir(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /Menú de usuario/ }));
  await user.click(screen.getByRole("button", { name: "Problemas con tu cuenta" }));
  return screen.getByRole("dialog", { name: "Problemas con tu cuenta" });
}

it("muestra el formulario visual con datos vacíos o escritos sin enviar solicitudes", async () => {
  const user = userEvent.setup();
  const fetch = vi.spyOn(globalThis, "fetch");
  render(cabecera(true));
  const dialogo = await abrir(user);
  expect(dialogo).toHaveAttribute("aria-modal", "true");
  expect(screen.getByLabelText("Destinatario provisional")).toHaveValue("epp@soporte.cl");
  expect(screen.getByLabelText("Destinatario provisional")).toHaveAttribute("readonly");
  const asunto = screen.getByRole("textbox", { name: "Asunto" });
  const problema = screen.getByRole("textbox", { name: "Describe tu problema" });
  expect(asunto).toHaveValue("");
  expect(problema).toHaveValue("");
  const enviar = screen.getByRole("button", { name: "Enviar solicitud" });
  expect(enviar).toBeDisabled();
  expect(enviar).toHaveAccessibleDescription("El envío de solicitudes estará disponible próximamente");
  for (const texto of [" ", "No puedo acceder"]) {
    await user.clear(asunto);
    await user.type(asunto, texto);
    await user.keyboard("{Enter}");
    await user.clear(problema);
    await user.type(problema, texto);
    expect(enviar).toBeDisabled();
    await user.click(enviar);
    expect(fireEvent.submit(screen.getByRole("form", { name: "Contacto con soporte" }))).toBe(false);
  }
  expect(fetch).not.toHaveBeenCalled();
  expect(dialogo).toBeVisible();
});

it.each(["Escape", "botón"])("mantiene el foco dentro del modal y lo devuelve al cerrar con %s", async (cierre) => {
  const user = userEvent.setup();
  render(cabecera(true));
  await abrir(user);
  const cerrar = screen.getByRole("button", { name: "Cerrar problemas con tu cuenta" });
  expect(cerrar).toHaveFocus();
  await user.tab({ shift: true });
  expect(screen.getByText("¿Qué hago si no puedo acceder?")).toHaveFocus();
  await user.tab();
  expect(cerrar).toHaveFocus();
  await user.tab();
  expect(screen.getByLabelText("Destinatario provisional")).toHaveFocus();
  if (cierre === "Escape") await user.keyboard("{Escape}");
  else await user.click(cerrar);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Menú de usuario/ })).toHaveFocus();
});

it.each([false, true])("retira acceso, modal y borrador al perder la sesión (error=%s)", async (error) => {
  const user = userEvent.setup();
  const { rerender } = render(cabecera(true));
  await abrir(user);
  await user.type(screen.getByLabelText("Asunto"), "Consulta privada");
  rerender(cabecera(error, error));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Menú de usuario|Problemas con tu cuenta/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Ayuda" })).toHaveFocus();
  rerender(cabecera(true));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await abrir(user);
  expect(screen.getByLabelText("Asunto")).toHaveValue("");
});

it("cierra el modal al cambiar de cuenta aunque ambas tengan sesión", async () => {
  const user = userEvent.setup();
  const { rerender } = render(<UserMenu sesion={sesion} />);
  await abrir(user);
  rerender(<UserMenu sesion={{ ...sesion, id: 1 }} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it.each(["¿Cómo recupero mi contraseña?", "¿Cómo actualizo mi perfil?", "¿Qué hago si no puedo acceder?"])("despliega y repliega la pregunta %s", async (pregunta) => {
  const user = userEvent.setup();
  render(cabecera(true));
  await abrir(user);
  const resumen = within(screen.getByRole("region", { name: "Preguntas frecuentes sobre tu cuenta" })).getByText(pregunta);
  const detalle = resumen.closest("details")!;
  expect(detalle).not.toHaveAttribute("open");
  await user.click(resumen);
  expect(detalle).toHaveAttribute("open");
  expect(detalle.querySelector("p")).toBeVisible();
  await user.click(resumen);
  expect(detalle).not.toHaveAttribute("open");
});
