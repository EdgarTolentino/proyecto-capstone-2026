import { ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import type { Sesion } from "../api/types";
import { AccountHelpDialog } from "./AccountHelpDialog";

interface UserMenuProps {
  sesion?: Sesion;
  sesionError?: boolean;
}

export function UserMenu({ sesion, sesionError = false }: UserMenuProps) {
  if (!sesion || sesionError) {
    return <div className="user-profile" role="status">{sesionError ? "Sesión no disponible" : "Cargando sesión…"}</div>;
  }
  return <UserMenuSesion key={sesion.id} sesion={sesion} />;
}

function UserMenuSesion({ sesion }: { sesion: Sesion }) {
  const [abierto, setAbierto] = useState(false);
  const [soporte, setSoporte] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const nombre = sesion?.nombre?.trim() || "Nombre no disponible";
  const rol = sesion?.rol || "Rol no disponible";

  useEffect(() => {
    if (!abierto) return;
    const cerrarFuera = (event: PointerEvent) => {
      if (event.target instanceof Node && !contenedor.current?.contains(event.target)) {
        setAbierto(false);
      }
    };
    document.addEventListener("pointerdown", cerrarFuera);
    return () => document.removeEventListener("pointerdown", cerrarFuera);
  }, [abierto]);

  return <><div className="user-profile" ref={contenedor} onKeyDown={(event) => {
    if (event.key === "Escape" && abierto) {
      setAbierto(false);
      boton.current?.focus();
    }
  }} onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setAbierto(false);
  }}>
    <button ref={boton} type="button" className="user-menu__trigger" aria-expanded={abierto} aria-controls={panelId} aria-label={`Menú de usuario: ${nombre}`} onClick={(event) => {
      event.currentTarget.focus();
      setAbierto(!abierto);
    }}>
      <span className="user-avatar" aria-hidden="true">{nombre.slice(0, 1).toUpperCase()}</span>
      <span className="user-menu__summary"><small>Sesión de trabajo</small><span>{nombre}</span></span>
      <ChevronDown size={16} aria-hidden="true" />
    </button>
    {abierto && <section id={panelId} className="user-menu__panel" aria-label="Datos del usuario">
      <strong>{nombre}</strong>
      <p><span>Rol: </span><span>{rol}</span></p>
      <button type="button" className="user-menu__help" onMouseDown={(event) => {
        event.preventDefault();
        event.currentTarget.focus();
      }} onClick={() => {
        setAbierto(false);
        setSoporte(true);
      }}>Problemas con tu cuenta</button>
    </section>}
  </div>
    {soporte && <AccountHelpDialog volverA={boton} onClose={() => setSoporte(false)} />}
  </>;
}
