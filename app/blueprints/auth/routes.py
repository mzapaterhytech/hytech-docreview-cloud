from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
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
