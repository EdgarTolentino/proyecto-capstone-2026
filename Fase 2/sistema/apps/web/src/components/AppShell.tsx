import {
  BarChart3,
  CircleDot,
  FileVideo,
  HardHat,
  Map,
  Radio,
  SearchCheck,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";

import type { Catalogos, EstadoSistema, Sesion } from "../api/types";
import type { SeccionApp } from "../hooks/useAppNavigation";

interface AppShellProps {
  children: ReactNode;
  catalogos?: Catalogos;
  estado?: EstadoSistema;
  sesion?: Sesion;
  sesionError?: boolean;
  seccion: SeccionApp;
  onNavigate: (seccion: SeccionApp) => void;
}

const navegacion = [
  { texto: "Panel general", icono: BarChart3, seccion: "panel" },
  { texto: "Hallazgos", icono: SearchCheck, seccion: "hallazgos" },
  { texto: "Videos", icono: FileVideo, seccion: "videos" },
  { texto: "Reglas", icono: Settings2, seccion: "reglas" },
  { texto: "Reportes", icono: CircleDot },
  { texto: "Zonas y cámaras", icono: Map },
] satisfies { texto: string; icono: typeof BarChart3; seccion?: SeccionApp }[];

export function AppShell({ children, catalogos, estado, sesion, sesionError = false, seccion, onNavigate }: AppShellProps) {
  const obra = catalogos?.obras?.[0]?.nombre ?? "Sin obra seleccionada";
  const ingestaActiva = estado?.ingesta?.activa ?? false;
  const nombre = sesion?.nombre ?? (sesionError ? "Sesión no disponible" : "Cargando sesión…");

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="brand">
          <span className="brand__mark"><ShieldCheck size={25} /></span>
          <div><strong>Guardián<span> EPP</span></strong><small>SEGURIDAD OPERACIONAL</small></div>
        </div>
        <div className="site-header__context"><HardHat size={18} /><span>Centro de control <strong>Operaciones</strong></span></div>
        <div className="user-profile">
          <span className="user-avatar" aria-hidden="true">{sesion?.nombre?.slice(0, 1).toUpperCase() ?? "—"}</span>
          <div><small>Sesión de trabajo</small><span>{nombre}</span></div>
        </div>
      </header>
      <nav className="operations-nav" aria-label="Navegación principal">
        {navegacion.map(({ texto, icono: Icono, seccion: destino }) => {
          const activo = destino === seccion;
          return (
          <button key={texto} className={`nav-item ${activo ? "nav-item--active" : ""}`} type="button" disabled={!destino} aria-current={activo ? "page" : undefined} title={!destino ? "Módulo próximamente disponible" : undefined} onClick={() => destino && onNavigate(destino)}>
            <Icono size={17} aria-hidden="true" /><span>{texto}</span>
            {destino === "hallazgos" && <span className="nav-count">{estado?.pendientes_por_revisar ?? "—"}</span>}
          </button>
          );
        })}
      </nav>
      <section className="workspace">
        <header className="operations-hero">
          <div className="hero-copy">
            <p className="eyebrow"><span />PREVENCIÓN EN TERRENO</p>
            <h1>Cada hallazgo cuenta.<br /><span>La seguridad, primero.</span></h1>
            <p>Revisa la evidencia, valida los riesgos y actúa con información.</p>
          </div>
          <div className="operation-context">
            <div className="operation-context__title"><Map size={18} /><span>OPERACIÓN ACTUAL</span></div>
            <strong>{obra}</strong>
            <div className={`ingestion ${ingestaActiva ? "ingestion--active" : ""}`} role="status">
              <Radio size={15} />{estado ? (ingestaActiva ? "Ingesta activa" : "Ingesta detenida") : "Consultando estado…"}
              {estado?.ingesta?.en_proceso ? ` · ${estado.ingesta.en_proceso} en proceso` : ""}
            </div>
          </div>
        </header>
        {children}
        <footer className="workspace-footer"><span>GUARDIÁN EPP <i>/</i> VALIDACIÓN HUMANA · PREVENCIÓN CONTINUA</span><span>Proyecto académico · Datos de demostración</span></footer>
      </section>
    </div>
  );
}
