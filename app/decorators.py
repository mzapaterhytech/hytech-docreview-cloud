from functools import wraps
from flask import current_app, abort
from flask_login import current_user


def admin_required(view):
    """Exige rol admin. El login en sí ya lo exige el before_request global."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.es_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def local_file_ops_required(view):
    """Exige que esta instancia corra con acceso local a T:\\ (ENABLE_LOCAL_FILE_OPS=1
    en el .env). No es un chequeo de rol: aunque sea admin, si esta instancia está
    deployada en la nube sin VPN, estas operaciones no tienen sentido."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_app.config.get('ENABLE_LOCAL_FILE_OPS'):
            abort(403)
        return view(*args, **kwargs)
    return wrapped
