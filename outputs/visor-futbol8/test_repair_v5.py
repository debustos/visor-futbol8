"""Regression tests for actual failures: camera jitter, identity swaps and missed touches."""
import copy,unittest
import numpy as np
from visual_memory_v5 import reconstruct
from sequence_engine import sequence_actions
from analytics_v3 import profiles_for
from season_store import aggregate_parts
class RepairTests(unittest.TestCase):
 def test_camera_and_projection_jump_do_not_cut_screen_continuity(self):
  rs=[]
  for i in range(3):
   rs.append({'time':i*.2,'tracks':[{'id':j,'kit':'orange','box':[j*100+i*30,20,j*100+40+i*30,120],'position':[10 if i==0 else 95,50]} for j in range(4)]})
  e=[{'track_id':0,'readings':[{'frame':i,'time':i*.2,'text':'41','score':.99,'localized':True} for i in (0,2)]}]
  _,segs,_,q=reconstruct(rs,[],np.zeros((0,2)),e,{41:{}})
  self.assertEqual(len([s for s in segs if s['track_id']==0]),1)
 def test_verified_16_then_11_split_instead_of_labelling_whole_track(self):
  rs=[{'time':i*.2,'tracks':[{'id':1,'kit':'orange','position':[50,50]}]} for i in range(10)]
  e=[{'track_id':1,'readings':[{'frame':2,'time':.4,'text':'16','score':.999,'localized':True,'source':'verified_training_reference'},{'frame':8,'time':1.6,'text':'11','score':.999,'localized':True,'source':'verified_training_reference'}]}]
  result,_,_,_=reconstruct(rs,[],np.zeros((0,2)),e,{16:{},11:{}})
  self.assertEqual(result[0]['tracks'][0]['player_id'],'orange-16');self.assertEqual(result[-1]['tracks'][0]['player_id'],'orange-11')
 def test_duplicate_manual_reference_wins_over_ocr(self):
  rs=[{'time':i*.2,'tracks':[{'id':j,'kit':'orange','position':[j*10,50]} for j in (1,2)]} for i in range(3)]
  e=[{'track_id':2,'readings':[{'frame':i,'time':i*.2,'text':'41','score':.99,'localized':True} for i in (0,2)]}]
  reviews=[{'category':'identity','track_id':1,'start':0,'end':.4,'player_id':'orange-41','decision':'corrected'}]
  result,_,_,_=reconstruct(rs,[],np.zeros((0,2)),e,{41:{}},reviews=reviews)
  for r in result:self.assertEqual(r['tracks'][0]['player_id'],'orange-41');self.assertIsNone(r['tracks'][1]['player_id'])
 def touch_sequence(self,unknown=False,opponent=False,coexist=True):
  rs=[]
  for i in range(3):
   x=100+i*50;owner=1 if i==0 else 2 if i==2 else None
   a={'id':1,'kit':'opponent' if opponent else 'orange','player_id':None if opponent else 'orange-41','box':[80,30,120,100],'position':[10,50]}
   b={'id':2,'kit':'orange','player_id':None if unknown else 'orange-7','box':[180,30,220,100],'position':[30,50]}
   tracks=[a,b] if coexist else [a] if i==0 else [b]
   rs.append({'time':i*.1,'ball':{'confidence':.9,'position':[10+i*10,50],'center':[x,100]},'tracks':tracks,'possession':{'track_id':owner,'distance':.1} if owner else None})
  return rs
 def test_fast_single_touch_pass_with_measured_ball_path(self):
  es,_=sequence_actions(self.touch_sequence(),[],short_contacts=True)
  self.assertEqual([(e['kind'],e['state']) for e in es],[('pass','estimated')]);self.assertEqual(es[0]['sequence']['image_path_samples'],1)
 def test_low_confidence_boot_like_endpoint_never_counts_as_a_pass(self):
  rs=self.touch_sequence();rs[0]['ball']['confidence']=.4
  # Keep a stable contact to exercise travel with a weak endpoint.
  extra=copy.deepcopy(rs[0]);extra['time']=-.1;rs.insert(0,extra)
  es,_=sequence_actions(rs,[],short_contacts=True)
  self.assertTrue(es);self.assertTrue(all(e['state']=='candidate' for e in es))
 def test_missing_ball_path_stays_candidate(self):
  rs=self.touch_sequence();rs[1]['ball']=None;es,_=sequence_actions(rs,[],short_contacts=True)
  self.assertEqual(es[0]['state'],'candidate')
 def test_unknown_receiver_name_can_still_credit_known_passer(self):
  es,_=sequence_actions(self.touch_sequence(unknown=True),[],short_contacts=True)
  self.assertEqual(es[0]['player_id'],'orange-41');self.assertIsNone(es[0]['receiver_id']);self.assertEqual(es[0]['state'],'estimated')
 def test_unknown_receiver_without_two_people_is_not_a_pass(self):
  es,_=sequence_actions(self.touch_sequence(unknown=True,coexist=False),[],short_contacts=True)
  self.assertFalse(es)
 def test_recovery_time_and_source_track_are_the_recoverer(self):
  es,_=sequence_actions(self.touch_sequence(opponent=True),[],short_contacts=True)
  e=next(e for e in es if e['kind']=='recovery');self.assertEqual(e['player_id'],'orange-7');self.assertEqual(e['source_track'],2);self.assertEqual(e['time'],.2)
 def test_unobserved_player_is_unknown_not_a_match_zero(self):
  rs=[{'time':0,'tracks':[{'id':1,'player_id':'orange-41','position':[50,50]}]}]
  ps=profiles_for(rs,[],[{'jersey_number':41},{'jersey_number':5}],1)
  self.assertEqual(ps[0]['metrics']['passes']['detected_value'],0);self.assertIsNone(ps[1]['metrics']['passes']['detected_value']);self.assertIsNone(ps[0]['metrics']['passes']['value'])
if __name__=='__main__':unittest.main()
