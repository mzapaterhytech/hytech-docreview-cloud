import os
import click


def register_cli(app):
    @app.cli.command('seed-admin')
    @click.option('--email', default=None, help='Email del admin (o ADMIN_SEED_EMAIL en .env).')
    @click.option('--password', default=None, help='Contraseña (o ADMIN_SEED_PASSWORD en .env).')
    @click.option('--nombre', default='Administrador', help='Nombre completo.')
    @click.option('--iniciales', default='ADM', help='Iniciales.')
    def seed_admin(email, password, nombre, iniciales):
        """Crea (o actualiza) un usuario admin. Pensado para correrse UNA VEZ,
        desde la PC del administrador, apuntando al mismo DATABASE_URL que usa
        la instancia deployada — así no hace falta shell en el hosting ni dejar
        credenciales de admin como variable de entorno permanente."""
        from app import db
        from app.models import Usuario

        email = (email or os.environ.get('ADMIN_SEED_EMAIL', '')).strip().lower()
        password = password or os.environ.get('ADMIN_SEED_PASSWORD', '')

        if not email or not password:
            click.echo('Falta email o password (pasalos por --email/--password o '
                       'ADMIN_SEED_EMAIL/ADMIN_SEED_PASSWORD en el .env).')
            return

        usuario = Usuario.query.filter_by(email=email).first()
        if usuario:
            usuario.set_password(password)
            usuario.rol = 'admin'
            usuario.activo = True
            click.echo(f'Usuario admin existente actualizado: {email}')
        else:
            iniciales_norm = iniciales.strip().upper()
            if Usuario.query.filter_by(iniciales=iniciales_norm).first():
                click.echo(f'Ya existe un usuario con iniciales "{iniciales_norm}". '
                           'Pasá otras con --iniciales.')
                return
            usuario = Usuario(
                email=email,
                nombre=nombre,
                iniciales=iniciales_norm,
                rol='admin',
                activo=True,
            )
            usuario.set_password(password)
            db.session.add(usuario)
            click.echo(f'Usuario admin creado: {email}')

        db.session.commit()
