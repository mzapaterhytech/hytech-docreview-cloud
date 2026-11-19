import json
import logging
from pathlib import Path

from flask import (Blueprint, abort, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user

from app import db
from app.decorators import local_file_ops_required
from app.models import TIPOS_DOCUMENTO, Cliente, Proyecto
from app.services.file_server_service import (DISCIPLINA_PATRON,
                                              encontrar_carpeta_disciplina,
                                              encontrar_carpeta_tipo)

logger = logging.getLogger(__name__)
bp = Blueprint('config', __name__)


@bp.before_request
def _solo_admin():
    """Todo este blueprint (gestión de clientes/proyectos) es exclusivo de admin."""
    if not current_user.is_authenticated or not current_user.es_admin:
        abort(403)


# ──────────────────────────────────────────────────────────
# Clientes
# ──────────────────────────────────────────────────────────

@bp.route('/')
def index():
    clientes = Cliente.query.order_by(Cliente.nombre).all()
    return render_template('config_proyecto/index.html', clientes=clientes)


@bp.route('/cliente/nuevo', methods=['GET', 'POST'])
def cliente_nuevo():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            flash('El nombre del cliente es obligatorio.', 'warning')
            return render_template('config_proyecto/cliente_form.html', cliente=None)
        if Cliente.query.filter_by(nombre=nombre).first():
            flash(f'Ya existe un cliente con el nombre "{nombre}".', 'danger')
            return render_template('config_proyecto/cliente_form.html', cliente=None)
        db.session.add(Cliente(nombre=nombre))
        db.session.commit()
        flash(f'Cliente "{nombre}" creado correctamente.', 'success')
        return redirect(url_for('config.index'))
    return render_template('config_proyecto/cliente_form.html', cliente=None)


@bp.route('/cliente/<int:cliente_id>/editar', methods=['GET', 'POST'])
def cliente_editar(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            flash('El nombre es obligatorio.', 'warning')
        else:
            cliente.nombre = nombre
            db.session.commit()
            flash('Cliente actualizado.', 'success')
            return redirect(url_for('config.index'))
    return render_template('config_proyecto/cliente_form.html', cliente=cliente)


# ──────────────────────────────────────────────────────────
# Proyectos
# ──────────────────────────────────────────────────────────

@bp.route('/proyecto/nuevo', methods=['GET', 'POST'])
def proyecto_nuevo():
    clientes = Cliente.query.order_by(Cliente.nombre).all()
    if request.method == 'POST':
        proyecto = _proyecto_desde_form(None)
        if proyecto:
            db.session.add(proyecto)
            db.session.commit()
            flash(f'Proyecto "{proyecto.nombre}" creado.', 'success')
            return redirect(url_for('config.index'))
    todos_proyectos = Proyecto.query.order_by(Proyecto.nombre).all()
    return render_template(
        'config_proyecto/proyecto_form.html',
        proyecto=None,
        clientes=clientes,
        tipos_disponibles=TIPOS_DOCUMENTO,
        todos_proyectos=todos_proyectos,
    )


@bp.route('/proyecto/<int:proyecto_id>/eliminar', methods=['POST'])
def proyecto_eliminar(proyecto_id):
    proyecto = Proyecto.query.get_or_404(proyecto_id)
    nombre = proyecto.nombre
    from app.models import Documento
    Documento.query.filter_by(proyecto_id=proyecto_id).delete()
    db.session.delete(proyecto)
    db.session.commit()
    flash(f'Proyecto "{nombre}" eliminado.', 'success')
    return redirect(url_for('config.index'))


@bp.route('/proyecto/<int:proyecto_id>/editar', methods=['GET', 'POST'])
def proyecto_editar(proyecto_id):
    proyecto = Proyecto.query.get_or_404(proyecto_id)
    clientes = Cliente.query.order_by(Cliente.nombre).all()
    if request.method == 'POST':
        actualizado = _proyecto_desde_form(proyecto)
        if actualizado:
            db.session.commit()
            flash('Proyecto actualizado.', 'success')
            return redirect(url_for('config.index'))
    return render_template(
        'config_proyecto/proyecto_form.html',
        proyecto=proyecto,
        clientes=clientes,
        tipos_disponibles=TIPOS_DOCUMENTO,
        todos_proyectos=[],
    )


# ──────────────────────────────────────────────────────────
# Helpers privados
# ──────────────────────────────────────────────────────────

@bp.route('/proyecto/<int:proyecto_id>/crear-carpetas-provision', methods=['POST'])
@local_file_ops_required
def crear_carpetas_provision(proyecto_id):
    """
    Crea en el servidor las carpetas de provisión dentro de cada carpeta
    de tipo de documento, para las provisiones seleccionadas.
    """
    proyecto = Proyecto.query.get_or_404(proyecto_id)
    provisiones_sel = request.json.get('provisiones', [])

    if not provisiones_sel:
        return jsonify({'error': 'No se seleccionaron provisiones.'}), 400

    base = Path(proyecto.ruta_servidor_base)
    drive = Path(base.anchor)
    if not drive.exists():
        return jsonify({'error': f'No se puede acceder al servidor ({drive}). Verificá la VPN.'}), 400
    if not base.exists():
        return jsonify({'error': f'La ruta base no existe: {base}'}), 400

    creadas = []
    existentes = []
    errores = []

    for disciplina, patron in DISCIPLINA_PATRON.items():
        try:
            carpeta_disc = encontrar_carpeta_disciplina(base, disciplina)
        except ValueError:
            continue  # esa disciplina no existe en este proyecto, se omite

        for tipo in proyecto.tipos_documento_habilitados or TIPOS_DOCUMENTO:
            try:
                carpeta_tipo = encontrar_carpeta_tipo(carpeta_disc, tipo)
            except ValueError:
                continue  # ese tipo no existe aún, se omite

            for prov in provisiones_sel:
                carpeta_prov = carpeta_tipo / prov
                try:
                    if carpeta_prov.exists():
                        existentes.append(str(carpeta_prov))
                    else:
                        carpeta_prov.mkdir()
                        creadas.append(str(carpeta_prov))
                except OSError as e:
                    errores.append(f'{carpeta_prov}: {e}')

    return jsonify({'creadas': creadas, 'existentes': existentes, 'errores': errores})


@bp.route('/proyecto/<int:proyecto_id>/config-json')
def proyecto_config_json(proyecto_id):
    """Devuelve la configuración copiable de un proyecto en JSON (para clonar)."""
    p = Proyecto.query.get_or_404(proyecto_id)
    return jsonify({
        'reglas_tipo_documento': p.reglas_tipo_documento,
        'reglas_codigo': p.reglas_codigo,
        'ruta_servidor_base': p.ruta_servidor_base,
        'template_correo': p.template_correo,
    })


def _proyecto_desde_form(proyecto: Proyecto | None) -> Proyecto | None:
    """
    Lee los campos del formulario y actualiza (o crea) un objeto Proyecto.
    Devuelve None si hay errores de validación.
    """
    nombre = request.form.get('nombre', '').strip()
    codigo = request.form.get('codigo', '').strip()
    cliente_id = request.form.get('cliente_id', type=int)

    if not nombre or not codigo or not cliente_id:
        flash('Nombre, código y cliente son obligatorios.', 'warning')
        return None

    if proyecto is None:
        proyecto = Proyecto()

    proyecto.nombre = nombre
    proyecto.codigo = codigo
    proyecto.cliente_id = cliente_id
    # provision_unica se infiere automáticamente más abajo, tras parsear reglas_codigo

    regla_tipo = request.form.get('regla_tipo', '')
    regla_n = request.form.get('regla_n', '').strip()
    regla_inicio = request.form.get('regla_inicio', '').strip()
    regla_fin = request.form.get('regla_fin', '').strip()
    if regla_tipo == 'primeros_N' and regla_n.isdigit():
        proyecto.regla_provision = f'primeros_{regla_n}_caracteres'
    elif regla_tipo == 'segmento_N' and regla_n.isdigit():
        proyecto.regla_provision = f'segmento_{regla_n}'
    elif regla_tipo == 'chars_X_Y' and regla_inicio.isdigit() and regla_fin.isdigit():
        proyecto.regla_provision = f'chars_{regla_inicio}_{regla_fin}'
    else:
        proyecto.regla_provision = ''

    claves = request.form.getlist('prov_clave[]')
    nombres_prov = request.form.getlist('prov_nombre[]')
    mapeo = {}
    for k, n in zip(claves, nombres_prov):
        k, n = k.strip(), n.strip()
        if k and n:
            mapeo[k] = n
    proyecto.mapeo_provision = mapeo

    proyecto.ruta_servidor_base = request.form.get('ruta_servidor_base', '').strip()
    proyecto.estructura_servidor = request.form.get('estructura_servidor', 'v1')
    proyecto.alcance_v2 = request.form.get('alcance_v2', '').strip()
    proyecto.template_correo = request.form.get('template_correo', '').strip()

    # Reglas tipo documento: tabla dinámica (patron_N / tipo_N)
    reglas = {}
    patrones = request.form.getlist('patron[]')
    tipos = request.form.getlist('tipo_regla[]')
    for p, t in zip(patrones, tipos):
        p, t = p.strip(), t.strip()
        if p and t:
            reglas[p] = t
    proyecto.reglas_tipo_documento = reglas

    # Nueva estructura de código por segmentos
    reglas_raw = request.form.get('reglas_codigo', '{}')
    try:
        proyecto.reglas_codigo = json.loads(reglas_raw)
    except (ValueError, TypeError):
        proyecto.reglas_codigo = {}

    # provision_unica: True si ningún segmento está mapeado a 'provision'
    segmentos = proyecto.reglas_codigo.get('segmentos', [])
    proyecto.provision_unica = not any(s.get('campo') == 'provision' for s in segmentos)

    return proyecto
