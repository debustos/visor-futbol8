import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from evaluacion.medir import evaluate, validate
from evaluacion.preparar import inspect_capture, reference


class PreparationTests(unittest.TestCase):
    def capture(self, fps=30, decode=True, seek=True):
        cv = SimpleNamespace(CAP_PROP_FPS=1, CAP_PROP_FRAME_COUNT=2, CAP_PROP_POS_FRAMES=3, CAP_PROP_POS_MSEC=4)
        position = [0]
        def get(key):
            return {1: fps, 2: 300, 3: position[0], 4: (position[0]-1)*1000/30}[key]
        def set_frame(_key, index):
            position[0] = index
            return seek
        def read():
            position[0] += 1
            return decode, None
        return cv, Mock(get=get, set=set_frame, read=read, isOpened=lambda: True)

    def test_records_observed_pts_without_claiming_full_review(self):
        cv, cap = self.capture(fps=29.99)
        with patch.dict("sys.modules", cv2=cv):
            timing = inspect_capture(cap)
        self.assertEqual([s["frame_index"] for s in timing["samples"]], [0, 1, 150, 151, 298, 299])
        self.assertFalse(timing["timing_complete"])
        sample = timing["samples"][2]
        self.assertNotEqual(sample["pts_seconds"], sample["frame_over_average_fps_seconds"])

    def test_rejects_missing_duration(self):
        cv, cap = self.capture(fps=0)
        with patch.dict("sys.modules", cv2=cv), self.assertRaises(ValueError):
            inspect_capture(cap)

    def test_rejects_failed_decode(self):
        cv, cap = self.capture(decode=False)
        with patch.dict("sys.modules", cv2=cv), self.assertRaises(ValueError):
            inspect_capture(cap)

    def test_rejects_failed_seek(self):
        cv, cap = self.capture(seek=False)
        with patch.dict("sys.modules", cv2=cv), self.assertRaises(ValueError):
            inspect_capture(cap)

    def test_real_original_is_not_a_verified_reference(self):
        ref = reference(2, 1, "a"*64, {"duration_seconds": 60, "timing_complete": False})
        validate(ref, "a"*64, 2, 1)
        self.assertFalse(ref["synthetic"])
        self.assertEqual(ref["events"], [])
        self.assertEqual(ref["coverage"], {"development": [], "holdout": []})
        result = evaluate(ref, [{"id": "proposal", "kind": "goal", "time": 20}], "goal", "development")
        self.assertEqual(len(result["unassessed"]), 1)
        self.assertEqual(result["false"], [])
        self.assertIsNone(result["precision"])
        self.assertIsNone(result["recall"])
        self.assertEqual(result["acceptance"], "not_demonstrated")

    def test_each_half_keeps_its_own_original_identity(self):
        ref = reference(2, 2, "b"*64, {"duration_seconds": 60})
        with self.assertRaises(ValueError):
            validate(ref, "b"*64, 2, 1)
