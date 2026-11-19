"""
Módulo 2 — Servicio de movimiento de documentos al servidor.

Regla critica: este modulo NUNCA elimina archivos del servidor (T:).
Las unicas operaciones permitidas sobre el servidor son: mkdir y shutil.copy2.
"""
import shutil
import logging
from datetime import date
from pathlib import Path

from app.models import MESES_ES

logger = logging.getLogger(__name__)

# Patrón de búsqueda para cada disciplina en el servidor (estructura v1)
DISCIPLINA_PATRON = {
    'Civil':  'CIVIL',
    'Ductos': 'DUCTO',
}

# Códigos de carpeta para estructura v2
DISCIPLINA_V2 = {
    'Civil':  '06-CI',
    'Ductos': '10-DU',
}

TIPO_DOC_V2 = {
    'ESPECIFICACIONES':      '01-TS',
    'FUNDACIONES':           '02-RS',
    'ESTRUCTURAS':           '03-STR',
    'UNDERGROUND':           '04-UN',
    'MOVIMIENTO DE SUELO':   '05-ED',
    'MEMORIAS DESCRIPTIVAS': '06-TD',
    'PAVIMENTOS Y CAMINOS':  '08-P_Y_C',
    'ARQUITECTURA':          '09-CA',
    'LAY OUT':               '10-LO',
    'ESTUDIOS ESPECIALES':   '11-SS',
    'REQUISICIONES':         '12-MR',
    'LISTAS':                '13-LI',
}


def encontrar_carpeta_disciplina(ruta_base: Path, disciplina: str) -> Path:
    """
    Busca en ruta_base un subdirectorio cuyo nombre contiene el patrón
    asociado a la disciplina (ej. 'CIVIL' para 'Civil').

    Lanza ValueError si no se encuentra o si la disciplina no es soportada.
    """
    patron = DISCIPLINA_PATRON.get(disciplina)
    if patron is None:
        raise ValueError(
            f"La disciplina '{disciplina}' no tiene una carpeta en el servidor. "
            "Solo se admiten documentos de disciplina Civil o Ductos."
        )

    for entry in ruta_base.iterdir():
        if entry.is_dir() and patron.upper() in entry.name.upper():
            return entry

    raise ValueError(
        f"No se encontró ninguna carpeta de disciplina '{disciplina}' "
        f"(patrón: '{patron}') dentro de:\n{ruta_base}\n\n"
        "Verificá que la carpeta exista en el servidor."
    )


def encontrar_carpeta_tipo(carpeta_disc: Path, tipo_documento: str) -> Path:
    """
    Busca en carpeta_disc un subdirectorio cuyo nombre contiene el tipo de documento.
    Maneja prefijos numéricos del estilo 'XX - FUNDACIONES'.
    """
    for entry in carpeta_disc.iterdir():
        if entry.is_dir() and tipo_documento.upper() in entry.name.upper():
            return entry
    raise ValueError(
        f"No se encontró carpeta para el tipo de documento '{tipo_documento}' "
        f"dentro de:\n{carpeta_disc}\n\n"
        "Verificá que la carpeta exista en el servidor."
    )


ALCANCE_SIGLA = 'OE'  # Este dashboard siempre maneja alcances de Owner Engineering


def encontrar_carpeta_alcance(base: Path, numero: str) -> Path:
    """Busca en base una carpeta cuyo nombre contiene '{numero}_OE' (ej: 03-501_OE)."""
    numero = (numero or '').strip()
    if not numero:
        raise ValueError(
            "El proyecto no tiene configurado el número de alcance (OE). "
            "Configuralo en Configuración → editar proyecto."
        )
    patron = f'{numero}_{ALCANCE_SIGLA}'.upper()
    for entry in base.iterdir():
        if entry.is_dir() and patron in entry.name.upper():
            return entry
    raise ValueError(
        f"No se encontró carpeta de alcance OE {numero} "
        f"(patrón: '{patron}') dentro de:\n{base}\n\n"
        "Verificá que la carpeta exista en el servidor."
    )


