import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, ChevronLeft, ChevronRight, Lock, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { EvidenceMedia } from "./EvidenceMedia";
import { useModalKeyboard } from "../hooks/useModalKeyboard";

import { obtenerHallazgo } from "../api/client";
import type { DecisionTriage, Hallazgo } from "../api/types";
import { formatDuracion, formatHora } from "../utils/format";
import { SeverityBadge } from "./SeverityBadge";

interface EvidenceDrawerProps {
  hallazgoId: number;
  cola: Hallazgo[];
  permiteTriar: boolean;
  onClose: () => void;
  onMove: (id: number) => void;
  onTriage: (decision: DecisionTriage) => void;
  onFalsePositive: () => void;
  isUpdating: boolean;
}

export function EvidenceDrawer(props: EvidenceDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  useModalKeyboard(dialogRef, props.onClose);
  const detalle = useQuery({
    queryKey: ["hallazgo", props.hallazgoId],
    queryFn: () => obtenerHallazgo(props.hallazgoId),
  });
  const indice = props.cola.findIndex((item) => item.id === props.hallazgoId);
  const anterior = props.cola[indice - 1];
  const siguiente = props.cola[indice + 1];

  // Al abrir, llevamos el foco al botón cerrar. Al cerrar, App lo devuelve a la bandeja.
  useEffect(() => closeRef.current?.focus(), []);

  return (
    <>
      <button className="drawer-overlay" type="button" aria-label="Cerrar visor" onClick={props.onClose} />
      <aside ref={dialogRef} className="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <header className="drawer-header">
          {detalle.data && <SeverityBadge severidad={detalle.data.severidad} />}
          <strong id="drawer-title" className="mono">H-{props.hallazgoId}</strong>
          {detalle.data && <span className="drawer-summary">sin {detalle.data.epp_faltante.join(" y ")} · {detalle.data.area?.nombre} / {detalle.data.zona?.nombre} · {formatHora(detalle.data.ts_inicio)} · {formatDuracion(detalle.data.duracion_s)}</span>}
          <div className="drawer-nav">
            <button type="button" disabled={!anterior} onClick={() => anterior && props.onMove(anterior.id)} aria-label="Hallazgo anterior"><ChevronLeft size={17} /></button>
            <button type="button" disabled={!siguiente} onClick={() => siguiente && props.onMove(siguiente.id)} aria-label="Hallazgo siguiente"><ChevronRight size={17} /></button>
            <button ref={closeRef} type="button" onClick={props.onClose} aria-label="Cerrar visor"><X size={18} /></button>
          </div>
        </header>

        <div className="drawer-scroll">
          {detalle.isLoading && <div className="state-message">Cargando evidencia…</div>}
          {detalle.isError && <div className="state-message state-message--error">No fue posible cargar la evidencia.</div>}
          {detalle.data && <EvidenceContent key={detalle.data.id} detalle={detalle.data} />}
        </div>

        {detalle.data && props.permiteTriar && (
          <footer className="drawer-actions">
            <button className="primary-button" type="button" disabled={props.isUpdating} onClick={() => props.onTriage({ estado: "confirmado" })}>Confirmar <kbd>c</kbd></button>
            <button type="button" disabled={props.isUpdating} onClick={props.onFalsePositive}>Falso positivo <kbd>x</kbd></button>
            <button type="button" disabled={props.isUpdating} onClick={() => props.onTriage({ estado: "duplicado", duplicado_de: null })}>Duplicado</button>
            <button type="button" disabled={props.isUpdating} onClick={() => props.onTriage({ estado: "pospuesto", posponer_hasta: null })}>Posponer</button>
            <button type="button" disabled title="El contrato aún no entrega el catálogo de responsables">Asignar…</button>
            <span className="queue-position mono">{indice + 1} de {props.cola.length} en la cola</span>
          </footer>
        )}
      </aside>
    </>
  );
}

