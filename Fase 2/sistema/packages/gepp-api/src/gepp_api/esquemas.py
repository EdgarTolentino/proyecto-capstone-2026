"""Cuerpos de petición del contrato. Las respuestas se validan contra el YAML en las pruebas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TipoEpp = Literal["casco", "chaleco", "lentes", "guantes", "arnes", "calzado"]
BaseLicitud = Literal["obligacion_legal", "interes_legitimo", "contrato"]


class DecisionTriage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: Literal["confirmado", "falso_positivo", "duplicado", "pospuesto"]
    motivo: str | None = None
    duplicado_de: int | None = None
    posponer_hasta: datetime | None = None


class TriageLote(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    decision: DecisionTriage


class AccionCorrectivaNueva(BaseModel):
    responsable_id: int
    descripcion: str = Field(min_length=1)
    plazo: date


class ReglaEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    area_id: int
    zona_ids: list[int] = Field(default_factory=list)
    epp_exigido: list[TipoEpp] = Field(min_length=1)
    #: Segundos, nunca cuadros (ADR-005).
    confirmacion_segundos: float = Field(ge=0.2)
    cierre_segundos: float = Field(default=3.0, gt=0)
    confianza_minima: float = Field(default=0.45, ge=0, le=1)
    severidad: Literal[1, 2, 3, 4]
    turno: str | None = None
    hora_desde: str | None = None
    hora_hasta: str | None = None
    activa: bool = True
    base_licitud: BaseLicitud = "obligacion_legal"
    norma_fundante: str | None = None
    finalidad_declarada: str = Field(min_length=1)
    retencion_dias: int = Field(default=30, ge=1)
    destinatarios: list[int] = Field(default_factory=list)
    espera_entre_alertas_s: int | None = None


class Simulacion(BaseModel):
    desde: date
    hasta: date
    regla: ReglaEntrada