def construir_ruta_v2(doc, proyecto) -> Path:
    """Construye la ruta para proyectos con estructura v2: base/{NN-NNN_OE}/disc/tipo/..."""
    base = Path(proyecto.ruta_servidor_base)
    disc_code = DISCIPLINA_V2.get(doc.disciplina)
    if not disc_code:
        raise ValueError(
            f"La disciplina '{doc.disciplina}' no tiene código v2 definido."
        )
    tipo_code = TIPO_DOC_V2.get(doc.tipo_documento)
    if not tipo_code:
        raise ValueError(
            f"El tipo de documento '{doc.tipo_documento}' no tiene código v2 definido."
        )
    numero_alcance = getattr(proyecto, 'alcance_v2', '') or ''
    carpeta_alcance = encontrar_carpeta_alcance(base, numero_alcance)
    ruta = carpeta_alcance / disc_code / tipo_code
    if not proyecto.provision_unica:
        ruta = ruta / doc.provision
    fecha = date.fromisoformat(doc.fecha_llegada)
    mes_str = f"{fecha.year}-{MESES_ES[fecha.month]}"
    fecha_str = fecha.strftime('%y-%m-%d')
    ruta = ruta / mes_str / fecha_str
    if doc.asignado_a:
        ruta = ruta / doc.asignado_a
    return ruta


def construir_ruta_destino(doc, proyecto) -> Path:
    """
    Construye la ruta completa de destino en el servidor para un documento.

    v1: {base}/{disciplina}/{tipo_doc}[/{provision}]/{mes}/{fecha}
    v2: {base}/05-500/{disc_code}/{tipo_code}[/{provision}]/{mes}/{fecha}
    """
    if getattr(proyecto, 'estructura_servidor', 'v1') == 'v2':
        return construir_ruta_v2(doc, proyecto)

    base = Path(proyecto.ruta_servidor_base)

    carpeta_disc = encontrar_carpeta_disciplina(base, doc.disciplina)

    ruta = encontrar_carpeta_tipo(carpeta_disc, doc.tipo_documento)

    if not proyecto.provision_unica:
        nombre_prov = doc.provision
        ruta_prov = ruta / nombre_prov
        if not ruta_prov.exists():
            raise ValueError(
                f"No se encontró la carpeta de provisión '{nombre_prov}' "
                f"dentro de:\n{ruta}\n\n"
                "Creá la carpeta manualmente o usá el botón 'Crear carpetas' "
                "en la configuración del proyecto."
            )
        ruta = ruta_prov

    fecha = date.fromisoformat(doc.fecha_llegada)
    mes_str = f"{fecha.year}-{MESES_ES[fecha.month]}"   # ej: '2026-03-Marzo'
    fecha_str = fecha.strftime('%y-%m-%d')   # ej: '26-03-15'

    ruta = ruta / mes_str / fecha_str
    if doc.asignado_a:
        ruta = ruta / doc.asignado_a
    return ruta


def mover_al_servidor(doc, proyecto) -> str:
    """
    Copia el archivo PDF desde la carpeta Backup local al servidor.

    - Crea las carpetas intermedias si no existen.
    - Nunca elimina nada del servidor ni del Backup local.
    - Devuelve la ruta de destino como string.
    - Lanza excepciones con mensajes claros ante errores.
    """
    # Validar acceso al servidor
    base = Path(proyecto.ruta_servidor_base)
    drive = Path(base.anchor)
    if not drive.exists():
        raise OSError(
            f"No se puede acceder al servidor ({drive}).\n"
            "Verificá que estés conectado a la VPN (FortiClient)."
        )

    if not base.exists():
        raise FileNotFoundError(
            f"La ruta base del proyecto no existe en el servidor:\n{base}\n\n"
            "Verificá la configuración del proyecto."
        )

    # Encontrar archivo fuente en carpeta Backup
    if not doc.archivo_local:
        raise ValueError("El documento no tiene ruta de archivo local registrada.")

    original = Path(doc.archivo_local)
    fuente = original.parent / 'Backup' / original.name

    if not fuente.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo en la carpeta de respaldo:\n{fuente}\n\n"
            "El archivo puede haber sido movido o eliminado manualmente."
        )

    # Construir ruta destino y crear carpetas
    carpeta_destino = construir_ruta_destino(doc, proyecto)
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    destino = carpeta_destino / original.name
    shutil.copy2(str(fuente), str(destino))

    logger.info("Documento copiado al servidor: %s → %s", fuente, destino)
    return str(carpeta_destino)
