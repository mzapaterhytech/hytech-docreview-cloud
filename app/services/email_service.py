"""
Módulo 3 — Servicio de generación de correos para el Nuevo Outlook.

Genera archivos .eml y los abre con os.startfile() para que el Nuevo Outlook
los abra como ventanas de redacción listas para revisar y enviar.

Regla: NUNCA envía correos automáticamente. El usuario revisa y envía manualmente.
"""
import logging
import os
import tempfile
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itertools import groupby
from pathlib import Path

logger = logging.getLogger(__name__)


def generar_borradores_proyecto(proyecto) -> list:
    """
    Genera un .eml por cada combinación (asignado_a, provision) con documentos
    pendientes de correo en el proyecto, y los abre en Outlook.

    Criterio de inclusión: ruta_servidor asignada y correo_enviado = False.
    Agrupa por (asignado_a, provision) — un correo por combinación única.

    Devuelve lista de dicts:
        [{'persona': 'MAZ', 'provision': '03. EPF2', 'n_docs': 3}, ...]

    Marca doc.correo_enviado = True en cada documento procesado.
    """
    from app import db
    from app.models import Usuario

    docs_pendientes = [
        d for d in proyecto.documentos
        if d.ruta_servidor and not d.correo_enviado and not d.correo_borrador and not d.cargado_dms
    ]
    if not docs_pendientes:
        return []

    # Mapeo iniciales → email/nombre desde los usuarios globales del dashboard
    usuarios = Usuario.query.filter_by(activo=True).all()
    email_por_iniciales = {u.iniciales: u.email for u in usuarios}
    nombre_por_iniciales = {u.iniciales: u.nombre for u in usuarios}

    # Agrupar por (asignado_a, provision)
    docs_pendientes.sort(key=lambda d: (d.asignado_a or '', d.provision or ''))

    borradores = []

    for (asignado, provision), grupo in groupby(
        docs_pendientes, key=lambda d: (d.asignado_a or '', d.provision or '')
    ):
        docs_grupo = list(grupo)
        email_dest = email_por_iniciales.get(asignado, '')
        if provision:
            asunto = f"{proyecto.codigo} - {provision} - Revisión de documentos"
        else:
            asunto = f"{proyecto.codigo} - Revisión de documentos"

        # Construir tabla HTML
        filas = ''
        for doc in docs_grupo:
            carpeta = str(Path(doc.ruta_servidor).parent) if doc.ruta_servidor else '—'
            filas += (
                f'<tr>'
                f'<td style="padding:4px 8px;border:1px solid #ddd;font-family:monospace;white-space:nowrap">{doc.codigo}</td>'
                f'<td style="padding:4px 8px;border:1px solid #ddd">{doc.titulo or "—"}</td>'
                f'<td style="padding:4px 8px;border:1px solid #ddd;text-align:center">{doc.revision}</td>'
                f'<td style="padding:4px 8px;border:1px solid #ddd;text-align:center">{doc.fecha_devolucion or "—"}</td>'
                f'<td style="padding:4px 8px;border:1px solid #ddd;font-family:monospace;font-size:11px">{carpeta}</td>'
                f'</tr>'
            )

        tabla = (
            '<table style="border-collapse:collapse;font-size:13px;margin-top:12px">'
            '<thead><tr style="background:#f0f0f0">'
            '<th style="padding:4px 8px;border:1px solid #ddd">Código</th>'
            '<th style="padding:4px 8px;border:1px solid #ddd">Título</th>'
            '<th style="padding:4px 8px;border:1px solid #ddd">Rev.</th>'
            '<th style="padding:4px 8px;border:1px solid #ddd">Devolución</th>'
            '<th style="padding:4px 8px;border:1px solid #ddd">Carpeta en servidor</th>'
            '</tr></thead>'
            f'<tbody>{filas}</tbody>'
            '</table>'
        )

        # Sustituir variables del template y convertir saltos de línea a <br>
        nombre_asignado = nombre_por_iniciales.get(asignado, asignado)
        intro_raw = (proyecto.template_correo or '').strip()
        if intro_raw:
            intro_html = (
                intro_raw
                .replace('{nombre}', nombre_asignado)
                .replace('{proyecto}', proyecto.nombre or proyecto.codigo)
                .replace('{provision}', provision)
                .replace('\r\n', '\n')
                .replace('\n', '<br>')
            )
            cuerpo_html = f'<p style="font-size:13px">{intro_html}</p>{tabla}'
        else:
            cuerpo_html = tabla

        # Crear archivo .eml
        msg = MIMEMultipart('alternative')
        msg['To'] = email_dest
        msg['Subject'] = asunto
        msg['X-Unsent'] = '1'  # Indica que es un borrador sin enviar
        msg.attach(MIMEText(cuerpo_html, 'html', 'utf-8'))

        # Guardar en carpeta temporal y abrir con Outlook
        tmp_dir = Path(tempfile.gettempdir()) / 'hytech_correos'
        tmp_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        nombre_archivo = f"{proyecto.codigo}_{asignado}_{provision}_{ts}.eml".replace('/', '-').replace('\\', '-')
        eml_path = tmp_dir / nombre_archivo

        with open(eml_path, 'w', encoding='utf-8') as f:
            f.write(msg.as_string())

        os.startfile(str(eml_path))
        logger.info("Correo abierto en Outlook: %s → %s", asunto, email_dest)

        for doc in docs_grupo:
            doc.correo_borrador = True

        borradores.append({
            'persona': asignado,
            'provision': provision,
            'n_docs': len(docs_grupo),
        })

    db.session.commit()
    return borradores
