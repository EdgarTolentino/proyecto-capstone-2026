import { useEffect, useState } from "react";

import { obtenerEvidencia } from "../api/client";

// Descargamos la evidencia con autorización y liberamos su URL al cambiar de caso.
export function EvidenceMedia({ url, video = false }: { url?: string | null; video?: boolean }) {
  const [source, setSource] = useState<{ url: string; blob: string }>();
  const [failed, setFailed] = useState<string>();
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    let blobUrl: string | undefined;
    void obtenerEvidencia(url, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        blobUrl = URL.createObjectURL(blob);
        setSource({ url, blob: blobUrl });
      }).catch(() => { if (!controller.signal.aborted) setFailed(url); });
    return () => { controller.abort(); if (blobUrl) URL.revokeObjectURL(blobUrl); };
  }, [url]);
  if (!url || failed === url) return <span>Evidencia no disponible</span>;
  if (source?.url !== url) return <span>Cargando evidencia…</span>;
  return video ? <video src={source.blob} controls loop muted /> : <img src={source.blob} alt="Evidencia anonimizada del hallazgo" />;
}
