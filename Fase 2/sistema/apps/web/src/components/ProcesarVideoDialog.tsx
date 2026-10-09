import { useQuery } from "@tanstack/react-query";
import { LoaderCircle, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { listarEntradaVideos } from "../api/client";
import type { PedidoNuevo } from "../api/types";
import { mensajeDeEntrada } from "../api/videos";
import { useModalKeyboard } from "../hooks/useModalKeyboard";
import { formatearBytes } from "../utils/format";

export interface FuenteElegible {
  id: number;
  nombre: string;
}

interface ProcesarVideoDialogProps {
  // `undefined` mientras los catálogos cargan.
  fuentes: FuenteElegible[] | undefined;
  fuentesError: boolean;
  enviando: boolean;
  error: string;
  onCancel: () => void;
  onConfirm: (peticion: PedidoNuevo) => void;
}

export function ProcesarVideoDialog({ fuentes, fuentesError, enviando, error, onCancel, onConfirm }: ProcesarVideoDialogProps) {
  const [archivo, setArchivo] = useState("");
  const [fuenteId, setFuenteId] = useState("");
  const dialogRef = useRef<HTMLElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  useModalKeyboard(dialogRef, onCancel);
  // Sin reintentos automáticos ni caché: cada vez que se abre, la carpeta se lee de nuevo.
  const entrada = useQuery({ queryKey: ["videos-entrada"], queryFn: listarEntradaVideos, retry: false, gcTime: 0 });

  useEffect(() => {
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.focus();
    return () => {
      if (openerRef.current?.isConnected) openerRef.current.focus();
    };
  }, []);

  const archivos = entrada.data?.items ?? [];
  // Un archivo que desapareció de la carpeta al refrescar no puede seguir seleccionado.
  const elegido = archivos.find((item) => item.archivo === archivo);
  const puedeEnviar = Boolean(elegido && fuenteId) && !enviando;

  return (
    <div className="modal-layer" role="presentation">
      <section
        ref={dialogRef}
        className="reason-dialog process-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="process-title"
        tabIndex={-1}
      >
        <header>
          <h2 id="process-title">Procesar video</h2>
          <button type="button" onClick={onCancel} aria-label="Cerrar"><X size={17} /></button>
        </header>
        <p>Elige un archivo de la carpeta de entrada del servidor y la cámara que lo grabó. No se sube nada desde el navegador.</p>

        <fieldset className="process-files" aria-busy={entrada.isLoading}>
          <legend>Archivo</legend>
          {entrada.isLoading && (
            <div className="state-message" role="status" aria-live="polite">
              <LoaderCircle className="spin" aria-hidden="true" /> Cargando archivos…
            </div>
          )}
          {entrada.isError && (
            <div className="state-message state-message--error" role="alert">
              {mensajeDeEntrada(entrada.error)}
              <button type="button" onClick={() => void entrada.refetch()}>Reintentar</button>
            </div>
          )}
          {entrada.isSuccess && archivos.length === 0 && (
            <div className="state-message" role="status">No hay archivos en la carpeta de entrada.</div>
          )}
          {archivos.map((item) => (
            <label key={item.archivo} className="process-file">
              <input
                type="radio"
                name="archivo-entrada"
                value={item.archivo}
                checked={archivo === item.archivo}
                onChange={() => setArchivo(item.archivo)}
              />
              <span className="mono process-file__name">{item.archivo}</span>
              <span className="process-file__size">{formatearBytes(item.bytes)}</span>
              {item.posible_duplicado && <span className="process-file__dup">Posible duplicado</span>}
            </label>
          ))}
        </fieldset>
        {elegido?.posible_duplicado && (
          <p className="process-hint">
            Hay un video registrado con el mismo nombre y tamaño. El servidor lo decide por su contenido: si es el mismo, el pedido se rechaza.
          </p>
        )}

        <label className="process-camera">
          Cámara
          <select value={fuenteId} onChange={(event) => setFuenteId(event.target.value)} disabled={!fuentes?.length}>
            <option value="">{fuentes === undefined && !fuentesError ? "Cargando cámaras…" : "Elige una cámara"}</option>
            {fuentes?.map((fuente) => <option key={fuente.id} value={fuente.id}>{fuente.nombre}</option>)}
          </select>
        </label>
        {fuentesError && <div className="process-alert" role="alert">No fue posible cargar las cámaras. Recarga la página.</div>}
        {!fuentesError && fuentes?.length === 0 && <div className="process-alert" role="alert">No hay cámaras configuradas.</div>}

        {error && <div className="process-alert" role="alert">{error}</div>}

        <footer>
          <button type="button" onClick={onCancel}>Cancelar</button>
          <button
            className="primary-button"
            type="button"
            disabled={!puedeEnviar}
            onClick={() => elegido && onConfirm({ archivo: elegido.archivo, fuente_id: Number(fuenteId) })}
          >
            {enviando ? "Enviando…" : "Procesar"}
          </button>
        </footer>
      </section>
    </div>
  );
}
