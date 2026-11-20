import os
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

BASE_DIR = Path(__file__).parent.parent
PREVIEWS_DIR = BASE_DIR / 'previews'
BACKUPS_DIR = BASE_DIR / 'backups'


def create_app():
    app = Flask(__name__)

    instance_dir = BASE_DIR / 'instance'
    instance_dir.mkdir(exist_ok=True)
    PREVIEWS_DIR.mkdir(exist_ok=True)
    BACKUPS_DIR.mkdir(exist_ok=True)

    database_url = os.environ.get('DATABASE_URL', f'sqlite:///{instance_dir / "docreview.db"}')
    # Render/Heroku-style URLs a veces vienen como postgres:// — SQLAlchemy 2.x requiere postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    # Forzar psycopg2 como driver (evita que SQLAlchemy busque psycopg v3)
    if database_url.startswith('postgresql://') and '+' not in database_url.split('://')[0]:
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'hytech-docreview-cloud-dev-only')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    if database_url.startswith('postgresql://'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_size': 2,
            'max_overflow': 2,
            'pool_pre_ping': True,
            'pool_recycle': 280,
        }
    # Solo presente (y en '1') en el .env local del administrador, con VPN a T:\
    app.config['ENABLE_LOCAL_FILE_OPS'] = os.environ.get('ENABLE_LOCAL_FILE_OPS', '0') == '1'

    db.init_app(app)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Iniciá sesión para continuar.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import Usuario
        return db.session.get(Usuario, int(user_id))

    from app.blueprints.auth.routes import bp as auth_bp
    from app.blueprints.dashboard.routes import bp as dashboard_bp
    from app.blueprints.importacion.routes import bp as importacion_bp
    from app.blueprints.config_proyecto.routes import bp as config_bp
    from app.blueprints.revision.routes import bp as revision_bp
    from app.blueprints.usuarios.routes import bp as usuarios_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(importacion_bp, url_prefix='/importacion')
    app.register_blueprint(config_bp, url_prefix='/config')
    app.register_blueprint(revision_bp, url_prefix='/revision')
    app.register_blueprint(usuarios_bp, url_prefix='/usuarios')

    from flask_login import current_user

    @app.before_request
    def exigir_login():
        from flask import request
        if request.blueprint in ('auth', None) or request.endpoint == 'static':
            return None
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        return None

    @app.route('/')
    def index():
        return redirect(url_for('dashboard.index'))

    # Exponer enumerate y date en todos los templates
    from datetime import date as _date
    from app.services.calendario import dias_habiles_hasta as _dias_habiles_hasta
    app.jinja_env.globals['enumerate'] = enumerate
    app.jinja_env.globals['today'] = lambda: _date.today().isoformat()
    app.jinja_env.globals['dias_habiles_hasta'] = lambda fecha_str: (
        _dias_habiles_hasta(_date.today(), _date.fromisoformat(fecha_str))
        if fecha_str else None
    )

    from app.cli import register_cli
    register_cli(app)

    with app.app_context():
        db.create_all()
        from sqlalchemy import text
        with db.engine.connect() as conn:
            for stmt in [
                "ALTER TABLE proyecto ADD COLUMN regla_provision TEXT DEFAULT ''",
                "ALTER TABLE proyecto ADD COLUMN provision_unica BOOLEAN DEFAULT 0",
                "ALTER TABLE proyecto ADD COLUMN mapeo_provision TEXT DEFAULT '{}'",
                "ALTER TABLE proyecto ADD COLUMN reglas_tipo_documento TEXT DEFAULT '{}'",
                "ALTER TABLE proyecto ADD COLUMN tipos_documento_habilitados TEXT DEFAULT '[]'",
                "ALTER TABLE proyecto ADD COLUMN reglas_codigo TEXT DEFAULT '{}'",
                "ALTER TABLE proyecto ADD COLUMN template_correo TEXT DEFAULT ''",
                "ALTER TABLE proyecto ADD COLUMN ruta_servidor_base TEXT DEFAULT ''",
                "ALTER TABLE documento ADD COLUMN correo_borrador BOOLEAN DEFAULT 0",
                "ALTER TABLE documento ADD COLUMN correo_enviado BOOLEAN DEFAULT 0",
                "ALTER TABLE documento ADD COLUMN comentarios TEXT DEFAULT ''",
                "ALTER TABLE documento ADD COLUMN archivo_local TEXT DEFAULT ''",
                "ALTER TABLE proyecto ADD COLUMN estructura_servidor TEXT DEFAULT 'v1'",
                "ALTER TABLE proyecto ADD COLUMN alcance_v2 TEXT DEFAULT ''",
                "ALTER TABLE documento ADD COLUMN revisado_por TEXT DEFAULT ''",
            ]:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                except Exception:
                    conn.rollback()  # columna ya existe (o falla no fatal)

    return app
