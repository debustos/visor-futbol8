import unittest,tempfile,json
from pathlib import Path
import numpy as np
from native_ball import iter_records,consensus,associated_tracks
from ball_tracker import MeasuredBallTracker,compact_components
from automatic_core import foot_contacts,infer_possession
from dorsal_guard import apply_guard
from goal_geometry import detect_goal

class NativeBallTests(unittest.TestCase):
 def test_stream_preserves_unicode_and_order(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'r.json';p.write_text(json.dumps([{'time':1,'name':'Razquín'},{'time':2}],ensure_ascii=False),encoding='utf8');self.assertEqual(list(iter_records(p)),[{'time':1,'name':'Razquín'},{'time':2}])
 def test_incomplete_array_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'r.json';p.write_text('[{"time":1}',encoding='utf8')
   with self.assertRaises(ValueError):list(iter_records(p))
 def test_trailing_data_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'r.json';p.write_text('[] ignored',encoding='utf8')
   with self.assertRaises(ValueError):list(iter_records(p))
 def ball(self,x,kind='neural_detection'):
  return {'box':[x-5,45,x+5,55],'center':[x,50],'confidence':.9 if kind=='neural_detection' else .5,'measurement':kind}
 def test_different_bidirectional_tracks_abstain(self):self.assertIsNone(consensus(self.ball(50),self.ball(150)))
 def test_concordant_tracks_retain_measured_neural_box(self):
  q=consensus(self.ball(50,'compact_image_component'),self.ball(52));self.assertEqual(q['center'],[52,50]);self.assertEqual(q['tracking_consensus'],'bidirectional')
 def test_missing_measurements_never_create_a_ball(self):
  t=MeasuredBallTracker();im=np.full((120,120,3),(60,130,70),np.uint8);self.assertIsNone(t.update(im,0,[]));self.assertIsNone(t.update(im,.033,[]))
 def test_white_line_is_not_a_compact_component(self):
  im=np.zeros((120,120,3),np.uint8);im[60:64,10:110]=255;self.assertFalse(compact_components(im,[60,60],55,10))
 def test_new_seed_outside_projected_pitch_is_rejected(self):
  im=np.full((120,120,3),(60,130,70),np.uint8);t=MeasuredBallTracker();self.assertIsNone(t.update(im,0,[self.ball(50)],C=np.array([[1,0,300],[0,1,0],[0,0,1]],float)))
 def test_raised_ankle_contact_is_measured(self):
  kp=[[0,0,0] for _ in range(17)];kp[15]=[110,85,.9];kp[16]=[100,145,.9];b={'id':1,'kit':'orange','box':[90,10,130,150],'keypoints':kp};r={'ball':{'center':[113,85]},'tracks':[b]};self.assertEqual(infer_possession(r)['track_id'],1);self.assertEqual(infer_possession(r)['method'],'measured_ankle_contact')
 def test_unreliable_ankle_does_not_add_contact(self):
  kp=[[0,0,0] for _ in range(17)];kp[15]=[110,80,.2];r={'ball':{'center':[113,80]},'tracks':[{'id':1,'kit':'orange','box':[90,10,130,150],'keypoints':kp}]};self.assertIsNone(infer_possession(r))
 def test_chest_ball_is_not_ankle_contact(self):
  kp=[[0,0,0] for _ in range(17)];kp[15]=[110,145,.9];r={'ball':{'center':[110,55]},'tracks':[{'id':1,'kit':'orange','box':[90,10,130,150],'keypoints':kp}]};self.assertIsNone(infer_possession(r))
 def test_manual_competing_identity_survives_dorsal_guard(self):
  rs=[]
  for i in range(2):
   a={'id':1,'kit':'orange','person_track_id':'a','player_id':'orange-41','identity':{},'dorsal_observations':[{'number':22,'frame':i,'score':.99}]};b={'id':2,'kit':'orange','person_track_id':'manual','player_id':'orange-22','identity':{'method':'manual_review'}};rs.append({'time':i*.1,'frame':i,'tracks':[a,b]})
  apply_guard(rs);self.assertTrue(all(r['tracks'][1]['player_id']=='orange-22' for r in rs));self.assertTrue(all(r['tracks'][0]['player_id'] is None for r in rs))
 def test_goal_geometry_requires_calibration(self):self.assertIsNone(detect_goal(np.zeros((1080,1920,3),np.uint8),None))
 def test_no_goal_posts_no_goal_geometry(self):self.assertIsNone(detect_goal(np.zeros((300,400,3),np.uint8),np.eye(3)))
if __name__=='__main__':unittest.main()
