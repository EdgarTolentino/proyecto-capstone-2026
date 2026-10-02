/** La API configura la faena con esta zona; no se debe usar la zona del navegador. */
export const ZONA_HORARIA_FAENA = "America/Santiago";

const formatoFecha = /^(\d{4})-(\d{2})-(\d{2})$/;

export function esFechaValida(fecha: string): boolean {
  const partes = formatoFecha.exec(fecha);
  if (!partes) return false;

  const anio = Number(partes[1]);
  const mes = Number(partes[2]);
  const dia = Number(partes[3]);
  if (anio < 1 || mes < 1 || mes > 12) return false;

  const bisiesto = anio % 400 === 0 || (anio % 4 === 0 && anio % 100 !== 0);
  const diasPorMes = [31, bisiesto ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return dia >= 1 && dia <= diasPorMes[mes - 1];
}

export function sumarDias(fecha: string, dias: number): string {
  if (!esFechaValida(fecha)) throw new RangeError(`Fecha inválida: ${fecha}`);
  const [anio, mes, dia] = fecha.split("-").map(Number);
  const resultado = new Date(0);
  resultado.setUTCHours(0, 0, 0, 0);
  resultado.setUTCFullYear(anio, mes - 1, dia + dias);
  return [resultado.getUTCFullYear(), resultado.getUTCMonth() + 1, resultado.getUTCDate()]
    .map((parte, indice) => String(parte).padStart(indice === 0 ? 4 : 2, "0"))
    .join("-");
}

function partesEnFaena(instante: number): Record<string, number> {
  const formato = new Intl.DateTimeFormat("en-US", {
    timeZone: ZONA_HORARIA_FAENA,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  return Object.fromEntries(
    formato.formatToParts(new Date(instante))
      .filter((parte) => parte.type !== "literal")
      .map((parte) => [parte.type, Number(parte.value)]),
  );
}

export function fechaActualEnFaena(ahora = new Date()): string {
  const partes = partesEnFaena(ahora.getTime());
  return `${partes.year}-${String(partes.month).padStart(2, "0")}-${String(partes.day).padStart(2, "0")}`;
}

/** Convierte la medianoche local de la faena a UTC; resuelve días con cambio DST a medianoche. */
export function inicioDelDiaEnFaena(fecha: string): string {
  if (!esFechaValida(fecha)) throw new RangeError(`Fecha inválida: ${fecha}`);
  const [anio, mes, dia] = fecha.split("-").map(Number);
  const objetivoLocal = Date.UTC(anio, mes - 1, dia);
  let candidato = objetivoLocal;
  const visitados = new Set<number>();

  for (let intento = 0; intento < 6; intento += 1) {
    if (visitados.has(candidato)) break;
    visitados.add(candidato);
    const partes = partesEnFaena(candidato);
    const horaLocal = Date.UTC(
      partes.year,
      partes.month - 1,
      partes.day,
      partes.hour,
      partes.minute,
      partes.second,
    );
    const siguiente = candidato + (objetivoLocal - horaLocal);
    if (siguiente === candidato) return new Date(candidato).toISOString();
    if (visitados.has(siguiente)) {
      // Si la medianoche no existió por el cambio de hora, el instante posterior es
      // el primer instante representable de ese día local.
      return new Date(Math.max(candidato, siguiente)).toISOString();
    }
    candidato = siguiente;
  }

  return new Date(candidato).toISOString();
}

export function rangoDefectoPanel(ahora = new Date()): { desde: string; hasta: string } {
  const hasta = fechaActualEnFaena(ahora);
  return { desde: sumarDias(hasta, -6), hasta };
}
