import { useEffect, useId, useRef, useState } from "react";

import { HelpDialog } from "./HelpDialog";

export function HelpMenu() {
  const [abierto, setAbierto] = useState(false);
  const [guia, setGuia] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!abierto) return;
    const cerrarFuera = (event: PointerEvent) => {
      if (event.target instanceof Node && !contenedor.current?.contains(event.target)) setAbierto(false);
    };
    document.addEventListener("pointerdown", cerrarFuera);
    return () => document.removeEventListener("pointerdown", cerrarFuera);
  }, [abierto]);

  return <><div className="help-menu" ref={contenedor} onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setAbierto(false);
  }} onKeyDown={(event) => {
    if (event.key === "Escape" && abierto) {
      setAbierto(false);
      boton.current?.focus();
    }
  }}>
    <button ref={boton} type="button" className="help-menu__trigger" aria-label="Ayuda" title="Ayuda" aria-expanded={abierto} aria-controls={panelId} onClick={(event) => {
      event.currentTarget.focus();
      setAbierto(!abierto);
    }}>?</button>
    {abierto && <section id={panelId} className="user-menu__panel" aria-label="Opciones de ayuda">
      <a className="user-menu__help" href="https://github.com/EdgarTolentino/proyecto-capstone-2026/blob/main/Fase%202/Evidencias%20Proyecto/Evidencias%20de%20documentaci%C3%B3n/Manual%20de%20Usuario.pdf" target="_blank" rel="noopener noreferrer">Manual de usuario</a>
      <button type="button" className="user-menu__help" onMouseDown={(event) => {
        event.preventDefault();
        event.currentTarget.focus();
      }} onClick={() => {
        setAbierto(false);
        setGuia(true);
      }}>Guía rápida</button>
    </section>}
  </div>
    {guia && <HelpDialog onClose={() => {
      setGuia(false);
      boton.current?.focus();
    }} />}
  </>;
}
