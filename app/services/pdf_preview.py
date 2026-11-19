"""
Genera una imagen de previsualización de la esquina inferior derecha de la
última página de un PDF (zona donde suele estar el rótulo del plano).
"""

import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def generar_preview(pdf_path: str, previews_dir: Path) -> str | None:
    """
    Renderiza la esquina inferior derecha (40% ancho × 25% alto) de la última
    página del PDF y guarda el resultado como PNG en previews_dir.

    Args:
        pdf_path:     ruta absoluta al archivo PDF.
        previews_dir: directorio donde se guardan las imágenes generadas.

    Returns:
        Nombre del archivo PNG generado (sin ruta), o None si falla.
    """
    try:
        import fitz  # PyMuPDF

        previews_dir.mkdir(parents=True, exist_ok=True)
        doc = fitz.open(pdf_path)
        page = doc[-1]  # última página (donde está el rótulo)

        rect = page.rect
        # Recorte: columna derecha (60-100%) × fila inferior (75-100%)
        clip = fitz.Rect(
            rect.width * 0.60,
            rect.height * 0.75,
            rect.width,
            rect.height,
        )

        # Zoom 2× para mejor legibilidad
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, clip=clip)

        filename = f"{uuid.uuid4().hex}.png"
        pix.save(str(previews_dir / filename))
        doc.close()
        return filename

    except ImportError:
        logger.warning("PyMuPDF no está instalado — no se generarán previews.")
        return None
    except Exception as exc:
        logger.warning("No se pudo generar preview para %s: %s", pdf_path, exc)
        return None


def extraer_titulo_pdf(pdf_path: str) -> str:
    """
    Extrae el título del rótulo de la primera página del PDF.

    Estrategia 1: busca TITULO: y recoge las líneas siguientes hasta la próxima
    etiqueta de rótulo. Filtra vacías y numéricas. Une con ' - '.

    Estrategia 2 (fallback si TITULO: vacío): busca el texto que sigue a un tipo
    de documento conocido (MEMORIA DE CÁLCULO, INFORME, etc.) salteando números.

    Devuelve '' si no hay texto (PDF escaneado) o no se puede determinar el título.
    """
    try:
        import fitz  # PyMuPDF
        import re

        doc = fitz.open(pdf_path)
        text = doc[0].get_text("text")
        doc.close()

        if not text.strip():
            return ''  # PDF escaneado — sin texto

        # Regex para detectar etiquetas de rótulo (líneas que NO son el título)
        RE_ETIQUETA = re.compile(
            r'^(PROYECTO|PROJECT|DOC(UMENTO)?[\s\.]*N[°º\.]?|REVIS[IÍ][OÓ]N|REEMPLAZA|'
            r'P[AÁ]G(INA)?|FECHA|REV[\.\s:]|EJE[\.\s:]|APR[\.\s:]|CHK[\.\s:]|'
            r'DESCRIPCI[OÓ]N|ESCALA|SCALE|EMISI[OÓ]N|IND[\.\s:]|'
            r'FACILITIES|TODA LA INFORMACI[OÓ]N|CODIGO)',
            re.IGNORECASE
        )
        RE_SOLO_NUMEROS = re.compile(r'^\d[\d\s\/\-\.]*$')

        # Tipos de documento que van seguidos del título específico en la siguiente línea
        RE_TIPO_DOC = re.compile(
            r'^(MEMORIA DE C[AÁ]LCULO|INFORME|ESPECIFICACI[OÓ]N T[EÉ]CNICA|'
            r'REQUISICI[OÓ]N|ESTUDIO|PROCEDIMIENTO|PROTOCOLO)$',
            re.IGNORECASE
        )

        # ── Estrategia 1: recoger líneas después de TITULO: ──────────
        m = re.search(r'T[IÍií]TULO\s*:?\s*\n', text, re.IGNORECASE)
        if m:
            resto = text[m.end():]
            partes = []
            for linea in resto.splitlines():
                linea = linea.strip()
                if not linea:
                    continue
                if linea.endswith(':') or RE_ETIQUETA.match(linea):
                    break  # llegamos a la próxima etiqueta
                if RE_SOLO_NUMEROS.match(linea):
                    continue
                partes.append(linea)
                # Continuar solo si la primera línea es un tipo de documento conocido
                # (tiene una segunda línea con el título específico).
                # En cualquier otro caso, la primera línea ya es el título completo.
                if len(partes) == 1 and not RE_TIPO_DOC.match(linea):
                    break
                if len(partes) == 2:
                    break
            if partes:
                return ' - '.join(partes)

        # ── Estrategia 2: línea descriptiva tras tipo de documento ───
        # Busca el tipo de documento y recorre las líneas siguientes descartando
        # etiquetas conocidas, textos de confidencialidad y números hasta encontrar
        # una línea descriptiva (el título específico).
        TIPOS_DOC = re.compile(
            r'^(MEMORIA DE CA[LÁ]CULO|MEMORIA DE C[AÁ]LCULO|INFORME|'
            r'ESPECIFICACI[OÓ]N T[EÉ]CNICA|REQUISICI[OÓ]N|ESTUDIO|'
            r'PROCEDIMIENTO|PROTOCOLO)$',
            re.IGNORECASE
        )
        RE_DESCARTAR = re.compile(
            r'^(FACILITIES|CONSTRUCTION|TODA LA|CONFIDENCIAL|PROPIEDAD|'
            r'PLUSPETROL|PROHIBIDA|REPRODUCCI)',
            re.IGNORECASE
        )
        lineas = [l.strip() for l in text.splitlines()]
        for idx, linea in enumerate(lineas):
            if TIPOS_DOC.match(linea):
                # Buscar la primera línea descriptiva en las siguientes 10 líneas
                for siguiente in lineas[idx + 1: idx + 11]:
                    if not siguiente:
                        continue
                    if RE_SOLO_NUMEROS.match(siguiente):
                        continue
                    if siguiente.endswith(':'):
                        continue
                    if RE_ETIQUETA.match(siguiente):
                        continue
                    if RE_DESCARTAR.match(siguiente):
                        continue
                    if TIPOS_DOC.match(siguiente):
                        continue
                    return siguiente
                break

        return ''

    except Exception:
        return ''
