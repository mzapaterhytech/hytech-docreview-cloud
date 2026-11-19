from datetime import date
from flask import Blueprint, render_template, abort, jsonify
from flask_login import login_required, current_user
from app.models import Documento
from app import db

bp = Blueprint('revision', __name__)


def _query_pendientes(usuario):
    return (
        Documento.query
        .filter(Documento.asignado_a == usuario.iniciales, Documento.cargado_dms == False)
        .order_by(Documento.fecha_devolucion)
        .all()
    )


@bp.route('/mis-pendientes')
@login_required
def mis_pendientes():
    documentos = _query_pendientes(current_user)
    return render_template('revision/pendientes.html', documentos=documentos)


@bp.route('/documento/<int:doc_id>/marcar-revisado', methods=['POST'])
@login_required
def marcar_revisado(doc_id):
    doc = Documento.query.get_or_404(doc_id)
    if doc.asignado_a != current_user.iniciales:
        abort(403)

    if doc.fecha_revision:
        doc.fecha_revision = ''
        doc.revisado_por = ''
    else:
        doc.fecha_revision = date.today().isoformat()
        doc.revisado_por = current_user.iniciales
    db.session.commit()

    return jsonify({'fecha_revision': doc.fecha_revision, 'revisado_por': doc.revisado_por})
