import { LoaderCircle, X } from "lucide-react";
import { useState } from "react";

import type { Catalogos, Regla, ReglaEntrada, ResultadoSimulacion, TipoEpp } from "../api/types";

interface ReglaEditorProps {
  catalogos?: Catalogos;
  regla?: Regla;
  guardando: boolean;
  error?: string;
  simulando: boolean;
  resultadoSimulacion?: ResultadoSimulacion;
  errorSimulacion?: string;
  onCancel: () => void;
  onSubmit: (entrada: ReglaEntrada) => void;
  onSimular: (simulacion: { desde: string; hasta: string; regla: ReglaEntrada }) => void;
}

const eppPredeterminado: TipoEpp[] = ["casco", "chaleco", "lentes", "guantes", "arnes", "calzado"];

function valoresIniciales(regla?: Regla): ReglaEntrada {
  return {
    nombre: regla?.nombre ?? "", area_id: regla?.area_id ?? 0, zona_ids: regla?.zona_ids ?? [], epp_exigido: regla?.epp_exigido ?? [],
    confirmacion_segundos: regla?.confirmacion_segundos ?? 2, cierre_segundos: regla?.cierre_segundos ?? 3, confianza_minima: regla?.confianza_minima ?? 0.45,
    severidad: regla?.severidad ?? 2, turno: regla?.turno ?? null, hora_desde: regla?.hora_desde ?? null, hora_hasta: regla?.hora_hasta ?? null,
    activa: regla?.activa ?? true, base_licitud: regla?.base_licitud ?? "obligacion_legal", norma_fundante: regla?.norma_fundante ?? "",
    finalidad_declarada: regla?.finalidad_declarada ?? "", retencion_dias: regla?.retencion_dias ?? 30, destinatarios: regla?.destinatarios ?? [], espera_entre_alertas_s: regla?.espera_entre_alertas_s ?? 900,
  };
}

function fechaIso(fecha: Date) { return fecha.toISOString().slice(0, 10); }

