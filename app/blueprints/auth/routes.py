from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import Usuario

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and usuario.activo and usuario.check_password(password):
            login_user(usuario)
            siguiente = request.args.get('next')
            return redirect(siguiente or url_for('dashboard.index'))
        flash('Email o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html')


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@bp.route('/invitar/<token>', methods=['GET', 'POST'])
def aceptar_invitacion(token):
    usuario = Usuario.query.filter_by(invite_token=token).first()
    if not usuario or not usuario.invite_expires:
        flash('El link de invitación no es válido.', 'danger')
        return redirect(url_for('auth.login'))
    if datetime.utcnow() > datetime.fromisoformat(usuario.invite_expires):
        flash('El link de invitación expiró. Pedile uno nuevo al administrador.', 'warning')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirmar = request.form.get('confirmar', '')
        if len(password) < 8:
            flash('La contraseña debe tener al menos 8 caracteres.', 'warning')
        elif password != confirmar:
            flash('Las contraseñas no coinciden.', 'warning')
        else:
            usuario.set_password(password)
            usuario.invite_token = None
            usuario.invite_expires = None
            usuario.activo = True
            db.session.commit()
            login_user(usuario)
            flash(f'Bienvenido/a, {usuario.nombre}. Ya podés usar el sistema.', 'success')
            return redirect(url_for('dashboard.index'))

    return render_template('auth/aceptar_invitacion.html', usuario=usuario)
