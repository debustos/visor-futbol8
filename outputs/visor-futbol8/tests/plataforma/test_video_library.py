"""Isolated originals: registration, cache invalidation, catalogues and HTTP sessions."""
import copy
import importlib.util
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from f8.plataforma.server import App, ROOT, handler_for
from f8.plataforma.season_store import SeasonStore
from f8.plataforma.video_library import VideoLibrary, library_for, sha256


class VideoLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        root = self.base / 'app'
        (root / 'data').mkdir(parents=True)
        (root / 'plantilla.json').write_bytes((ROOT / 'plantilla.json').read_bytes())
        (root / 'data/metadata.json').write_text(json.dumps({'source': 'unused', 'duration': 5}), encoding='utf8')
        self.app = App(root)
        self.app.season = SeasonStore(self.app)
        self.library = VideoLibrary(self.app.season, self.base / 'models', settle_seconds=0)
        self.app.video_library = self.library
        self.data = self.base / 'Futbol8Datos'
        self.configure()

    def configure(self):
        self.library.configure({'directory': str(self.data), 'season': 'temporada-2026'})
        self.library.thread.join(10)
        self.assertFalse(self.library.thread.is_alive())

    def video(self, name='primera.avi', round=2, seed=1):
        path = self.data / 'originales/temporada-2026' / f'jornada-{round:03d}' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (48, 32))
        self.assertTrue(writer.isOpened())
        try:
            for i in range(20):
                writer.write(np.full((32, 48, 3), (i * seed + 10) % 255, np.uint8))
        finally:
            writer.release()
        return path

    def scan(self):
        self.library.scan()
        result = self.library.snapshot()
        self.assertEqual(result['state'], 'complete', result)
        return result['files']

    def test_registration_is_persistent_idempotent_and_checks_content_once(self):
        source = self.video()
        with patch.object(self.app.season, 'probe', wraps=self.app.season.probe) as probe:
            self.assertEqual(self.scan()[0]['state'], 'ready')
            row = self.app.season.rows()[0]
            revision = self.app.season.context(2, 1).db_path
            before = revision.read_bytes()
            self.assertEqual(self.scan()[0]['state'], 'registered')
            self.assertEqual(probe.call_count, 1)
            self.assertEqual(revision.read_bytes(), before)
        self.assertEqual(row['fingerprint'], sha256(source))
        reopened = VideoLibrary(self.app.season)
        self.assertEqual(reopened.settings['directory'], str(self.data.resolve()))
        self.assertEqual(len(self.app.season.rows()), 1)

    def test_content_duplicate_and_occupied_part_do_not_replace_original(self):
        source = self.video()
        self.scan()
        duplicate = self.data / 'originales/temporada-2026/jornada-003/primera.avi'
        duplicate.parent.mkdir(parents=True)
        duplicate.write_bytes(source.read_bytes())
        self.assertEqual(self.scan()[1]['state'], 'duplicate')
        self.video(seed=7)
        self.assertEqual(self.scan()[0]['state'], 'conflict')
        self.assertEqual(len(self.app.season.rows()), 1)

    def test_pending_copy_invalid_name_and_ambiguous_slot_are_not_registered(self):
        source = self.video()
        self.video('video.avi', round=3)
        self.video('parte-1.avi')
        (source.parent / 'segunda.mp4.part').write_bytes(b'partial')
        states = [f['state'] for f in self.scan()]
        self.assertEqual(states.count('conflict'), 2)
        self.assertIn('incomplete', states)
        self.assertIn('needs_metadata', states)
        self.assertEqual(self.app.season.rows(), [])

    def test_recent_and_changing_files_are_not_registered(self):
        self.video()
        self.library.settle_seconds = 60
        self.assertEqual(self.scan()[0]['state'], 'incomplete')
        self.library.settle_seconds = 0
        original_probe = self.app.season.probe
        def changing(source):
            result = original_probe(source)
            stat = Path(source).stat()
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000))
            return result
        with patch.object(self.app.season, 'probe', side_effect=changing):
            self.assertEqual(self.scan()[0]['state'], 'incomplete')
        self.assertEqual(self.app.season.rows(), [])

    def test_decode_failure_and_missing_season_show_errors(self):
        source = self.video()
        with patch('f8.plataforma.video_library.check_frames', side_effect=ValueError('Final ilegible')):
            self.assertEqual(self.scan()[0]['state'], 'error')
        self.assertEqual(self.app.season.rows(), [])
        self.library.settings['season'] = 'temporada-2099'
        self.library.scan()
        self.assertEqual(self.library.snapshot()['state'], 'failed')

    def test_background_checks_do_not_start_inference_or_block_status(self):
        self.video()
        started = threading.Event()
        release = threading.Event()
        def wait(*args):
            started.set()
            release.wait(5)
        with patch('f8.plataforma.video_library.check_frames', side_effect=wait):
            try:
                result = self.library.start_scan()
                self.assertTrue(started.wait(5))
                self.assertEqual(result['state'], 'scanning')
                thread = self.library.thread
                self.library.start_scan()
                self.assertIs(self.library.thread, thread)
                self.assertEqual(self.library.snapshot()['state'], 'scanning')
            finally:
                release.set()
                self.library.thread.join(10)
        self.assertFalse((self.app.root / 'automatic/profiles.json').exists())

    def test_configuration_rejects_links_relative_paths_and_season_traversal(self):
        for directory, season in [('https://drive.google.com/file/x', 'temporada-2026'), ('relative', 'temporada-2026'), (str(self.data), '../other')]:
            with self.assertRaises(ValueError):
                self.library.configure({'directory': directory, 'season': season})

    def test_empty_installation_preparer_uses_phase_zero_layout_and_keeps_metadata(self):
        spec = importlib.util.spec_from_file_location('prepare_library_test', ROOT.parents[1] / 'preparar-proyecto.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        code = self.base / 'new-install/outputs/visor-futbol8/f8/plataforma/server.py'
        code.parent.mkdir(parents=True)
        code.write_text('# fixture')
        prepared = module.prepare(self.base / 'new-install')
        metadata = prepared / 'data/metadata.json'
        metadata.write_text('{"existing": true}')
        module.prepare(self.base / 'new-install')
        self.assertEqual(json.loads(metadata.read_text()), {'existing': True})

    def example(self, **overrides):
        return {'round': 2, 'half': 1, 'start': .1, 'end': .8, 'label': 'Cruce', 'category': 'identidad', 'split': 'desarrollo', **overrides}

    def test_examples_roundtrip_without_machine_paths_and_remove(self):
        self.video()
        self.scan()
        result = self.library.save_examples(self.example())
        self.assertTrue(result['examples'][0]['available'])
        catalogue = self.library.catalogue()
        self.assertNotIn(str(self.base), json.dumps(catalogue))
        self.assertEqual(len(self.library.save_examples({'catalogue': catalogue})['examples']), 1)
        self.assertEqual(self.library.save_examples({'remove': catalogue['examples'][0]['id']})['examples'], [])
        self.assertEqual(len(self.library.save_examples({'catalogue': catalogue})['examples']), 1)
        source = Path(self.app.season.rows()[0]['source'])
        source.unlink()
        self.assertFalse(self.library.snapshot()['examples'][0]['available'])

    def test_bad_intervals_unknown_parts_and_overlapping_splits_are_rejected(self):
        self.video()
        self.scan()
        for changes in ({'end': 9}, {'start': -.1}, {'end': float('nan')}, {'half': 2}, {'round': None}, {'split': 'training'}):
            with self.assertRaises(ValueError):
                self.library.save_examples(self.example(**changes))
        self.library.save_examples(self.example())
        with self.assertRaisesRegex(ValueError, 'solapados'):
            self.library.save_examples(self.example(split='reserva', start=.5, end=1.0))
        self.assertEqual(len(self.library.catalogue()['examples']), 1)

    def test_import_is_atomic_and_does_not_overwrite_conflicting_ids(self):
        self.video()
        self.scan()
        self.library.save_examples(self.example())
        catalogue = self.library.catalogue()
        changed = copy.deepcopy(catalogue)
        changed['examples'][0]['label'] = 'Otro'
        with self.assertRaises(ValueError):
            self.library.save_examples({'catalogue': changed})
        changed = copy.deepcopy(catalogue)
        changed['examples'].append({'id': 'invalid'})
        with self.assertRaises(ValueError):
            self.library.save_examples({'catalogue': changed})
        self.assertEqual(self.library.catalogue(), catalogue)

    def test_model_hashes_are_verified_and_reused(self):
        models = self.base / 'models'
        models.mkdir()
        model = models / 'test.onnx'
        model.write_bytes(b'example-model')
        manifest = self.base / 'manifest'
        manifest.mkdir()
        (manifest / 'modelos.json').write_text(json.dumps([{'file': model.name, 'sha256': sha256(model)}, {'file': 'missing.onnx', 'sha256': '0' * 64}]))
        with patch('f8.plataforma.video_library.APP_DIR', manifest):
            self.assertEqual([m['state'] for m in self.library.check_models()], ['verified', 'missing'])
            with patch('f8.plataforma.video_library.sha256', side_effect=AssertionError('Rehashed')):
                self.library.check_models()
            model.write_bytes(b'different-model')
            self.assertEqual(self.library.check_models()[0]['state'], 'mismatch')

    def test_http_uses_host_token_even_with_half_scope_and_serves_library_module(self):
        self.video()
        self.scan()
        child = self.app.season.context(2, 1)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join()))
        base = f'http://127.0.0.1:{server.server_port}'
        self.assertEqual(urllib.request.urlopen(base + '/modulos/80-video-library.js').status, 200)
        self.assertEqual(json.load(urllib.request.urlopen(base + '/api/season/library?round=2&half=1'))['directory'], str(self.data.resolve()))
        def post(token):
            return urllib.request.urlopen(urllib.request.Request(base + '/api/season/library/examples?round=2&half=1',
                data=json.dumps(self.example()).encode(), headers={'X-Review-Token': token, 'Content-Type': 'application/json'}))
        with self.assertRaises(urllib.error.HTTPError) as error:
            post(child.token)
        self.assertEqual(error.exception.code, 403)
        self.assertEqual(len(json.load(post(self.app.token))['examples']), 1)


if __name__ == '__main__':
    unittest.main()
