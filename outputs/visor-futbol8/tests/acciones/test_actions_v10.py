import unittest,copy
import numpy as np
from f8.acciones.action_quality import metric_counts,action_diagnostics
from f8.identidad.dorsal_guard import apply_guard
from f8.balon.refine_ball import search_plan
from f8.acciones.sequence_engine import temporal_shot_proposals,released_actor

class ActionTests(unittest.TestCase):
 def test_goal_reference_never_creates_an_automatic_event(self):
  actions=[];q=action_diagnostics(actions,{}, {'source_key':'a','team_goals':1},'a')
  self.assertEqual(q['goal_check']['missing_from_automatic_count'],1);self.assertEqual(actions,[])
 def test_reference_for_another_video_is_not_used(self):
  self.assertIsNone(action_diagnostics([],{}, {'source_key':'a','team_goals':1},'b')['goal_check'])
 def test_matching_total_is_not_accuracy_validation(self):
  q=action_diagnostics([{'kind':'goal','state':'estimated','player_id':'orange-41'}],{}, {'source_key':'a','team_goals':1},'a')
  self.assertEqual(q['goal_check']['state'],'count_matches_unvalidated')
 def test_unsupported_metric_never_reports_a_zero_from_identity_visibility(self):
  self.assertIsNone(metric_counts('shots',0,0,3,True)['detected_value'])
 def test_passes_remain_partial_detected_counts(self):
  self.assertEqual(metric_counts('passes',1,0,3,True)['detected_value'],1)
 def test_ball_search_without_geometry(self):
  self.assertEqual(search_plan(None,1,None,(1080,1920,3),0)[1],'full')
  self.assertEqual(search_plan({'time':1,'center':[800,700],'position':None},1.1,None,(1080,1920,3),1)[1],'local')
 def test_two_shot_labels_keep_stronger_probability(self):
  q=temporal_shot_proposals([{'time':10,'class':'Shots off target','score':.21},{'time':10,'class':'Shots on target','score':.56}])
  self.assertEqual(len(q),1);self.assertEqual(q[0]['class'],'Shots on target');self.assertEqual(len(q[0]['temporal_evidence']),2)
 def rows(self,manual=False):
  return [{'frame':i,'time':i*.1,'tracks':[{'id':1,'person_track_id':'ctx','player_id':'orange-41','kit':'orange','identity':{'method':'manual_review' if manual else 'trajectory_context'},'dorsal_observations':[{'number':22,'score':.99,'frame':i,'time':i*.1,'source':'full_jersey'}]}]} for i in range(2)]
 def test_local_dorsal_beats_an_old_track_label(self):
  rs=self.rows();q=apply_guard(rs);self.assertEqual(len(q['changes']),1);self.assertTrue(all(r['tracks'][0]['player_id']=='orange-22' for r in rs))
 def test_one_contrary_frame_suspends_identity_without_guessing_another(self):
  rs=self.rows()[:1];apply_guard(rs);self.assertIsNone(rs[0]['tracks'][0]['player_id'])
 def test_manual_identity_is_preserved(self):
  rs=self.rows(True);apply_guard(rs);self.assertEqual(rs[0]['tracks'][0]['player_id'],'orange-41')
 def test_goalkeeper_reception_without_release_cannot_be_a_shooter(self):
  r={'time':1,'ball':{'center':[100,100],'confidence':.9},'tracks':[{'id':1,'kit':'keeper','player_id':'orange-1','box':[80,30,120,100]}]}
  ep={'trusted':True,'last':r,'actor':r['tracks'][0]}
  actor,evidence=released_actor([ep],[r],1,{1:np.zeros(2)})
  self.assertFalse(actor);self.assertEqual(evidence['state'],'unobserved')
if __name__=='__main__':unittest.main()
