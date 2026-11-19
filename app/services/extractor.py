"""
Extrae metadatos desde el nombre de archivo de un PDF.

Convención de nombre de archivo:
    {codigo}{separador}{revision}.pdf

donde separador es el ÚLTIMO guion bajo (_) o guion (-) del nombre.

Ejemplos:
    2024-PPL-FUND-001_R0.pdf  → código: 2024-PPL-FUND-001, revisión: R0
    MEM-CALC-001-A.pdf        → código: MEM-CALC-001, revisión: A
    PLANO_FUND_B.pdf          → código: PLANO_FUND, revisión: B
"""

import re
from pathlib import Path


def extraer_metadatos_nombre(filename: str, config_proyecto: dict) -> dict:
    """
    Extrae código, revisión, provisión y tipo de documento del nombre de archivo.

    Args:
        filename: nombre del archivo (con o sin extensión).
        config_proyecto: dict con la configuración del proyecto (ver Proyecto.to_config_dict()).

    Returns:
        dict con claves: codigo, revision, provision, tipo_documento, filename.
    """
    stem = Path(filename).stem

    # Último separador _ o - define el límite revisión/código
    match = re.search(r'[_\-](?=[^_\-]*$)', stem)
    if match:
        codigo = stem[:match.start()]
        revision = stem[match.end():]
    else:
        codigo = stem
        revision = ''

    reglas_codigo = config_proyecto.get('reglas_codigo', {})
    if reglas_codigo.get('segmentos'):
        extraidos = _extraer_por_segmentos(codigo, reglas_codigo, config_proyecto)
        provision = extraidos['provision']
        tipo_documento = extraidos['tipo_documento']
    else:
        provision = _extraer_provision(codigo, config_proyecto)
        tipo_documento = _inferir_tipo(codigo, config_proyecto)

    return {
        'filename': filename,
        'codigo': codigo,
        'revision': revision,
        'provision': provision,
        'tipo_documento': tipo_documento,
    }


def _extraer_provision(codigo: str, config: dict) -> str:
    """
    Extrae la provisión desde el código del documento según la regla configurada
    y luego aplica el mapeo valor_extraído → nombre_provisión del proyecto.

    Reglas soportadas:
        - provision_unica=True          → devuelve ''
        - 'primeros_N_caracteres'       → primeros N caracteres del código
        - 'segmento_N'                  → segmento N (separado por _ o -), base 0
        - 'chars_INICIO_FIN'            → substring codigo[INICIO:FIN]
        - cadena vacía o no reconocida  → devuelve ''
    """
    if config.get('provision_unica'):
        return ''

    regla = (config.get('regla_provision') or '').strip()
    if not regla:
        return ''

    partes = re.split(r'[_\-]', codigo)
    raw = ''

    # primeros_N_caracteres
    m = re.fullmatch(r'primeros_(\d+)_caracteres', regla)
    if m:
        raw = codigo[:int(m.group(1))]

    # segmento_N
    if not raw:
        m = re.fullmatch(r'segmento_(\d+)', regla)
        if m:
            idx = int(m.group(1))
            raw = partes[idx] if idx < len(partes) else ''

    # chars_INICIO_FIN
    if not raw:
        m = re.fullmatch(r'chars_(\d+)_(\d+)', regla)
        if m:
            raw = codigo[int(m.group(1)):int(m.group(2))]

    if not raw:
        return ''

    mapeo = config.get('mapeo_provision', {})
    return mapeo.get(raw, raw)


def _inferir_tipo(codigo: str, config: dict) -> str:
    """
    Infiere el tipo de documento desde el código usando el mapeo del proyecto.

    El mapeo es {patron: tipo}; se prueban los patrones de mayor a menor longitud
    para dar prioridad a los más específicos.
    """
    reglas: dict = config.get('reglas_tipo_documento', {})
    codigo_upper = codigo.upper()
    for patron in sorted(reglas.keys(), key=len, reverse=True):
        if patron.upper() in codigo_upper:
            return reglas[patron]
    return ''


def _extraer_por_segmentos(codigo: str, reglas_codigo: dict, config: dict) -> dict:
    """
    Extrae provision y tipo_documento dividiendo el código por un separador
    y aplicando reglas por índice de segmento.

    reglas_codigo = {
        "separador": "-",
        "segmentos": [
            {"indice": 0, "campo": "provision",     "mapeo": {"052": "03. EPF2"}},
            {"indice": 4, "campo": "tipo_documento", "mapeo": {"B": "FUNDACIONES"}},
        ]
    }
    - provision_unica=True → provision siempre vacía.
    - Si el valor del segmento no está en el mapeo → tipo_documento queda vacío.
    - Si no hay mapeo definido para provision → se usa el valor raw.
    """
    separador = reglas_codigo.get('separador', '-') or '-'
    segmentos_cfg = reglas_codigo.get('segmentos', [])
    partes = codigo.split(separador)

    provision = ''
    tipo_documento = ''
    provision_unica = config.get('provision_unica', False)

    for seg in segmentos_cfg:
        indice = seg.get('indice', -1)
        campo = seg.get('campo', 'ignorar')
        mapeo = seg.get('mapeo', {})

        if campo == 'ignorar' or indice < 0 or indice >= len(partes):
            continue

        valor = partes[indice]

        if campo == 'provision' and not provision and not provision_unica:
            provision = mapeo.get(valor, valor) if mapeo else valor

        elif campo == 'tipo_documento' and not tipo_documento:
            tipo_documento = mapeo.get(valor, '') if mapeo else valor

    return {'provision': provision, 'tipo_documento': tipo_documento}
