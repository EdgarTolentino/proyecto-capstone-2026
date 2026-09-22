"""Geometría mínima. Cajas normalizadas a 0..1 respecto del cuadro."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Caja:
    """Caja delimitadora en coordenadas normalizadas (0..1), origen arriba-izquierda."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError(f"caja degenerada: {self}")

    @property
    def ancho(self) -> float:
        return self.x2 - self.x1

    @property
    def alto(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.ancho * self.alto

    @property
    def centro(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def contiene(self, punto: tuple[float, float]) -> bool:
        x, y = punto
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def interseccion(self, otra: Caja) -> float:
        ancho = min(self.x2, otra.x2) - max(self.x1, otra.x1)
        alto = min(self.y2, otra.y2) - max(self.y1, otra.y1)
        return ancho * alto if ancho > 0 and alto > 0 else 0.0

    def iou(self, otra: Caja) -> float:
        inter = self.interseccion(otra)
        union = self.area + otra.area - inter
        return inter / union if union > 0 else 0.0

    def fraccion_dentro_de(self, otra: Caja) -> float:
        """Qué proporción de esta caja cae dentro de `otra`.

        Es el criterio de pertenencia a zona: una persona "está" en la zona cuando
        una fracción suficiente de su caja cae dentro del polígono envolvente.
        """
        return self.interseccion(otra) / self.area if self.area > 0 else 0.0

    def franja(self, desde: float, hasta: float) -> Caja:
        """Franja horizontal de la caja, expresada en fracción de su alto.

        `franja(0.0, 0.35)` es el tercio superior — donde debe estar el casco.
        """
        if not 0.0 <= desde < hasta <= 1.0:
            raise ValueError(f"franja inválida: {desde}-{hasta}")
        return Caja(self.x1, self.y1 + self.alto * desde, self.x2, self.y1 + self.alto * hasta)


#: Polígono en coordenadas normalizadas 0..1, como lo guarda `zona.poligono`.
Poligono = tuple[tuple[float, float], ...]


def punto_en_poligono(punto: tuple[float, float], poligono: Poligono) -> bool:
    """Trazado de rayos: cuántas aristas cruza una semirrecta horizontal desde el punto."""
    x, y = punto
    dentro = False
    j = len(poligono) - 1
    for i in range(len(poligono)):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def fraccion_en_poligono(caja: Caja, poligono: Poligono, muestras: int = 8) -> float:
    """Qué proporción de la caja cae dentro del polígono, por muestreo en rejilla.

    Con 8 x 8 puntos el error es de ~1/64 por borde: sobra para decidir contra un umbral
    de 0,50 y evita traer una biblioteca de geometría a un paquete que es Python puro.
    """
    if len(poligono) < 3:
        raise ValueError("un polígono necesita al menos 3 vértices")
    dentro = 0
    for i in range(muestras):
        for j in range(muestras):
            px = caja.x1 + caja.ancho * (i + 0.5) / muestras
            py = caja.y1 + caja.alto * (j + 0.5) / muestras
            dentro += punto_en_poligono((px, py), poligono)
    return dentro / (muestras * muestras)
