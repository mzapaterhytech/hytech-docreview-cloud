import logging
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

from flask import (Blueprint, Response, flash, jsonify, redirect,
                   render_template, request, send_file, url_for)

from app import PREVIEWS_DIR, db
from app.decorators import admin_required, local_file_ops_required
from app.models import DISCIPLINAS, TIPOS_DOCUMENTO, Documento, Proyecto, Usuario
from app.services.calendario import sumar_dias_habiles
from app.services.extractor import extraer_metadatos_nombre
from app.services.pdf_preview import extraer_titulo_pdf, generar_preview

logger = logging.getLogger(__name__)
bp = Blueprint('importacion', __name__)


def _archivo_en_uso(path: Path) -> bool:
    """Devuelve True si el archivo está siendo usado por otro proceso."""
    try:
        with open(path, 'r+b'):
            return False
    except PermissionError:
        return True
    except Exception:
        return False


@bp.route('/')
@admin_required
@local_file_ops_required
def index():
    """Pantalla de selección de carpeta padre."""
    return render_template('importacion/index.html')


@bp.route('/folder-picker')
@admin_required
@local_file_ops_required
def folder_picker():
    """Abre un diálogo de Windows para seleccionar carpeta (requiere tkinter)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title='Seleccionar carpeta principal')
        root.destroy()
        return jsonify({'folder': folder or ''})
    except Exception as exc:
        logger.warning("folder-picker no disponible: %s", exc)
        return jsonify({'folder': '', 'error': str(exc)})


@bp.route('/preview-img/<filename>')
def preview_img(filename):
    """Sirve una imagen de previsualización generada."""
    safe_name = Path(filename).name
    img_path = PREVIEWS_DIR / safe_name
    if not img_path.exists():
        return Response(status=404)
    return send_file(str(img_path), mimetype='image/png')


@bp.route('/scan', methods=['POST'])
@admin_required
@local_file_ops_required
def scan():
    """
    Escanea las subcarpetas de la carpeta indicada.
    Cada subcarpeta debe llamarse como el código o nombre de un proyecto.
    Genera un grupo por proyecto con sus documentos.
    """
    carpeta = request.form.get('carpeta', '').strip()
    carpeta_path = Path(carpeta)

    if not carpeta or not carpeta_path.exists() or not carpeta_path.is_dir():
        flash('La carpeta no existe o no es válida. Verificá la ruta.', 'danger')
        return redirect(url_for('importacion.index'))

    # Construir índice de proyectos: código (lower) → proyecto, nombre (lower) → proyecto
    todos_proyectos = Proyecto.query.all()
    idx_por_codigo = {p.codigo.strip().lower(): p for p in todos_proyectos}
    idx_por_nombre = {p.nombre.strip().lower(): p for p in todos_proyectos}

    hoy = date.today()
    fecha_dev = sumar_dias_habiles(hoy, 5)

    grupos = []       # [{'proyecto': obj, 'carpeta': str, 'docs': [...]}]
    sin_proyecto = [] # nombres de subcarpetas sin match

    subcarpetas = sorted([s for s in carpeta_path.iterdir() if s.is_dir()])

    if not subcarpetas:
        flash('La carpeta seleccionada no tiene subcarpetas. '
              'Cada subcarpeta debe llamarse como el código o nombre de un proyecto.', 'warning')
        return redirect(url_for('importacion.index'))

    for subcarpeta in subcarpetas:
        nombre_sub = subcarpeta.name.strip().lower()
        proyecto = idx_por_codigo.get(nombre_sub) or idx_por_nombre.get(nombre_sub)

        if proyecto is None:
            sin_proyecto.append(subcarpeta.name)
            continue

        pdfs = sorted(subcarpeta.glob('*.pdf'))
        if not pdfs:
            continue

        config = proyecto.to_config_dict()
        tipos = TIPOS_DOCUMENTO

        docs = []
        for pdf_path in pdfs:
            meta = extraer_metadatos_nombre(pdf_path.name, config)
            meta['titulo'] = extraer_titulo_pdf(str(pdf_path))
            # Solo generar preview del rótulo si no se pudo leer el título automáticamente
            meta['preview_file'] = None if meta['titulo'] else generar_preview(str(pdf_path), PREVIEWS_DIR)
            meta['archivo_original'] = str(pdf_path)
            meta['fecha_llegada'] = hoy.isoformat()
            meta['fecha_devolucion'] = fecha_dev.isoformat()
            docs.append(meta)

        grupos.append({
            'proyecto': proyecto,
            'carpeta': str(subcarpeta),
            'docs': docs,
            'tipos': tipos,
        })

    if not grupos and not sin_proyecto:
        flash('No se encontraron PDFs en ninguna subcarpeta.', 'warning')
        return redirect(url_for('importacion.index'))

    usuarios = Usuario.query.filter_by(activo=True).order_by(Usuario.iniciales).all()

    return render_template(
        'importacion/preview.html',
        grupos=grupos,
        sin_proyecto=sin_proyecto,
        disciplinas=DISCIPLINAS,
        usuarios=usuarios,
    )


@bp.route('/confirmar', methods=['POST'])
@admin_required
@local_file_ops_required
def confirmar():
    """Guarda los documentos confirmados y mueve los archivos a subcarpeta Backup/."""
    total_grupos = request.form.get('total_grupos', type=int, default=0)
    archivos_importados = []
    cliente_id = None
    guardados = 0

    # Recolectar primero todos los archivos a importar para verificar bloqueos
    for g in range(total_grupos):
        total_docs = request.form.get(f'total_{g}', type=int, default=0)
        for i in range(total_docs):
            if not request.form.get(f'incluir_{g}_{i}'):
                continue
            archivo_path_str = request.form.get(f'archivo_original_{g}_{i}', '').strip()
            if archivo_path_str:
                archivos_importados.append(Path(archivo_path_str))

    # Verificar que ningún archivo esté abierto ANTES de guardar nada
    archivos_en_uso = [p for p in archivos_importados if p.exists() and _archivo_en_uso(p)]
    if archivos_en_uso:
        nombres = ', '.join(p.name for p in archivos_en_uso)
        flash(
            f'Importación cancelada. Los siguientes archivos están abiertos: {nombres}. '
            f'Cerrá los documentos y volvé a intentarlo.',
            'danger'
        )
        return redirect(url_for('importacion.index'))

    for g in range(total_grupos):
        proyecto_id = request.form.get(f'proyecto_id_{g}', type=int)
        if not proyecto_id:
            continue
        proyecto = Proyecto.query.get(proyecto_id)
        if not proyecto:
            continue
        cliente_id = proyecto.cliente_id

        total_docs = request.form.get(f'total_{g}', type=int, default=0)
        for i in range(total_docs):
            if not request.form.get(f'incluir_{g}_{i}'):
                continue

            archivo_path_str = request.form.get(f'archivo_original_{g}_{i}', '').strip()
            doc = Documento(
                proyecto_id=proyecto_id,
                codigo=request.form.get(f'codigo_{g}_{i}', '').strip(),
                revision=request.form.get(f'revision_{g}_{i}', '').strip(),
                provision=request.form.get(f'provision_{g}_{i}', '').strip(),
                titulo=request.form.get(f'titulo_{g}_{i}', '').strip(),
                disciplina=request.form.get(f'disciplina_{g}_{i}', '').strip(),
                tipo_documento=request.form.get(f'tipo_documento_{g}_{i}', '').strip(),
                asignado_a=request.form.get(f'asignado_a_{g}_{i}', '').strip(),
                fecha_llegada=request.form.get(f'fecha_llegada_{g}_{i}', date.today().isoformat()),
                fecha_devolucion=request.form.get(f'fecha_devolucion_{g}_{i}', '').strip(),
                comentarios=request.form.get(f'comentarios_{g}_{i}', '').strip(),
                archivo_local=archivo_path_str,
                cargado_dms=False,
                correo_enviado=False,
            )
            db.session.add(doc)
            guardados += 1

    db.session.commit()

    # Mover archivos a subcarpeta Backup/ (ya verificado que ninguno está abierto)
    archivos_por_carpeta = defaultdict(list)
    for p in archivos_importados:
        if p.exists():
            archivos_por_carpeta[p.parent].append(p)

    for carpeta, archivos in archivos_por_carpeta.items():
        backup_dir = carpeta / 'Backup'
        backup_dir.mkdir(exist_ok=True)
        for archivo in archivos:
            dest = backup_dir / archivo.name
            try:
                shutil.copy2(str(archivo), str(dest))
                archivo.unlink()
            except Exception as exc:
                logger.warning("No se pudo mover %s a Backup: %s", archivo, exc)

    flash(f'{guardados} documento(s) importado(s) correctamente.', 'success')
    if cliente_id:
        return redirect(url_for('dashboard.cliente', cliente_id=cliente_id))
    return redirect(url_for('dashboard.index'))
