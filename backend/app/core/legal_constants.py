"""Constantes legales centralizadas según la Ley Federal del Trabajo (LFT) México.

Este módulo agrupa los parámetros numéricos y tablas derivados de la LFT
para uso en cálculos de liquidación, auditoría laboral y validaciones.
Todas las constantes documentan el artículo de la LFT que las sustenta.
"""

from typing import Final

# ---------------------------------------------------------------------------
# Art. 87 LFT — Aguinaldo
# Los trabajadores tendrán derecho a una gratificación anual de al menos
# 15 días de salario. Quienes no hayan cumplido el año tendrán derecho
# a la parte proporcional.
# ---------------------------------------------------------------------------
"""Art. 87 LFT: Días mínimos de aguinaldo anual."""
DIAS_AGUINALDO: Final[int] = 15

# ---------------------------------------------------------------------------
# Art. 80 LFT — Prima vacacional
# Los trabajadores tendrán derecho a una prima no menor de 25% sobre
# los salarios que les correspondan durante el período de vacaciones.
# ---------------------------------------------------------------------------
"""Art. 80 LFT: Porcentaje mínimo de prima vacacional sobre salarios vacacionales."""
PORCENTAJE_PRIMA_VACACIONAL: Final[float] = 0.25

# ---------------------------------------------------------------------------
# Art. 48 LFT — Indemnización constitucional (despido injustificado)
# En caso de despido injustificado el patrón estará obligado a pagar
# tres meses de salario integrado.
# ---------------------------------------------------------------------------
"""Art. 48 LFT: Meses de salario integrado por indemnización constitucional."""
INDEMNIZACION_CONSTITUCIONAL_MESES: Final[int] = 3

# ---------------------------------------------------------------------------
# Art. 162 LFT — Prima de antigüedad
# Los trabajadores de planta tienen derecho a una prima por antigüedad de
# 12 días de salario por cada año de servicios. La prima de antigüedad
# no podrá exceder del equivalente a dos veces el salario mínimo general
# vigente en el DF (actualmente ZMVM) por cada año.
# ---------------------------------------------------------------------------
"""Art. 162 LFT: Días de salario por año para prima de antigüedad."""
PRIMA_ANTIGUEDAD_DIAS_POR_ANIO: Final[int] = 12

"""Art. 162 LFT: Tope de prima de antigüedad (veces el salario mínimo por año)."""
PRIMA_ANTIGUEDAD_TOPE_VECES_SALARIO_MINIMO: Final[int] = 2

# ---------------------------------------------------------------------------
# Fórmula de estimación de liquidación (prueba)
# 3 meses (Art. 48) + 20 días por año para verificación matemática.
# ---------------------------------------------------------------------------
"""Días de salario por año usados en la estimación básica de liquidación (test)."""
LIQUIDACION_ESTIMACION_DIAS_POR_ANIO: Final[int] = 20

# ---------------------------------------------------------------------------
# Vacaciones Dignas (reforma LFT, en vigor desde 2023)
# Tabla progresiva de días de vacaciones según años de antigüedad.
# Años 1-5: 12, 14, 16, 18, 20 días; después +2 días cada 5 años (máx. 32).
# ---------------------------------------------------------------------------
# Construcción de la tabla: 1→12, 2→14, 3→16, 4→18, 5→20;
# 6-10→22, 11-15→24, 16-20→26, 21-25→28, 26-30→30, 31+→32
_VACACIONES_BASE: list[tuple[int, int]] = [
    (1, 12),
    (2, 14),
    (3, 16),
    (4, 18),
    (5, 20),
]
_VACACIONES_RANGOS: list[tuple[int, int]] = [
    (10, 22),
    (15, 24),
    (20, 26),
    (25, 28),
    (30, 30),
    (999, 32),  # 31 años en adelante
]


def _build_vacaciones_dignas_dict() -> dict[int, int]:
    """Construye el diccionario año -> días de vacaciones (Vacaciones Dignas)."""
    result: dict[int, int] = {}
    for anio, dias in _VACACIONES_BASE:
        result[anio] = dias
    ultimo_anio = 5
    ultimos_dias = 20
    for tope_anio, dias in _VACACIONES_RANGOS:
        for anio in range(ultimo_anio + 1, tope_anio + 1):
            result[anio] = dias
        ultimo_anio = tope_anio
        ultimos_dias = dias
    return result


"""Tabla de días de vacaciones por año de antigüedad (Vacaciones Dignas, LFT)."""
VACACIONES_DIGNAS: Final[dict[int, int]] = _build_vacaciones_dignas_dict()

# ---------------------------------------------------------------------------
# Jornadas máximas legales (LFT)
# Art. 61: La duración máxima de la jornada será: 8h diurnas, 7h nocturnas,
# 7h 30min mixtas. Semanal: 48h diurna, 42h nocturna, 45h mixta.
# ---------------------------------------------------------------------------
"""LFT: Jornada máxima semanal (horas) por tipo — Art. 61 LFT."""
JORNADA_MAXIMA_HORAS_SEMANALES: Final[dict[str, int]] = {
    "DIURNA": 48,
    "NOCTURNA": 42,
    "MIXTA": 45,
}

"""LFT: Jornada máxima diaria (horas) por tipo — Art. 61 LFT."""
JORNADA_MAXIMA_HORAS_DIARIAS: Final[dict[str, float]] = {
    "DIURNA": 8.0,
    "NOCTURNA": 7.0,
    "MIXTA": 7.5,
}
