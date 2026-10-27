"""Local corrections stay anchors; rechecks reuse only matching input pixels."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from f8.identidad.dorsal_guard import (cached_recheck, load_recheck_cache,
                                       recheck_fingerprint, recheck_key)
from f8.identidad.dorsales import jersey_vote
from f8.identidad.trajectory_identity import stabilize
from tests.identidad.compare_contexts import observation, sequences


class LocalAnchorTests(unittest.TestCase):
    def test_fixed_sequences_and_repeated_stabilization(self):
        for name, (records, truth) in sequences().items():
            with self.subTest(sequence=name):
                for _ in range(2):
                    stabilize(records)
                    self.assertEqual([[b.get('player_id') for b in r['tracks']] for r in records], truth)

    def test_local_anchor_keeps_unknown_neighbours_until_a_contradiction(self):
        records, _ = sequences()['local_22_then_41']
        records.insert(1, {'frame': 1, 'time': .05, 'tracks': [observation()]})
        contexts, report = stabilize(records)
        self.assertEqual([r['tracks'][0]['player_id'] for r in records], ['orange-22', 'orange-22', 'orange-41'])
        self.assertEqual(len(contexts), 2)
        self.assertEqual(report['reset_reasons']['contradictory_anchor'], 1)

    def test_simultaneous_duplicate_does_not_gain_a_name_from_the_new_anchor(self):
        records, _ = sequences()['local_22_then_41']
        for r in records:
            r['tracks'].append(observation('orange-22', 'calibrated_appearance', tid=2, x=300))
        stabilize(records)
        self.assertTrue(all(r['tracks'][1]['player_id'] is None for r in records))

    def test_documented_ocr_confusions_remain_unknown_or_full_number(self):
        for full, clipped in ((99, 9), (16, 6)):
            reads = [{'text': str(clipped), 'score': .99, 'localized': True, 'frame': i} for i in (1, 2)]
            self.assertIsNone(jersey_vote(reads+[{'text': str(full), 'score': .32, 'localized': True, 'frame': 3}], {full, clipped})[0])
            reads += [{'text': str(full), 'score': .85, 'localized': True, 'frame': i} for i in (1, 2)]
            self.assertEqual(jersey_vote(reads, {full, clipped})[0], full)
        for a, b in ((41, 14), (9, 5)):
            reads = [{'text': str(n), 'score': .99, 'localized': True, 'frame': i} for i, n in enumerate((a, b, a, b))]
            self.assertIsNone(jersey_vote(reads, {a, b})[0])


class RecheckCacheTests(unittest.TestCase):
    def test_repeated_stage_keeps_output_without_loading_ocr_or_decoding(self):
        from f8.identidad.dorsal_guard import main
        from f8.core import runtime_context
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root/'automatic').mkdir(); cache = root/'cache'; cache.mkdir()
            source = root/'video'; source.write_bytes(b'synthetic video placeholder')
            (cache/'scan.json').write_text('[]'); path = root/'records.json'
            records = []
            for i in range(5):
                b = observation('orange-41'); b['person_track_id'] = 'context'; b['box'][3] = 120
                if i==2: b['dorsal_observations'] = [{'number': 22, 'frame': 30, 'time': 1., 'score': .99}]
                records.append({'frame': i*15, 'time': i*.5, 'tracks': [b]})
            def read(cap, reader, r, b):
                return [{'track_id': b['id'], 'readings': [{'text': '22', 'frame': r['frame'],
                         'time': r['time'], 'score': .99, 'localized': True, 'source': 'local_dorsal_recheck'}]}]
            reader = Mock()
            with patch.multiple(runtime_context, ROOT=root, CACHE=cache, SOURCE=str(source)), \
                 patch.dict('sys.modules', {'torch': Mock(), 'easyocr': reader}), \
                 patch('cv2.VideoCapture') as capture, \
                 patch('f8.identidad.dorsal_guard.read_local_dorsal', side_effect=read) as ocr, \
                 patch('sys.argv', ['dorsal_guard', '--records', str(path)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                outputs = []
                for _ in range(2):
                    path.write_text(json.dumps(records)); main(); outputs.append(json.loads(path.read_text()))
                self.assertEqual(outputs[0], outputs[1])
                self.assertTrue(all(r['tracks'][0]['player_id']=='orange-22' for r in outputs[1]))
                self.assertEqual(ocr.call_count, 4)
                reader.Reader.assert_called_once(); capture.assert_called_once()
                quality = json.loads((root/'automatic/dorsal-guard-quality.json').read_text())
                self.assertEqual(quality['ocr_cache'], {'reused_observations': 4, 'read_observations': 0})

    def test_successful_empty_and_nonempty_results_are_reused(self):
        r = {'frame': 10, 'time': .5}; b = observation(); b['id'] = 7
        for result in ([], [{'track_id': 7, 'readings': [{'text': '22'}]}]):
            with self.subTest(result=result):
                cache = {}; reader = Mock(return_value=result)
                self.assertEqual(cached_recheck(cache, r, b, reader), (result, False))
                self.assertEqual(cached_recheck(cache, r, b, reader), (result, True))
                reader.assert_called_once_with(r, b)
                # Cache keys survive JSON round trips and native numeric/string IDs.
                b['id'] = '7'
                self.assertEqual(cached_recheck(json.loads(json.dumps(cache)), r, b, reader), (result, True))

    def test_decode_failures_are_retried(self):
        cache = {}; reader = Mock(return_value=None); r = {'frame': 10, 'time': .5}; b = observation()
        for _ in range(2): self.assertEqual(cached_recheck(cache, r, b, reader), ([], False))
        self.assertEqual(reader.call_count, 2); self.assertFalse(cache)

    def test_box_frame_time_or_track_change_invalidates_the_observation(self):
        r = {'frame': 10, 'time': .5}; b = observation(); key = recheck_key(r, b)
        for target, field, value in (('r', 'frame', 11), ('r', 'time', .6),
                                     ('b', 'id', 2), ('b', 'box', [81, 20, 121, 100])):
            rr, bb = copy.deepcopy(r), copy.deepcopy(b)
            (rr if target=='r' else bb)[field] = value
            self.assertNotEqual(recheck_key(rr, bb), key)

    def test_video_scan_and_reader_fingerprint_are_required(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/'video'; scan = root/'scan'; path = root/'cache'
            source.write_bytes(b'video'); scan.write_bytes(b'[]')
            fingerprint = recheck_fingerprint(source, scan); observations = {'key': []}
            path.write_text(json.dumps({'fingerprint': fingerprint, 'observations': observations}))
            self.assertEqual(load_recheck_cache(path, fingerprint), observations)
            for field in fingerprint:
                changed = {**fingerprint, field: 'different'}
                self.assertEqual(load_recheck_cache(path, changed), {})
            scan.write_bytes(b'[{}]')
            self.assertNotEqual(recheck_fingerprint(source, scan), fingerprint)
            scan.write_bytes(b'[]'); source.write_bytes(b'another video')
            self.assertNotEqual(recheck_fingerprint(source, scan), fingerprint)
            model = root/'ocr.pth'; model.write_bytes(b'model one')
            first = recheck_fingerprint(source, scan, root); model.write_bytes(b'model two')
            self.assertNotEqual(recheck_fingerprint(source, scan, root), first)
            path.write_text('broken json')
            self.assertEqual(load_recheck_cache(path, fingerprint), {})
            path.write_text('[]')  # Old unscoped recheck list is never reused.
            self.assertEqual(load_recheck_cache(path, fingerprint), {})
            self.assertEqual(load_recheck_cache(root/'missing', fingerprint), {})


if __name__ == '__main__':
    unittest.main()
