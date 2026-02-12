"""Ontología legal para auditoría laboral (LFT México).

Define los modelos Pydantic que representan actores, montos, hechos auditables
y el estado del expediente para el flujo de LangGraph.
Importa constantes de legal_constants para validaciones y cálculos.
"""

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, computed_field, field_validator, model_validator

# Importar constantes LFT para uso en validadores y documentación
from app.core.legal_constants import VACACIONES_DIGNAS


# ---------------------------------------------------------------------------
# Monto — Representación de cantidades monetarias
# ---------------------------------------------------------------------------
class Monto(BaseModel):
    """Cantidad de dinero con moneda (LFT: referencias a salarios, indemnizaciones).

    Attributes:
        cantidad: Importe numérico (siempre no negativo en contexto laboral).
        moneda: Código ISO de moneda (ej. MXN). Art. 2 LFT — salarios en moneda.
    """

    cantidad: Decimal
    moneda: str = "MXN"

    @field_validator("cantidad")
    @classmethod
    def cantidad_no_negativa(cls, v: Decimal) -> Decimal:
        """En contexto laboral los montos no deben ser negativos."""
        if v < 0:
            raise ValueError("La cantidad no puede ser negativa")
        return v

    @field_validator("moneda", mode="before")
    @classmethod
    def moneda_uppercase(cls, v: Any) -> str:
        """Normaliza la moneda a mayúsculas (ej. MXN)."""
        return str(v).strip().upper() if v else "MXN"


# ---------------------------------------------------------------------------
# Perfil del trabajador (actor en la relación laboral)
# ---------------------------------------------------------------------------
class PerfilActor(BaseModel):
    """Datos del trabajador para cálculos de antigüedad y liquidación (LFT).

    Art. 18 LFT (relación de trabajo); Art. 48 y 162 para indemnización y prima.
    Valida que fecha_salida > fecha_ingreso y calcula antigüedad en años.
    """

    fecha_ingreso: date
    fecha_salida: date
    salario_diario: Decimal
    salario_integrado: Decimal | None = None

    @model_validator(mode="after")
    def fecha_salida_posterior_a_ingreso(self) -> "PerfilActor":
        """LFT: la fecha de separación debe ser posterior al ingreso."""
        if self.fecha_salida <= self.fecha_ingreso:
            raise ValueError(
                "fecha_salida debe ser posterior a fecha_ingreso (Art. 18 LFT)"
            )
        return self

    @computed_field
    @property
    def antiguedad_anios(self) -> float:
        """Antigüedad en años (fracción decimal) entre ingreso y salida.

        Utilizado para prima de antigüedad (Art. 162) y vacaciones (Vacaciones Dignas).
        """
        delta = self.fecha_salida - self.fecha_ingreso
        return round(delta.days / 365.0, 4)

    @computed_field
    @property
    def dias_vacaciones_segun_ley(self) -> int:
        """Días de vacaciones que corresponden por antigüedad (Vacaciones Dignas, LFT)."""
        anios_completos: int = int(self.antiguedad_anios)
        if anios_completos < 1:
            return 0
        # LFT: tabla hasta 35+ años; más de 35 se considera 32 días
        return VACACIONES_DIGNAS.get(min(anios_completos, 35), 32)

    @field_validator("salario_diario", "salario_integrado")
    @classmethod
    def salario_positivo(cls, v: Decimal | None) -> Decimal | None:
        """Los salarios deben ser positivos (LFT)."""
        if v is not None and v <= 0:
            raise ValueError("El salario debe ser mayor que cero")
        return v


# ---------------------------------------------------------------------------
# Hecho auditable (posible contradicción o hallazgo)
# ---------------------------------------------------------------------------
CATEGORIA_HECHO: type[str] = Literal[
    "DESPIDO_INJUSTIFICADO",
    "FALTA_PAGO",
    "TIEMPO_EXTRA",
    "VACACIONES",
    "AGUINALDO",
    "PRIMA_VACACIONAL",
    "PRIMA_ANTIGUEDAD",
    "DISCRIMINACION",
    "ACOSO",
    "OTRO",
]


class HechoAuditable(BaseModel):
    """Un hecho o posible contradicción detectado en la auditoría (LFT).

    Permite a la IA citar el fundamento legal (artículo) para cada hallazgo.
    """

    categoria: CATEGORIA_HECHO
    descripcion: str = ""
    fundamento_legal: str = ""
    severidad: Literal["BAJA", "MEDIA", "ALTA"] = "MEDIA"

    @field_validator("fundamento_legal", mode="before")
    @classmethod
    def fundamento_stripped(cls, v: Any) -> str:
        """Normaliza el texto del fundamento legal."""
        return str(v).strip() if v is not None else ""


# ---------------------------------------------------------------------------
# Estado global del expediente (LangGraph)
# ---------------------------------------------------------------------------
class ExpedienteState(BaseModel):
    """Estado global del expediente para el flujo de LangGraph.

    Agrupa hechos auditables, resumen del caso y metadatos de auditoría.
    """

    hechos: list[HechoAuditable] = []
    resumen_caso: str = ""
    metadatos_auditoria: dict[str, Any] = {}

    @field_validator("hechos", mode="before")
    @classmethod
    def hechos_lista(cls, v: Any) -> list[HechoAuditable]:
        """Asegura que hechos sea una lista de HechoAuditable."""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("hechos debe ser una lista")
        return [HechoAuditable.model_validate(x) for x in v]
