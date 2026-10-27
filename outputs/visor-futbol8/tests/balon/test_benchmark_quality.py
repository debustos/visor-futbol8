import unittest
from tests.balon.benchmark_native_ball import quality


class BallQualityTests(unittest.TestCase):
    def test_wrong_location_counts_as_false_detection_and_missed_visible_ball(self):
        result=quality([{'frame':1,'ball':{'center':[90,50]}}],[{'frame':1,'center':[50,50],'tolerance_pixels':12}])
        self.assertEqual(result['false_detections'],1);self.assertEqual(result['missed_visible'],1)
        self.assertEqual(result['coverage'],1);self.assertEqual(result['precision'],0);self.assertEqual(result['recall'],0)

    def test_unknown_frames_are_excluded_and_invisible_frames_are_negatives(self):
        rows=[{'frame':1,'ball':{'center':[50,50]}},{'frame':2,'ball':{'center':[50,50]}}]
        result=quality(rows,[{'frame':1,'unknown':True},{'frame':2,'center':None}])
        self.assertEqual(result['unknown'],1);self.assertEqual(result['annotated'],1)
        self.assertEqual(result['false_detections'],1);self.assertIsNone(result['recall'])

    def test_recall_includes_visible_frames_with_no_published_row(self):
        rows=[{'frame':1,'ball':{'center':[51,50]}}]
        labels=[{'frame':frame,'center':[50,50],'tolerance_pixels':12} for frame in (1,2)]
        result=quality(rows,labels)
        self.assertEqual(result['correct'],1);self.assertEqual(result['missed_visible'],1)
        self.assertEqual(result['precision'],1);self.assertEqual(result['recall'],.5);self.assertEqual(result['coverage'],.5)


if __name__=='__main__':unittest.main()
