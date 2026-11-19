"""
Cálculo de días hábiles para Argentina.
Excluye sábados, domingos y feriados nacionales argentinos.
"""

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def dias_habiles_hasta(fecha_inicio: date, fecha_fin: date) -> int:
    """
    Devuelve los días hábiles que faltan desde fecha_inicio hasta fecha_fin.
    Resultado negativo si fecha_fin ya pasó.
    Excluye fines de semana y feriados argentinos.
    """
    try:
        import holidays
        años = {fecha_inicio.year, fecha_fin.year}
        feriados = holidays.Argentina(years=list(años))
    except ImportError:
        logger.warning("Paquete 'holidays' no instalado — se usarán solo días de semana.")
        feriados = {}

    if fecha_fin >= fecha_inicio:
        count = 0
        d = fecha_inicio
        while d < fecha_fin:
            if d.weekday() < 5 and d not in feriados:
                count += 1
            d += timedelta(days=1)
        return count
    else:
        count = 0
        d = fecha_fin
        while d < fecha_inicio:
            if d.weekday() < 5 and d not in feriados:
                count += 1
            d += timedelta(days=1)
        return -count


def sumar_dias_habiles(fecha_inicio: date, n: int = 5) -> date:
    """
    Devuelve la fecha resultante de sumar n días hábiles a fecha_inicio.
    Excluye fines de semana y feriados argentinos.

    Args:
        fecha_inicio: fecha de partida.
        n:            cantidad de días hábiles a sumar (default 5).

    Returns:
        Fecha resultante como objeto date.
    """
    try:
        import holidays
        # Precalcular feriados para el año actual y el siguiente (por si cruza año)
        feriados = holidays.Argentina(years=[fecha_inicio.year, fecha_inicio.year + 1])
    except ImportError:
        logger.warning("Paquete 'holidays' no instalado — se usarán solo días de semana.")
        feriados = {}

    fecha = fecha_inicio
    sumados = 0
    while sumados < n:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5 and fecha not in feriados:  # lun–vie, no feriado
            sumados += 1
    return fecha
