import type { Severidad } from "../api/types";

const severidades = {
  4: { nombre: "Crítica", forma: "◆", clase: "critica" },
  3: { nombre: "Alta", forma: "▲", clase: "alta" },
  2: { nombre: "Media", forma: "●", clase: "media" },
  1: { nombre: "Baja", forma: "○", clase: "baja" },
} satisfies Record<Severidad, { nombre: string; forma: string; clase: string }>;

export function SeverityBadge({ severidad }: { severidad: Severidad }) {
  const dato = severidades[severidad];
  return (
    <span className={`severity severity--${dato.clase}`} aria-label={`Severidad ${dato.nombre}`}>
      <span aria-hidden="true">{dato.forma}</span>
      {dato.nombre}
    </span>
  );
}

export function nombreSeveridad(severidad: Severidad) {
  return severidades[severidad].nombre;
}
