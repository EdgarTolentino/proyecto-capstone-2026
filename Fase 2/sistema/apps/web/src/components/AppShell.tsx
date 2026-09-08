import {
  BarChart3,
  Bell,
  ChevronDown,
  CircleDot,
  FileVideo,
  Map,
  PanelLeft,
  SearchCheck,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";

import type { Catalogos, EstadoSistema, Sesion } from "../api/types";

interface AppShellProps {
  children: ReactNode;
  catalogos?: Catalogos;
  estado?: EstadoSistema;
  sesion?: Sesion;
  sesionError?: boolean;
}

const navegacion = [
  { texto: "Panel general", icono: BarChart3 },
  { texto: "Hallazgos", icono: SearchCheck, activo: true },
  { texto: "Videos", icono: FileVideo },
  { texto: "Reglas", icono: Settings2, separador: "Configuración" },
  { texto: "Reportes", icono: CircleDot },
  { texto: "Zonas y cámaras", icono: Map },
  { texto: "Notificaciones", icono: Bell },
];

export function AppShell({ children, catalogos, estado, sesion, sesionError = false }: AppShellProps) {
  const obra = catalogos?.obras?.[0]?.nombre ?? "Sin obra seleccionada";
  const ingestaActiva = estado?.ingesta.activa ?? false;

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Navegación principal">
        <div className="brand">
          <span className="brand__mark"><ShieldCheck size={16} /></span>
          <strong>Guardián EPP</strong>
        </div>
        <nav>
          <p className="nav-section">Operación</p>
          {navegacion.map(({ texto, icono: Icono, activo, separador }) => (
            <div key={texto}>
              {separador && <p className="nav-section">{separador}</p>}
              <button className={`nav-item ${activo ? "nav-item--active" : ""}`} type="button">
                <Icono size={15} aria-hidden="true" />
                <span>{texto}</span>
                {activo && <span className="nav-count">{estado?.pendientes_por_revisar ?? "—"}</span>}
              </button>
            </div>
          ))}
        </nav>
        <div className="severity-key" aria-label="Leyenda de severidad">
          <p className="nav-section">Severidad</p>
          <span className="severity severity--critica"><i>◆</i> Crítica</span>
          <span className="severity severity--alta"><i>▲</i> Alta</span>
          <span className="severity severity--media"><i>●</i> Media</span>
          <span className="severity severity--baja"><i>○</i> Baja</span>
        </div>
      </aside>

      <section className="workspace">
        <header className="global-header">
          <button className="sidebar-toggle" type="button" aria-label="Contraer navegación">
            <PanelLeft size={16} />
          </button>
          <button className="header-select" type="button">
            <span>Obra</span><strong>{obra}</strong><ChevronDown size={13} />
          </button>
          <div className="header-spacer" />
          <div className={`ingestion ${ingestaActiva ? "ingestion--active" : ""}`}>
            <span aria-hidden="true" />
            {ingestaActiva ? "Ingesta activa" : "Ingesta detenida"}
            {estado?.ingesta.en_proceso ? ` · ${estado.ingesta.en_proceso} en proceso` : ""}
          </div>
          <div className="user-name">{sesion?.nombre ?? (sesionError ? "Sesión no disponible" : "Cargando sesión…")}</div>
        </header>
        {children}
      </section>
    </div>
  );
}
