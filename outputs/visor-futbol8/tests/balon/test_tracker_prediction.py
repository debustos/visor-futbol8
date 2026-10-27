import unittest
from unittest.mock import patch
import numpy as np
from f8.balon.ball_tracker import MeasuredBallTracker


class TrackerPredictionTests(unittest.TestCase):
    def setUp(self):
        self.image=np.full((120,120,3),(60,130,70),np.uint8)

    def seed(self,x=50):
        return {'box':[x-5,45,x+5,55],'confidence':.9}

    def test_no_seed_skips_camera_and_never_publishes_a_prediction(self):
        tracker=MeasuredBallTracker()
        with patch('f8.balon.ball_tracker.camera_step',side_effect=AssertionError('Unneeded camera registration')):
            for time in (0,.033,.066,.099):
                prediction=tracker.predict(self.image,time)
                self.assertIsNone(prediction)
                self.assertIsNone(tracker.update(self.image,time,[],prediction=prediction))
        self.assertIsNone(tracker.last_camera)

    def test_seed_reacquisition_after_empty_frames_keeps_measured_box(self):
        tracker=MeasuredBallTracker();tracker.update(self.image,0,[])
        with patch('f8.balon.ball_tracker.camera_step') as camera:
            ball=tracker.update(self.image,.033,[self.seed()])
        camera.assert_not_called();self.assertEqual(ball['box'],self.seed()['box'])
        self.assertEqual(ball['measurement'],'neural_detection')

    def test_active_seed_keeps_inverse_camera_mapping_and_velocity(self):
        tracker=MeasuredBallTracker();tracker.update(self.image,0,[self.seed()]);tracker.velocity=np.array([30.,0.])
        backward=np.array([[1.,0.,-4.],[0.,1.,2.],[0.,0.,1.]])
        with patch('f8.balon.ball_tracker.camera_step',return_value=backward) as camera:
            prediction=tracker.predict(self.image,.1)
            ball=tracker.update(self.image,.1,[self.seed(54)],prediction=prediction)
        camera.assert_called_once();np.testing.assert_allclose(prediction,[57,48])
        self.assertEqual(ball['center'],[54,50]);np.testing.assert_allclose(tracker.last_camera,np.linalg.inv(backward))

    def test_gap_clears_cached_prediction_and_reacquires_without_camera(self):
        tracker=MeasuredBallTracker();tracker.update(self.image,0,[self.seed()]);tracker.last_camera=np.eye(3);tracker.prediction_value=np.array([99,99])
        with patch('f8.balon.ball_tracker.camera_step') as camera:
            self.assertIsNone(tracker.predict(self.image,.8))
            ball=tracker.update(self.image,.8,[self.seed(90)])
        camera.assert_not_called();self.assertIsNone(tracker.last_camera)
        self.assertEqual(ball['center'],[90,50]);self.assertEqual(ball['time'],.8)

    def test_missing_measurement_uses_camera_only_until_seed_expires(self):
        tracker=MeasuredBallTracker();tracker.update(self.image,0,[self.seed()])
        with patch('f8.balon.ball_tracker.camera_step',return_value=np.eye(3)) as camera,patch('f8.balon.ball_tracker.compact_components',return_value=[]):
            for index in range(1,22):self.assertIsNone(tracker.update(self.image,index/30,[]))
            self.assertIsNone(tracker.ball);calls=camera.call_count
            self.assertGreater(calls,0)
            self.assertIsNone(tracker.update(self.image,22/30,[]))
            self.assertEqual(camera.call_count,calls)


if __name__=='__main__':unittest.main()
