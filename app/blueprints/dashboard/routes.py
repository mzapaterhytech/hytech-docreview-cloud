import io
from sqlalchemy import func
from flask import Blueprint, jsonify, render_template, abort, request, send_file
from app.decorators import admin_required, local_file_ops_required
from app.models import Cliente, Documento, Proyecto, Usuario, DISCIPLINAS, TIPOS_DOCUMENTO
from app import db
from app.services.file_server_service import mover_al_servidor
from app.services.email_service import generar_borradores_proyecto

bp = Blueprint('dashboard', __name__)


@bp.route('/')
def index():
    """Lista de todos los clientes."""
    clientes = Cliente.query.order_by(Cliente.nombre).all()

    pendientes_por_cliente = {}
    for cliente in clientes:
        ids_proyectos = [p.id for p in cliente.proyectos]
        if ids_proyectos:
            total = Documento.query.filter(
                Documento.proyecto_id.in_(ids_proyectos),
                Documento.cargado_dms == False,
            ).count()
        else:
            total = 0
        pendientes_por_cliente[cliente.id] = total

    pendientes_por_revisor = dict(
        db.session.query(Documento.asignado_a, func.count(Documento.id))
        .filter(Documento.cargado_dms == False, Documento.asignado_a != '')
        .group_by(Documento.asignado_a)
        .order_by(func.count(Documento.id).desc())
        .all()
    )

    return render_template(
        'dashboard/index.html',
        clientes=clientes,
        pendientes_por_cliente=pendientes_por_cliente,
        pendientes_por_revisor=pendientes_por_revisor,
    )


@bp.route('/cliente/<int:cliente_id>')
def cliente(cliente_id):
    """Dashboard de un cliente: proyectos, documentos y carga por persona."""
    cliente = Cliente.query.get_or_404(cliente_id)

    # Carga global por persona (suma todos los proyectos del cliente) — usuarios
    # globales, ya no equipo por proyecto (ver decisión de diseño: iniciales únicas).
    usuarios_activos = Usuario.query.filter_by(activo=True).order_by(Usuario.iniciales).all()
    carga_global = {}
    for usuario in usuarios_activos:
        total = sum(
            1 for proyecto in cliente.proyectos
            for d in proyecto.documentos
            if d.asignado_a == usuario.iniciales and not d.cargado_dms
        )
        if total:
            carga_global[usuario.iniciales] = {'nombre': usuario.nombre, 'total': total}

    proyectos_data = []
    for proyecto in cliente.proyectos:
        docs = proyecto.documentos
        pendientes = [d for d in docs if not d.cargado_dms]
        proyectos_data.append({
            'proyecto': proyecto,
            'documentos': docs,
            'pendientes': len(pendientes),
        })

    return render_template(
        'dashboard/cliente.html',
        cliente=cliente,
        proyectos_data=proyectos_data,
        carga_global=carga_global,
        disciplinas=DISCIPLINAS,
        tipos_documento=TIPOS_DOCUMENTO,
        usuarios=usuarios_activos,
    )


# ── Endpoints AJAX ──────────────────────────────────────────

@bp.route('/documento/<int:doc_id>/toggle-dms', methods=['POST'])
@admin_required
def toggle_dms(doc_id):
    """Alterna el estado cargado_dms de un documento."""
    doc = Documento.query.get_or_404(doc_id)
    doc.cargado_dms = not doc.cargado_dms
    db.session.commit()
    return jsonify({'cargado_dms': doc.cargado_dms})


