# Hytech DocReview Cloud — Contexto del Proyecto

## Qué es esto

Es la **versión 2** de "Hytech DocReview" (la app original vive en la carpeta hermana
`../Hytech DocReview/` y **no se toca** — sigue siendo la instalación local de un solo
usuario). Esta carpeta es un fork que reutiliza modelos, servicios y templates de v1,
pero agrega **login, roles y una base de datos compartida en la nube** para que varias
personas (6-15) vean el mismo estado de documentos desde cualquier lado.

Para las reglas de negocio generales (regla crítica de nunca borrar nada del
servidor `T:\`, estructura de carpetas v1/v2, `reglas_codigo`, Módulos 1/2/3, etc.)
seguí valiendo todo lo que dice el `CLAUDE.md` de `../Hytech DocReview/` — acá solo se
documentan las diferencias.

## Qué cambia respecto a v1

- **Base de datos:** Postgres compartido (Neon, free tier) en vez de SQLite local por
  instalación. `DATABASE_URL` por variable de entorno (`.env`, nunca hardcodeado); si
  no está seteada cae a SQLite local solo para pruebas sin nube.
- **Login y roles:** modelo `Usuario` (`app/models.py`) con Flask-Login. Dos roles:
  - `admin`: gestiona clientes/proyectos/usuarios, importa PDFs, mueve al servidor,
    genera correos.
  - `revisor`: solo ve "Mis pendientes" (`/revision/mis-pendientes`) y tilda
    documentos asignados a él.
  El rol controla qué se puede **gestionar**, no quién puede **recibir** documentos:
  un admin también puede tener documentos asignados y usar "Mis pendientes".
- **Sin equipo por proyecto:** se eliminó `MiembroEquipo`. Las personas se cargan
  **una sola vez, globalmente**, en `/usuarios` (solo admin). `Usuario.iniciales` es
  **único en todo el sistema** — por eso cualquier documento de cualquier proyecto
  puede filtrarse de forma segura por `asignado_a == usuario.iniciales`.
- **Dos "modos" de la misma instancia**, controlados por `ENABLE_LOCAL_FILE_OPS`
  (`.env`, nunca en el hosting en la nube):
  - **Local (PC del admin, `ENABLE_LOCAL_FILE_OPS=1`):** tiene VPN + `T:\` montado.
    Se usa para Importar documentos, Mover al servidor y Generar correos — estas
    rutas están decoradas con `@local_file_ops_required` y devuelven 403 si la
    variable no está activa.
  - **Nube (Render, sin la variable):** siempre encendida, 24/7, independiente de que
    la PC del admin esté prendida. Ahí viven el dashboard, "Mis pendientes" y la
    gestión de usuarios/clientes/proyectos — nada que toque el filesystem local.
  Ambos contextos apuntan a la misma base compartida en Neon.
- **CSRF:** protegido con Flask-WTF (`CSRFProtect`). Los formularios tradicionales
  llevan `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`; las
  llamadas `fetch()` lo reciben automáticamente vía un wrapper global en
  `base.html` que agrega el header `X-CSRFToken` a todo `fetch` mutante (lee el
  token del `<meta name="csrf-token">` del `<head>`).
- **`revisado_por`:** nuevo campo en `Documento`, junto a `fecha_revision` (ya
  existía en v1). Al tildar "revisado" en `/revision/mis-pendientes`, se setea
  `fecha_revision` a hoy y `revisado_por` a las iniciales de quien tildó.

## Siembra del primer admin

No hay registro público. Se usa el comando CLI (una sola vez, desde la PC del admin,
apuntando al mismo `DATABASE_URL` que usará Render):

```
flask seed-admin --email admin@hytech.com --password "..." --nombre "Nombre" --iniciales XX
```

También acepta `ADMIN_SEED_EMAIL`/`ADMIN_SEED_PASSWORD` por variable de entorno en vez
de flags. Es idempotente: si el email ya existe, actualiza su contraseña y lo deja
como admin. El resto de usuarios se crea desde `/usuarios` ya logueado.

## Hosting gratuito

- **DB:** Neon (Postgres serverless gratis) — preferido sobre Supabase porque
  Supabase pausa el proyecto entero tras 7 días sin uso (requiere restore manual);
  Neon solo suspende el cómputo y lo retoma solo. Usar el connection string
  **pooled** (sufijo `-pooler`, PgBouncer) para no agotar conexiones del free tier.
- **App:** Render.com free web service, `gunicorn run:app -w 1` (ver `Procfile`). Se
  duerme tras ~15 min sin tráfico (cold start al despertar) — aceptable, no se pidió
  tiempo real.
- Variables de entorno en Render: `DATABASE_URL` (pooled de Neon), `SECRET_KEY`
  (generada, no la de desarrollo). `ENABLE_LOCAL_FILE_OPS` **no** se setea ahí.

## Convenciones

Las mismas que v1 (ver su `CLAUDE.md`): operaciones de archivo solo `mkdir`/
`shutil.copy2`, nunca `.Send()` en correos, migraciones con `ALTER TABLE` idempotente
en `create_app()` (no Alembic), logging con `logging`, mensajes de error claros sin
stack traces en la UI.
