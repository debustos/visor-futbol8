import unittest,numpy as np
from f8.identidad.far_identity import evidence_windows,decide_context,calibrate_sequences,train_and_evaluate,feature_scale
class FarIdentityTests(unittest.TestCase):
 def test_windows_use_time_and_work_at_both_sampling_rates(self):
  for step in (1,.5):
   t=np.arange(0,10,step);windows=evidence_windows(np.arange(len(t)),t,np.repeat(60,len(t)));self.assertTrue(windows);self.assertTrue(all(t[w[-1]]-t[w[0]]>=6 for w in windows))
 def test_short_burst_cannot_become_an_identity(self):
  t=np.arange(8)*.2;self.assertFalse(evidence_windows(np.arange(8),t,np.repeat(60,8)))
 def test_occlusion_gap_is_not_interpolated_as_evidence(self):
  t=np.array([0,1,2,3,7,8,9,10]);self.assertFalse(evidence_windows(np.arange(8),t,np.repeat(60,8)))
 def test_far_class_requires_its_far_gate(self):
  p=np.tile([.96,.04],(9,1));t=np.arange(9);h=np.repeat(60,9)
  self.assertFalse(decide_context(p,[41,7],t,h,{'41:small':.7})['accepted'])
  self.assertTrue(decide_context(p,[41,7],t,h,{'41:far':.7})['accepted'])
 def test_clearer_views_can_anchor_a_mixed_scale_sequence(self):
  p=np.tile([.96,.04],(9,1));result=decide_context(p,[41,7],np.arange(9),np.array([60]*6+[95]*3),{'41:small':.8});self.assertTrue(result['accepted']);self.assertFalse(result['pure_far'])
 def test_appearance_disagreement_blocks_a_name(self):
  p=np.array([[.95,.05]]*5+[[.05,.95]]*4);self.assertFalse(decide_context(p,[41,7],np.arange(9),np.repeat(60,9),{'41:far':.65})['accepted'])
 def test_context_balancing_prevents_a_long_track_hiding_one_wrong_player(self):
  def item(group,truth):return {'number':41,'truth':truth,'group':group,'far':True,'score':.95,'agreement':1,'margin':.9}
  windows=[item('long',41)]*100+[item('b',41),item('c',41),item('wrong',7)];thresholds,_=calibrate_sequences(windows,[41,7]);self.assertEqual(thresholds['41:small'],1.1);self.assertEqual(thresholds['41:far'],1.1)
 def test_one_context_is_insufficient_for_calibration(self):
  windows=[{'number':41,'truth':41,'group':'one','far':True,'score':.95,'agreement':1,'margin':.9}]*100
  thresholds,_=calibrate_sequences(windows,[41]);self.assertEqual(thresholds['41:far'],1.1)
 def test_near_views_are_not_replaced_by_the_small_player_model(self):
  p=np.tile([.96,.04],(9,1));self.assertFalse(decide_context(p,[41,7],np.arange(9),np.repeat(180,9),{'41:small':.65})['accepted'])
 def test_feature_scaling_reduces_global_kit_and_preserves_boot_evidence(self):
  scale=feature_scale('physical');self.assertEqual(len(scale),872);self.assertLess(scale[0],scale[-1]);self.assertLess(scale[600],scale[-1])
 def test_model_selection_does_not_see_outer_context_labels(self):
  rng=np.random.default_rng(13);x=[];y=[];groups=[];times=[]
  for n in (7,41):
   for g in range(6):
    for t in range(10):
     v=rng.normal(0,.0001,872);v[800+(n==41)]=1;x.append(v);y.append(n);groups.append(f'{n}-{g}');times.append(g*20+t)
  x=np.array(x,np.float32);y=np.array(y);groups=np.array(groups);model,scale,thresholds,q=train_and_evaluate(x,y,groups,x,y,groups,np.repeat(60,len(x)),np.array(times))
  self.assertEqual(len(q['folds']),3);self.assertTrue(all(not f['context_leakage'] and not f['selection_saw_outer_labels'] for f in q['folds']));self.assertFalse(q['active']);self.assertEqual(q['comparisons']['far']['specialist_accuracy_against_anchor_labels'],1)
if __name__=='__main__':unittest.main()