export function ReglaEditor({ catalogos, regla, guardando, error, simulando, resultadoSimulacion, errorSimulacion, onCancel, onSubmit, onSimular }: ReglaEditorProps) {
  const [entrada, setEntrada] = useState<ReglaEntrada>(() => valoresIniciales(regla));
  const hoy = new Date();
  const haceTreintaDias = new Date(hoy);
  haceTreintaDias.setDate(hoy.getDate() - 30);
  const [desde, setDesde] = useState(fechaIso(haceTreintaDias));
  const [hasta, setHasta] = useState(fechaIso(hoy));
  const eppDisponibles = catalogos?.epp?.length ? catalogos.epp : eppPredeterminado;
  const actualizar = <K extends keyof ReglaEntrada>(campo: K, valor: ReglaEntrada[K]) => setEntrada((actual) => ({ ...actual, [campo]: valor }));
  const alternarEpp = (epp: TipoEpp) => actualizar("epp_exigido", entrada.epp_exigido.includes(epp) ? entrada.epp_exigido.filter((actual) => actual !== epp) : [...entrada.epp_exigido, epp]);

  return <section className="rule-editor" aria-labelledby="rule-editor-title">
    <header className="rule-editor__header"><div><p className="eyebrow">{regla ? `VERSIÓN ACTUAL ${regla.version}` : "NUEVA CONFIGURACIÓN"}</p><h3 id="rule-editor-title">{regla ? "Editar regla" : "Crear regla"}</h3></div><button type="button" className="icon-button" aria-label="Cerrar editor" onClick={onCancel}><X size={18} /></button></header>
    <form onSubmit={(event) => { event.preventDefault(); onSubmit(entrada); }}><div className="rule-editor__grid">
      <label className="rule-field rule-field--wide"><span>Nombre</span><input required value={entrada.nombre} onChange={(event) => actualizar("nombre", event.target.value)} /></label>
      <label className="rule-field"><span>Área</span><select required value={entrada.area_id || ""} onChange={(event) => actualizar("area_id", Number(event.target.value))}><option value="" disabled>Selecciona un área</option>{catalogos?.areas?.map((area) => area && <option key={area.id} value={area.id}>{area.nombre}</option>)}</select></label>
      <label className="rule-field"><span>Zona <small>Opcional</small></span><select value={entrada.zona_ids?.[0] ?? ""} onChange={(event) => actualizar("zona_ids", event.target.value ? [Number(event.target.value)] : [])}><option value="">Todas las zonas</option>{catalogos?.zonas?.map((zona) => zona && <option key={zona.id} value={zona.id}>{zona.nombre}</option>)}</select></label>
      <fieldset className="rule-field rule-field--wide"><legend>EPP exigido</legend><div className="rule-epp-options">{eppDisponibles.map((epp) => <label key={epp}><input type="checkbox" checked={entrada.epp_exigido.includes(epp)} onChange={() => alternarEpp(epp)} />{epp}</label>)}</div></fieldset>
      <label className="rule-field"><span>Confirmación (segundos)</span><input required min="0.2" step="0.1" type="number" value={entrada.confirmacion_segundos} onChange={(event) => actualizar("confirmacion_segundos", Number(event.target.value))} /><small>Tiempo continuo antes de generar el hallazgo.</small></label>
      <label className="rule-field"><span>Severidad</span><select value={entrada.severidad} onChange={(event) => actualizar("severidad", Number(event.target.value) as ReglaEntrada["severidad"])}><option value="1">Baja</option><option value="2">Media</option><option value="3">Alta</option><option value="4">Crítica</option></select></label>
      <label className="rule-field"><span>Turno <small>Opcional</small></span><select value={entrada.turno ?? ""} onChange={(event) => actualizar("turno", event.target.value || null)}><option value="">Todos los turnos</option>{catalogos?.turnos?.map((turno) => turno && <option key={turno.codigo} value={turno.codigo}>{turno.etiqueta}</option>)}</select></label>
      <label className="rule-field"><span>Desde <small>Opcional</small></span><input type="time" value={entrada.hora_desde ?? ""} onChange={(event) => actualizar("hora_desde", event.target.value || null)} /></label>
      <label className="rule-field"><span>Hasta <small>Opcional</small></span><input type="time" value={entrada.hora_hasta ?? ""} onChange={(event) => actualizar("hora_hasta", event.target.value || null)} /></label>
      <label className="rule-field rule-field--wide"><span>Finalidad declarada</span><input required value={entrada.finalidad_declarada} onChange={(event) => actualizar("finalidad_declarada", event.target.value)} placeholder="Ej.: Prevención de lesiones" /></label>
    </div>{error && <p className="rule-editor__error" role="alert">{error}</p>}
      {regla ? <section className="rule-simulator" aria-labelledby="rule-simulator-title"><div><p className="eyebrow">¿Y SI…?</p><h4 id="rule-simulator-title">Simular sobre el histórico</h4><p>Prueba los cambios actuales sin guardar una nueva versión.</p></div><div className="rule-simulator__period"><label>Desde simulación<input type="date" value={desde} max={hasta} onChange={(event) => setDesde(event.target.value)} /></label><label>Hasta simulación<input type="date" value={hasta} min={desde} onChange={(event) => setHasta(event.target.value)} /></label><button type="button" disabled={simulando || entrada.epp_exigido.length === 0 || !desde || !hasta} onClick={() => onSimular({ desde, hasta, regla: entrada })}>{simulando && <LoaderCircle className="spin" size={15} />}Simular sobre últimos 30 días</button></div>{errorSimulacion && <p className="rule-editor__error" role="alert">{errorSimulacion}</p>}{resultadoSimulacion && <div className="simulation-result" role="status"><strong>Habría generado {resultadoSimulacion.hallazgos_estimados} hallazgos.</strong>{resultadoSimulacion.contra_version_vigente?.variacion !== undefined && <span>Variación frente a la versión vigente: {resultadoSimulacion.contra_version_vigente.variacion >= 0 ? "+" : ""}{resultadoSimulacion.contra_version_vigente.variacion}.</span>}{resultadoSimulacion.alertas_por_turno_estimadas !== undefined && <span>{resultadoSimulacion.alertas_por_turno_estimadas} alertas estimadas por turno.</span>}</div>}</section> : <p className="rule-simulator__hint">Guarda la regla para poder simularla sobre el histórico.</p>}
      <footer className="rule-editor__actions"><button type="button" onClick={onCancel}>Cancelar</button><button type="submit" className="primary-button" disabled={guardando || entrada.epp_exigido.length === 0}>{guardando && <LoaderCircle className="spin" size={15} />}{regla ? "Guardar nueva versión" : "Crear regla"}</button></footer></form>
  </section>;
}
