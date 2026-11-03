import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { listarHallazgos } from "../api/client";
import type { Hallazgo } from "../api/types";
import { INTERVALO_BANDEJA_MS } from "../api/videos";
import { sinPermiso, textoDeFallo } from "../utils/fallosSala";
import { useEspejoWhep } from "../hooks/useEspejoWhep";
import { formatHora } from "../utils/format";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { SeverityBadge } from "./SeverityBadge";
import { VistaProcesada } from "./VistaProcesada";
import "./SalaEnVivoPage.css";

const HALLAZGOS_RECIENTES = 8;

function CamaraEnVivo() {
  const { estado, videoRef } = useEspejoWhep();
  return (
    <section className="sala-panel" aria-labelledby="sala-camara">
      <h2 id="sala-camara">Cámara en vivo</h2>
      <video ref={videoRef} autoPlay muted playsInline hidden={estado !== "en_vivo"} aria-label="Imagen de la cámara" />
      {estado === "conectando" && <p role="status">Conectando con la cámara…</p>}
      {estado === "apagada" && <p role="status">Cámara apagada</p>}
      <p className="sala-aviso">Sin audio ni grabación. Quien se pare frente a la cámara aparece en pantalla.</p>
    </section>
  );
}

interface RecientesProps {
  recientes: Hallazgo[];
  cargado: boolean;
  fallo: unknown; // el error de la consulta, si lo hay
  onReintentar: () => void;
  onAbrir: (id: number) => void;
}

function HallazgosRecientes({ recientes, cargado, fallo, onReintentar, onAbrir }: RecientesProps) {
  return (
    <section className="sala-panel" aria-labelledby="sala-hallazgos">
      <h2 id="sala-hallazgos">Hallazgos recientes</h2>
      {fallo !== null && <p role="alert">{textoDeFallo(fallo, "hallazgos")}</p>}
      {sinPermiso(fallo) && <button type="button" onClick={onReintentar}>Reintentar</button>}
      {cargado && recientes.length === 0 && <p role="status">Aún no hay hallazgos.</p>}
      <ul className="sala-recientes">
        {recientes.map((h) => (
          <li key={h.id}>
            <button type="button" onClick={() => onAbrir(h.id)}>
              <SeverityBadge severidad={h.severidad} />
              <strong className="mono">H-{h.id}</strong>
              <span>sin {h.epp_faltante.join(" y ")} · {formatHora(h.ts_inicio)}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

// «Sala en vivo»: la cámara, lo que ve el modelo y lo último que encontró, en una sola pantalla. Los
// dos rótulos son obligatorios: la cámara va casi en tiempo real y la vista procesada ~10 s después.
export function SalaEnVivoPage() {
  const [abierto, setAbierto] = useState<number>();
  const pagina = useQuery({
    queryKey: ["hallazgos-sala"],
    queryFn: () => listarHallazgos({ vista: "todos", orden: "ts_inicio_desc" }),
    retry: (intentos, error) => !sinPermiso(error) && intentos < 1,
    refetchInterval: (consulta) => (sinPermiso(consulta.state.error) ? false : INTERVALO_BANDEJA_MS),
  });
  const recientes = (pagina.data?.items ?? []).slice(0, HALLAZGOS_RECIENTES);
  return (
    <main className="sala-page">
      <div className="sala-vistas">
        <CamaraEnVivo />
        <VistaProcesada />
      </div>
      <HallazgosRecientes recientes={recientes} cargado={Boolean(pagina.data)} fallo={pagina.error} onReintentar={() => void pagina.refetch()} onAbrir={setAbierto} />
      {abierto !== undefined && (
        <EvidenceDrawer
          hallazgoId={abierto}
          cola={recientes}
          permiteTriar={false}
          onClose={() => setAbierto(undefined)}
          onMove={setAbierto}
          onTriage={() => undefined}
          onFalsePositive={() => undefined}
          isUpdating={false}
        />
      )}
    </main>
  );
}
