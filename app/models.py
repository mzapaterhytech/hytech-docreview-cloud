import json
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

ROLES = ['admin', 'revisor']

DISCIPLINAS = ['Civil', 'Ductos', 'Interdisciplinaria']

TIPOS_DOCUMENTO = [
    'FUNDACIONES',
    'ESTRUCTURAS',
    'LAY OUT',
    'REQUISICIONES',
    'MOVIMIENTO DE SUELO',
    'UNDERGROUND',
    'ESTUDIOS ESPECIALES',
    'ESPECIFICACIONES',
    'MEMORIAS DESCRIPTIVAS',
    'PAVIMENTOS Y CAMINOS',
    'ARQUITECTURA',
    'LISTAS',
]

MESES_ES = {
    1: '01-Enero', 2: '02-Febrero', 3: '03-Marzo', 4: '04-Abril',
    5: '05-Mayo', 6: '06-Junio', 7: '07-Julio', 8: '08-Agosto',
    9: '09-Septiembre', 10: '10-Octubre', 11: '11-Noviembre', 12: '12-Diciembre',
}


class Cliente(db.Model):
    __tablename__ = 'cliente'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False, unique=True)

    proyectos = db.relationship('Proyecto', backref='cliente', lazy=True,
                                order_by='Proyecto.nombre')

    def __repr__(self):
        return f'<Cliente {self.nombre}>'


class Proyecto(db.Model):
    __tablename__ = 'proyecto'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    codigo = db.Column(db.String(50), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)

    provision_unica = db.Column(db.Boolean, default=False)
    regla_provision = db.Column(db.String(100), default='')
    _mapeo_provision = db.Column('mapeo_provision', db.Text, default='{}')

    _reglas_tipo_documento = db.Column('reglas_tipo_documento', db.Text, default='{}')
    _tipos_habilitados = db.Column('tipos_documento_habilitados', db.Text, default='[]')
    _reglas_codigo = db.Column('reglas_codigo', db.Text, default='{}')

    template_correo = db.Column(db.Text, default='')
    ruta_servidor_base = db.Column(db.String(500), default='')
    estructura_servidor = db.Column(db.String(10), default='v1')
    alcance_v2 = db.Column(db.String(20), default='')

    documentos = db.relationship('Documento', backref='proyecto', lazy=True,
                                 order_by='Documento.fecha_llegada.desc()')

    @property
    def mapeo_provision(self):
        return json.loads(self._mapeo_provision or '{}')

    @mapeo_provision.setter
    def mapeo_provision(self, value):
        self._mapeo_provision = json.dumps(value, ensure_ascii=False)

    @property
    def reglas_tipo_documento(self):
        return json.loads(self._reglas_tipo_documento or '{}')

    @reglas_tipo_documento.setter
    def reglas_tipo_documento(self, value):
        self._reglas_tipo_documento = json.dumps(value, ensure_ascii=False)

    @property
    def tipos_documento_habilitados(self):
        return json.loads(self._tipos_habilitados or '[]')

    @tipos_documento_habilitados.setter
    def tipos_documento_habilitados(self, value):
        self._tipos_habilitados = json.dumps(value, ensure_ascii=False)

    @property
    def reglas_codigo(self):
        return json.loads(self._reglas_codigo or '{}')

    @reglas_codigo.setter
    def reglas_codigo(self, value):
        self._reglas_codigo = json.dumps(value, ensure_ascii=False)

    @property
    def provisiones_disponibles(self):
        """Lista de valores de provisión configurados para este proyecto."""
        reglas = self.reglas_codigo
        if reglas and 'segmentos' in reglas:
            for seg in reglas['segmentos']:
                if seg.get('campo') == 'provision' and 'mapeo' in seg:
                    return list(seg['mapeo'].values())
        mapeo = self.mapeo_provision
        if mapeo:
            return list(mapeo.values())
        return []

    def to_config_dict(self):
        """Devuelve la configuración del proyecto como dict para usar en los servicios."""
        return {
            'nombre': self.nombre,
            'codigo': self.codigo,
            'provision_unica': self.provision_unica,
            'regla_provision': self.regla_provision,
            'mapeo_provision': self.mapeo_provision,
            'reglas_tipo_documento': self.reglas_tipo_documento,

            'reglas_codigo': self.reglas_codigo,
        }

    def __repr__(self):
        return f'<Proyecto {self.codigo} - {self.nombre}>'


class Usuario(UserMixin, db.Model):
    """Persona con acceso al dashboard. Global (no por proyecto): sus iniciales son
    únicas en todo el sistema y sirven para asignarle documentos en cualquier
    proyecto. El rol controla qué puede GESTIONAR (admin: importar, mover a
    servidor, configurar, crear usuarios); cualquier usuario activo —sea admin o
    revisor— puede recibir documentos asignados y verlos en "Mis pendientes"."""
    __tablename__ = 'usuario'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    iniciales = db.Column(db.String(10), nullable=False, unique=True)
    rol = db.Column(db.String(20), nullable=False, default='revisor')
    activo = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def es_admin(self):
        return self.rol == 'admin'

    def __repr__(self):
        return f'<Usuario {self.iniciales} ({self.rol})>'


class Documento(db.Model):
    __tablename__ = 'documento'

    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('proyecto.id'), nullable=False)

    provision = db.Column(db.String(50), default='')
    codigo = db.Column(db.String(200), nullable=False)
    revision = db.Column(db.String(20), default='')
    titulo = db.Column(db.String(500), default='')
    disciplina = db.Column(db.String(50), default='')
    tipo_documento = db.Column(db.String(100), default='')
    asignado_a = db.Column(db.String(10), default='')

    fecha_llegada = db.Column(db.String(10), nullable=False)   # ISO 8601: YYYY-MM-DD
    fecha_devolucion = db.Column(db.String(10), default='')
    fecha_revision = db.Column(db.String(10), default='')
    revisado_por = db.Column(db.String(10), default='')  # iniciales de quien tildó "revisado"

    cargado_dms = db.Column(db.Boolean, default=False)
    ruta_servidor = db.Column(db.String(500), default='')
    correo_borrador = db.Column(db.Boolean, default=False)
    correo_enviado = db.Column(db.Boolean, default=False)
    comentarios = db.Column(db.Text, default='')

    archivo_local = db.Column(db.String(500), default='')

    @property
    def pendiente(self):
        return not self.cargado_dms

    def __repr__(self):
        return f'<Documento {self.codigo} Rev.{self.revision}>'