@bp.route('/documento/<int:doc_id>/editar', methods=['POST'])
@admin_required
def editar_documento(doc_id):
    """Actualiza los campos editables de un documento."""
    doc = Documento.query.get_or_404(doc_id)
    campos = ['titulo', 'disciplina', 'tipo_documento', 'asignado_a',
              'revision', 'provision', 'fecha_llegada', 'fecha_devolucion', 'fecha_revision', 'comentarios']
    for campo in campos:
        valor = request.form.get(campo)
        if valor is not None:
            setattr(doc, campo, valor.strip())
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/documento/<int:doc_id>/eliminar', methods=['POST'])
@admin_required
def eliminar_documento(doc_id):
    """Elimina un documento de la base de datos."""
    doc = Documento.query.get_or_404(doc_id)
    db.session.delete(doc)
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/documento/<int:doc_id>/reset-servidor', methods=['POST'])
@admin_required
def reset_servidor(doc_id):
    """Limpia la ruta del servidor de un documento para permitir re-subir."""
    doc = Documento.query.get_or_404(doc_id)
    doc.ruta_servidor = ''
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/documento/<int:doc_id>/mover-servidor', methods=['POST'])
@admin_required
@local_file_ops_required
def mover_servidor(doc_id):
    """Copia el documento desde el Backup local a la estructura del servidor."""
    doc = Documento.query.get_or_404(doc_id)
    proyecto = doc.proyecto
    try:
        ruta = mover_al_servidor(doc, proyecto)
        doc.ruta_servidor = ruta
        db.session.commit()
        return jsonify({'ok': True, 'ruta': ruta})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@bp.route('/documento/<int:doc_id>/reset-correo', methods=['POST'])
@admin_required
def reset_correo(doc_id):
    """Resetea completamente el estado de correo (borrador y enviado)."""
    doc = Documento.query.get_or_404(doc_id)
    doc.correo_borrador = False
    doc.correo_enviado = False
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/documento/<int:doc_id>/confirmar-correo', methods=['POST'])
@admin_required
def confirmar_correo(doc_id):
    """Confirma que el correo fue enviado desde Outlook (borrador → enviado)."""
    doc = Documento.query.get_or_404(doc_id)
    doc.correo_borrador = False
    doc.correo_enviado = True
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/cliente/<int:cliente_id>/exportar-excel')
def exportar_excel(cliente_id):
    """Genera un Excel con una hoja por proyecto del cliente."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    cliente = Cliente.query.get_or_404(cliente_id)
    wb = Workbook()
    wb.remove(wb.active)

    for proyecto in cliente.proyectos:
        nombre_hoja = proyecto.codigo[:31]
        ws = wb.create_sheet(title=nombre_hoja)

        columnas = ['Código', 'Rev.', 'Provisión', 'Título', 'Disciplina',
                    'Tipo de documento', 'Asignado a', 'Llegada', 'Devolución',
                    'Revisión', 'DMS', 'Ruta servidor', 'Comentarios']
        ws.append(columnas)

        header_fill = PatternFill('solid', fgColor='D9D9D9')
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

        for doc in proyecto.documentos:
            ws.append([
                doc.codigo,
                doc.revision,
                doc.provision if not proyecto.provision_unica else '',
                doc.titulo,
                doc.disciplina,
                doc.tipo_documento,
                doc.asignado_a,
                doc.fecha_llegada,
                doc.fecha_devolucion,
                doc.fecha_revision,
                'Sí' if doc.cargado_dms else 'No',
                doc.ruta_servidor,
                doc.comentarios,
            ])

        for col in ws.columns:
            max_len = max((len(str(c.value or '')) for c in col), default=0)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre_archivo = f"{cliente.nombre.replace(' ', '_')}.xlsx"
    return send_file(buf, as_attachment=True, download_name=nombre_archivo,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@bp.route('/proyecto/<int:proyecto_id>/generar-correos', methods=['POST'])
@admin_required
@local_file_ops_required
def generar_correos(proyecto_id):
    """Genera borradores de correo en Outlook para todos los docs pendientes del proyecto."""
    proyecto = Proyecto.query.get_or_404(proyecto_id)
    try:
        borradores = generar_borradores_proyecto(proyecto)
        return jsonify({'ok': True, 'borradores': borradores, 'total': len(borradores)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
