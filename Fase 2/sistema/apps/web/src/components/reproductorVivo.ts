// Política de reproducción de la vista en vivo (prototipo local). No toca el DOM: recibe cuadros ya
// decodificados, un reloj que avanza con cada tick de animación y una función para dibujar.
//
// El modelo analiza a ráfagas, así que los cuadros llegan a un ritmo irregular, pero cada uno trae
// su posición en el video (`posicion_s`). Se reproducen por esa posición, con un colchón de 1 s.

export interface Imagen {
  close(): void;
}

export interface CuadroListo {
  seq: number;
  posicion_s: number;
  imagen: Imagen;
}

// Segundos de video que hacen falta en el buffer para empezar (o para retomar tras vaciarse).
export const INICIO_S = 1;
// Lo más que se guarda; lo que sobra, de lo más viejo, se cierra y se descarta.
export const TOPE_BUFFER_S = 3;

export class ReproductorVivo {
  // Último `seq` recibido: es el `desde` del siguiente pedido.
  ultimoSeq = 0;

  private buffer: CuadroListo[] = [];
  private reproduciendo = false;
  private reloj = 0; // posición de reproducción, en segundos de video
  private ultimaMarca: number | undefined;

  constructor(private readonly dibujar: (imagen: Imagen) => void) {}

  agregar(cuadros: CuadroListo[]): void {
    const ordenados = [...cuadros].sort((a, b) => a.seq - b.seq);
    const nuevos: CuadroListo[] = [];
    for (const cuadro of ordenados) {
      // Un `seq` repetido o anterior ya se tuvo: no se duplica.
      if (cuadro.seq > this.ultimoSeq && !nuevos.some((n) => n.seq === cuadro.seq)) nuevos.push(cuadro);
      else cuadro.imagen.close();
    }
    if (nuevos.length === 0) return;

    // Si el servidor devolvió solo los más nuevos, lo que había queda atrás: se sigue desde lo nuevo.
    if (nuevos[0].seq > this.ultimoSeq + 1) this.descartarBuffer();
    this.buffer.push(...nuevos);
    this.ultimoSeq = nuevos[nuevos.length - 1].seq;

    while (this.buffer.length > 1 && this.duracion() > TOPE_BUFFER_S) this.buffer.shift()?.imagen.close();
    // Si se descartó lo que aún no se había mostrado (por un salto de seq o por el tope), el reloj
    // salta a lo más viejo que queda: no se espera a que llegue a esa posición.
    if (this.reproduciendo && this.buffer.length > 0 && this.reloj < this.buffer[0].posicion_s) {
      this.reloj = this.buffer[0].posicion_s;
    }
  }

  // Un tick de animación con su marca de tiempo en milisegundos.
  avanzar(marcaMs: number): void {
    const delta = this.ultimaMarca === undefined ? 0 : Math.max(0, marcaMs - this.ultimaMarca);
    this.ultimaMarca = marcaMs;

    if (!this.reproduciendo) {
      if (this.buffer.length === 0 || this.duracion() < INICIO_S) return;
      this.reproduciendo = true;
      this.reloj = this.buffer[0].posicion_s;
    } else {
      this.reloj += delta / 1000;
    }

    // El cuadro a mostrar es el de mayor posición que no pasa el reloj; los anteriores se descartan.
    let ultimoVisible = -1;
    while (ultimoVisible + 1 < this.buffer.length && this.buffer[ultimoVisible + 1].posicion_s <= this.reloj) {
      ultimoVisible += 1;
    }
    if (ultimoVisible >= 0) {
      const vencidos = this.buffer.splice(0, ultimoVisible + 1);
      for (const cuadro of vencidos.slice(0, -1)) cuadro.imagen.close();
      const mostrar = vencidos[vencidos.length - 1];
      this.dibujar(mostrar.imagen);
      mostrar.imagen.close(); // ya está pintado en el lienzo
    }
    // Se vació: el procesamiento va más lento que el tiempo real. Se queda en el último cuadro y
    // vuelve a cargar 1 s antes de seguir (sin acelerar ni repetir).
    if (this.buffer.length === 0) this.reproduciendo = false;
  }

  // Pausa o error: se cierra todo y se vuelve a cargar desde cero (el `seq` se conserva).
  vaciar(): void {
    this.descartarBuffer();
    this.reproduciendo = false;
    this.ultimaMarca = undefined;
  }

  // El servidor empezó una secuencia nueva (por ejemplo, el video se reprocesó): se olvida el `seq`.
  reiniciarSecuencia(): void {
    this.vaciar();
    this.ultimoSeq = 0;
  }

  private descartarBuffer(): void {
    for (const cuadro of this.buffer) cuadro.imagen.close();
    this.buffer = [];
  }

  private duracion(): number {
    if (this.buffer.length === 0) return 0;
    return this.buffer[this.buffer.length - 1].posicion_s - this.buffer[0].posicion_s;
  }
}
