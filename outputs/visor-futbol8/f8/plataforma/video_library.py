"""Local originals and portable example intervals; never launches model inference."""
import copy
import hashlib
import json
import math
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from f8.core.paths import APP_DIR, WORK_DIR

EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi'}
SPLITS = {'desarrollo', 'reserva'}
CATEGORIES = {'balon', 'identidad', 'acciones', 'campo', 'otro'}


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    temporary.replace(path)


def signature(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def check_frames(path, metadata):
    """Sample decoding catches common incomplete copies, not all corrupt frames."""
    import cv2
    cap = cv2.VideoCapture(str(path))
    try:
        frames = metadata['source_frames']
        for index in sorted({0, frames // 2, max(0, frames - 1)}):
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, image = cap.read()
            if not ok or image is None:
                raise ValueError('No se pueden leer muestras del inicio, centro y final; comprueba la descarga.')
    finally:
        cap.release()


class VideoLibrary:
    def __init__(self, store, models_root=WORK_DIR, settle_seconds=10):
        self.store = store
        self.path = store.root / 'data' / 'video-library.json'
        self.lock = threading.RLock()
        self.models_root = Path(models_root)
        self.settle_seconds = settle_seconds
        self.settings = read_json(self.path, {})
        self.settings.setdefault('directory', '')
        self.settings.setdefault('season', f'temporada-{datetime.now().year}')
        self.settings.setdefault('checked', {})
        self.settings.setdefault('model_checks', {})
        self.thread = None
        self.result = {'state': 'idle', 'files': [], 'models': [], 'error': None}

    def catalogue_path(self):
        if not self.settings['directory']:
            raise ValueError('Configura primero la carpeta de vídeos.')
        return Path(self.settings['directory']) / 'ejemplos' / 'catalogo.json'

    def catalogue(self):
        value = read_json(self.catalogue_path(), {'version': 1, 'examples': []})
        if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('examples'), list):
            raise ValueError('El catálogo debe tener version: 1 y una lista examples.')
        return value

    def snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.result)
            result.update(directory=self.settings['directory'], season=self.settings['season'],
                          suggested_directory=str(Path.home() / 'Videos' / 'Futbol8Datos'))
            try:
                catalogue = self.catalogue() if self.settings['directory'] else {'version': 1, 'examples': []}
                registered = {(r['round'], r['half']): r for r in self.store.rows()}
                result['examples'] = []
                for example in catalogue['examples']:
                    item = self.validate_example(example)
                    row = registered.get((item['round'], item['half']))
                    item['available'] = bool(row and row['fingerprint'] == item['source_sha256']
                                             and Path(row['source']).is_file()
                                             and item['season'] == self.settings['season'])
                    result['examples'].append(item)
                result['catalogue_error'] = None
            except (OSError, ValueError, KeyError, TypeError) as error:
                result.update(examples=[], catalogue_error=str(error))
            return result

    def configure(self, value):
        directory = value.get('directory', '')
        season = value.get('season', '')
        if not isinstance(directory, str) or not directory.strip() or '://' in directory:
            raise ValueError('Indica una carpeta local o sincronizada; un enlace de Drive no es una ruta local.')
        root = Path(directory.strip()).expanduser()
        if not root.is_absolute():
            raise ValueError('La ruta de la carpeta debe ser absoluta.')
        if not isinstance(season, str) or not re.fullmatch(r'temporada-[0-9]{4}(?:-[0-9]{4})?', season):
            raise ValueError('Usa una temporada como temporada-2026 o temporada-2026-2027.')
        with self.lock:
            if self.result['state'] == 'scanning':
                raise ValueError('Espera a que termine la comprobación actual.')
            for folder in (root / 'originales' / season, root / 'ejemplos', root / 'resultados'):
                folder.mkdir(parents=True, exist_ok=True)
            self.settings.update(directory=str(root.resolve()), season=season)
            write_json(self.path, self.settings)
            if not self.catalogue_path().exists():
                write_json(self.catalogue_path(), {'version': 1, 'examples': []})
        return self.start_scan()

    def start_scan(self):
        with self.lock:
            if self.result['state'] != 'scanning' and self.settings['directory']:
                self.result.update(state='scanning', error=None, files=[])
                self.thread = threading.Thread(target=self.scan, daemon=True, name='video-library')
                self.thread.start()
            return self.snapshot()

    def scan(self):
        """Runs in a background thread; public for deterministic tests."""
        with self.lock:
            self.result.update(state='scanning', error=None, files=[])
        try:
            root = Path(self.settings['directory']).resolve()
            folder = root / 'originales' / self.settings['season']
            if not folder.is_dir():
                raise ValueError('Carpeta de temporada no disponible. Comprueba la unidad o la sincronización.')
            candidates = []
            for match_folder in sorted(folder.iterdir()):
                if not match_folder.is_dir():
                    continue
                for source in sorted(match_folder.iterdir()):
                    if not source.is_file():
                        continue
                    temporary = source.suffix.lower() in {'.part', '.tmp', '.crdownload', '.download'}
                    if source.suffix.lower() not in EXTENSIONS and not temporary:
                        continue
                    match = re.fullmatch(r'jornada-0*([1-9][0-9]{0,3})', match_folder.name, re.I)
                    name = re.sub(r'[ _-]', '', source.stem.lower())
                    half = 1 if name in {'primera', 'primeraparte', 'parte1'} else 2 if name in {'segunda', 'segundaparte', 'parte2'} else None
                    item = {'source': str(source), 'name': source.name, 'round': int(match[1]) if match else None,
                            'half': half, 'state': 'pending', 'message': ''}
                    candidates.append((source, item, temporary))
            slots = [(i['round'], i['half']) for _, i, _ in candidates]
            for source, item, temporary in candidates:
                try:
                    if not source.resolve().is_relative_to(root):
                        raise ValueError('El archivo enlazado está fuera de la biblioteca.')
                    if temporary:
                        item.update(state='incomplete', message='Copia o descarga temporal; espera a que termine.')
                    elif item['round'] is None or item['half'] is None:
                        item.update(state='needs_metadata', message='Usa jornada-002/primera.mp4 o segunda.mp4.')
                    elif slots.count((item['round'], item['half'])) > 1:
                        item.update(state='conflict', message='Hay varios archivos para esta jornada y parte; conserva uno.')
                    else:
                        self.check_video(source, item)
                except (OSError, ValueError, KeyError) as error:
                    item.update(state='error', message=str(error))
                with self.lock:
                    self.result['files'].append(item)
            models = self.check_models()
            with self.lock:
                self.result.update(state='complete', models=models, checked_at=datetime.now().isoformat(timespec='seconds'))
                write_json(self.path, self.settings)
        except Exception as error:
            with self.lock:
                self.result.update(state='failed', error=str(error))

    def check_video(self, source, item):
        before = signature(source)
        if before[0] == 0 or time.time() - source.stat().st_mtime < self.settle_seconds:
            item.update(state='incomplete', message='Archivo reciente o vacío; se volverá a comprobar.')
            return
        key = str(source.resolve())
        cached = self.settings['checked'].get(key, {})
        if cached.get('signature') == before:
            fingerprint, metadata = cached['sha256'], cached['metadata']
        else:
            _, fingerprint, metadata = self.store.probe(source)
            check_frames(source, metadata)
            if signature(source) != before:
                item.update(state='incomplete', message='El archivo sigue cambiando; espera a que termine la copia.')
                return
            self.settings['checked'][key] = {'signature': before, 'sha256': fingerprint, 'metadata': metadata}
        item.update(sha256=fingerprint, duration=metadata['duration'], width=metadata['width'], height=metadata['height'])
        if signature(source) != before:
            item.update(state='incomplete', message='El archivo sigue cambiando; espera a que termine la copia.')
            return
        rows = self.store.rows()
        existing = next((r for r in rows if (r['round'], r['half']) == (item['round'], item['half'])), None)
        duplicate = next((r for r in rows if r['fingerprint'] == fingerprint), None)
        if existing:
            same = existing['fingerprint'] == fingerprint
            item.update(state='registered' if same else 'conflict',
                        message='Ya registrado; análisis y revisiones conservados.' if same else 'Esta parte ya tiene otro vídeo; no se sustituye.')
            if same and Path(existing['source']).resolve() != source.resolve():
                item.update(state='duplicate', message='Contenido ya registrado en otra ruta; se conserva la ubicación original.')
        elif duplicate:
            item.update(state='duplicate', message=f"Ya registrado en jornada {duplicate['round']}, parte {duplicate['half']}.")
        else:
            self.store.register({'round': item['round'], 'parts': [{'half': item['half'], 'source': key}]},
                                checked_sources={key: (key, fingerprint, metadata)})
            item.update(state='ready', message='Registrado y listo. Pulsa Analizar en la jornada cuando quieras.')

    def check_models(self):
        result = []
        for model in read_json(APP_DIR / 'modelos.json', []):
            path = self.models_root / model['file']
            item = {'file': model['file'], 'state': 'missing'}
            if path.is_file():
                stamp = signature(path)
                cached = self.settings['model_checks'].get(model['file'], {})
                digest = cached.get('sha256') if cached.get('signature') == stamp else sha256(path)
                self.settings['model_checks'][model['file']] = {'signature': stamp, 'sha256': digest}
                item['state'] = 'verified' if digest == model['sha256'] else 'mismatch'
            result.append(item)
        return result

    @staticmethod
    def validate_example(value):
        if not isinstance(value, dict):
            raise ValueError('Ejemplo inválido.')
        item = {key: value.get(key) for key in ('id', 'season', 'round', 'half', 'start', 'end', 'label', 'category', 'split', 'source_sha256')}
        if not isinstance(item['id'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', item['id']):
            raise ValueError('Identificador de ejemplo inválido.')
        if not isinstance(item['season'], str) or not re.fullmatch(r'temporada-[0-9]{4}(?:-[0-9]{4})?', item['season']):
            raise ValueError('Temporada del ejemplo inválida.')
        if type(item['round']) is not int or not 1 <= item['round'] <= 9999 or type(item['half']) is not int or item['half'] not in (1, 2):
            raise ValueError('Jornada o parte del ejemplo inválida.')
        if any(type(item[k]) not in (int, float) or not math.isfinite(item[k]) for k in ('start', 'end')) or not 0 <= item['start'] < item['end']:
            raise ValueError('El intervalo debe cumplir 0 ≤ inicio < fin.')
        if not isinstance(item['label'], str) or not 1 <= len(item['label'].strip()) <= 160:
            raise ValueError('Escribe un nombre de ejemplo de hasta 160 caracteres.')
        item['label'] = item['label'].strip()
        if item['category'] not in CATEGORIES or item['split'] not in SPLITS:
            raise ValueError('Categoría o grupo del ejemplo inválido.')
        if not isinstance(item['source_sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', item['source_sha256']):
            raise ValueError('Huella del vídeo inválida.')
        return item

    def save_examples(self, value):
        """Import merges IDs; a single example binds to the registered original."""
        with self.lock:
            catalogue = self.catalogue()
            existing = {self.validate_example(e)['id']: self.validate_example(e) for e in catalogue['examples']}
            if 'remove' in value:
                if value['remove'] not in existing:
                    raise ValueError('Ejemplo no encontrado.')
                del existing[value['remove']]
                write_json(self.catalogue_path(), {'version': 1, 'examples': list(existing.values())})
                return self.snapshot()
            if 'catalogue' in value:
                imported = value['catalogue']
                if not isinstance(imported, dict) or imported.get('version') != 1 or not isinstance(imported.get('examples'), list):
                    raise ValueError('Catálogo incompatible.')
                incoming = [self.validate_example(e) for e in imported['examples']]
            else:
                rows = self.store.rows(value.get('round'), value.get('half'))
                if len(rows) != 1:
                    raise ValueError('Selecciona una parte registrada.')
                row = rows[0]
                item = self.validate_example({**value, 'id': uuid.uuid4().hex, 'season': self.settings['season'], 'source_sha256': row['fingerprint']})
                if item['end'] > json.loads(row['metadata'])['duration']:
                    raise ValueError('El ejemplo termina después del vídeo.')
                incoming = [item]
            for item in incoming:
                if item['id'] in existing and existing[item['id']] != item:
                    raise ValueError('Un ejemplo con ese identificador tiene otro contenido; conserva ambas versiones con IDs distintos.')
                existing[item['id']] = item
            values = list(existing.values())
            registered = {(r['round'], r['half']): r for r in self.store.rows()}
            for i, one in enumerate(values):
                row = registered.get((one['round'], one['half']))
                if row and row['fingerprint'] == one['source_sha256'] and one['end'] > json.loads(row['metadata'])['duration']:
                    raise ValueError('El ejemplo termina después del vídeo.')
                for two in values[i + 1:]:
                    if one['source_sha256'] == two['source_sha256'] and one['split'] != two['split'] and max(one['start'], two['start']) < min(one['end'], two['end']):
                        raise ValueError('Una secuencia no puede estar a la vez en desarrollo y reserva con intervalos solapados.')
            write_json(self.catalogue_path(), {'version': 1, 'examples': values})
            return self.snapshot()


def library_for(app):
    with app.lock:
        if not hasattr(app, 'video_library'):
            app.video_library = VideoLibrary(app.season)
            app.video_library.start_scan()
        return app.video_library