function EvidenceContent({ detalle }: { detalle: Awaited<ReturnType<typeof obtenerHallazgo>> }) {
  const [indiceActual, setIndiceActual] = useState(0);
  const evidenciaActual = detalle.evidencias[indiceActual];
  return (
    <div className="evidence-content">
      <section className="evidence-player" aria-label="Recorte de evidencia anonimizado">
        <div className="player-label mono">{detalle.fuente?.nombre} · {formatHora(detalle.ts_inicio)}</div>
        <EvidenceMedia url={detalle.recorte_video_url ?? (evidenciaActual?.anonimizado ? evidenciaActual.url : null)} video={Boolean(detalle.recorte_video_url)} />
      </section>
      <div className="privacy-controls">
        <label><input type="checkbox" checked disabled /> Difuminar rostro <Lock size={12} /> <small>obligatorio por privacidad</small></label>
        <span className="legal-inline"><AlertTriangle size={12} /> {detalle.aviso_legal}</span>
      </div>
      <div className="evidence-strip" aria-label="Cuadros confirmados">
        {detalle.evidencias.slice(0, 6).map((evidencia, indice) => (
          <button onClick={() => setIndiceActual(indice)} className={indice === indiceActual ? "is-current" : ""} type="button" key={evidencia.id} aria-current={indice === indiceActual ? "true" : undefined} aria-label={`Cuadro de evidencia ${indice + 1}`}>
            <EvidenceMedia url={evidencia.anonimizado ? evidencia.url : null} /><span className="mono">{formatHora(evidencia.capture_ts)}</span>
          </button>
        ))}
      </div>

      <section className="timeline-card">
        <p className="section-label">Línea de tiempo del evento</p>
        <div className="timeline-line"><i /><b /><span /></div>
        <div className="timeline-labels mono">
          <span>{detalle.linea_tiempo?.primera_deteccion ? formatHora(detalle.linea_tiempo.primera_deteccion) : "—"} · 1.ª detección</span>
          <strong>{detalle.linea_tiempo?.umbral_alcanzado ? formatHora(detalle.linea_tiempo.umbral_alcanzado) : "—"} · umbral alcanzado</strong>
          <span>{detalle.linea_tiempo?.fin ? formatHora(detalle.linea_tiempo.fin) : "En curso"} · fin</span>
        </div>
      </section>

      {detalle.descripcion_automatica && (
        <section className="automatic-description">
          <p className="section-label">Descripción automática</p>
          <h2>{detalle.descripcion_automatica.titulo}</h2>
          <p>{detalle.descripcion_automatica.descripcion}</p>
          <small className="mono">Confianza de la descripción {detalle.descripcion_automatica.confianza?.toLocaleString("es-CL", { minimumFractionDigits: 2 })}</small>
        </section>
      )}

      <section className="trigger-card">
        <h3>Por qué se disparó</h3>
        <dl>
          <Detail label="Regla" value={`${detalle.por_que_se_disparo.regla_nombre} · versión ${detalle.por_que_se_disparo.regla_version}`} />
          <Detail label="Zona" value={detalle.por_que_se_disparo.zona ?? detalle.zona?.nombre ?? "—"} />
          <Detail label="EPP exigido" value={detalle.por_que_se_disparo.epp_exigido?.join(", ") ?? "—"} />
          <Detail label="Severidad resultante" value={<SeverityBadge severidad={detalle.severidad} />} />
          <Detail label="Umbral configurado" value={detalle.por_que_se_disparo.umbral_configurado} mono />
          <Detail label="Valores observados" value={detalle.por_que_se_disparo.valores_observados} mono />
          <Detail label="Confianza mínima" value={detalle.por_que_se_disparo.confianza_minima?.toLocaleString("es-CL") ?? "—"} mono />
          <Detail label="Base legal" value={detalle.por_que_se_disparo.norma_fundante ?? "—"} />
        </dl>
      </section>

      <details className="technical-details">
        <summary><ChevronDown size={14} /> Metadatos técnicos</summary>
        <dl>
          <Detail label="Archivo" value={detalle.tecnicos.video_archivo ?? "—"} mono />
          <Detail label="Hash" value={detalle.tecnicos.video_hash ?? "—"} mono />
          <Detail label="Segundo del video" value={String(detalle.tecnicos.segundo_en_video ?? "—")} mono />
          <Detail label="Cadencia" value={`${detalle.tecnicos.fps_muestreo ?? "—"} fps`} mono />
          <Detail label="Modelo" value={detalle.tecnicos.modelo_version ?? "—"} mono />
          <Detail label="Track efímero" value={String(detalle.tecnicos.track_id ?? "—")} mono />
        </dl>
      </details>
    </div>
  );
}

function Detail({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return <div><dt>{label}</dt><dd className={mono ? "mono" : ""}>{value}</dd></div>;
}
