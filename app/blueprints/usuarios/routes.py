from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import current_user
from app import db
from app.models import ROLES, Usuario

bp = Blueprint('usuarios', __name__)


@bp.before_request
def _solo_admin():
    """Gestión de usuarios es exclusiva de admin."""
    if not current_user.is_authenticated or not current_user.es_admin:
        abort(403)


@bp.route('/')
def index():
    usuarios = Usuario.query.order_by(Usuario.iniciales).all()
    return render_template('usuarios/index.html', usuarios=usuarios)


@bp.route('/nuevo', methods=['GET', 'POST'])
def nuevo():
    if request.method == 'POST':
        usuario = _usuario_desde_form(None)
        if usuario:
            db.session.add(usuario)
            db.session.commit()
            flash(f'Usuario "{usuario.nombre}" creado.', 'success')
            return redirect(url_for('usuarios.index'))
    return render_template('usuarios/form.html', usuario=None, roles=ROLES)


@bp.route('/<int:usuario_id>/editar', methods=['GET', 'POST'])
def editar(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    if request.method == 'POST':
        actualizado = _usuario_desde_form(usuario)
        if actualizado:
            db.session.commit()
            flash('Usuario actualizado.', 'success')
            return redirect(url_for('usuarios.index'))
    return render_template('usuarios/form.html', usuario=usuario, roles=ROLES)


def _usuario_desde_form(usuario: Usuario | None) -> Usuario | None:
    """Lee los campos del formulario y actualiza (o crea) un Usuario.
    Devuelve None si hay errores de validación."""
    email = request.form.get('email', '').strip().lower()
    nombre = request.form.get('nombre', '').strip()
    iniciales = request.form.get('iniciales', '').strip().upper()
    rol = request.form.get('rol', 'revisor')
    activo = request.form.get('activo') == 'on'
    password = request.form.get('password', '')

    if not email or not nombre or not iniciales:
        flash('Email, nombre e iniciales son obligatorios.', 'warning')
        return None
    if rol not in ROLES:
        rol = 'revisor'

    existente_email = Usuario.query.filter_by(email=email).first()
    if existente_email and (usuario is None or existente_email.id != usuario.id):
        flash(f'Ya existe un usuario con el email "{email}".', 'danger')
        return None
    existente_iniciales = Usuario.query.filter_by(iniciales=iniciales).first()
    if existente_iniciales and (usuario is None or existente_iniciales.id != usuario.id):
        flash(f'Ya existe un usuario con las iniciales "{iniciales}".', 'danger')
        return None

    if usuario is None:
        if not password:
            flash('La contraseña es obligatoria para un usuario nuevo.', 'warning')
            return None
        usuario = Usuario()

    usuario.email = email
    usuario.nombre = nombre
    usuario.iniciales = iniciales
    usuario.rol = rol
    usuario.activo = activo
    if password:
        usuario.set_password(password)

    return usuario
