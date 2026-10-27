"""Independent labels, scale quotas and held-out context regressions."""
import unittest,numpy as np
from f8.identidad.reference_bank import build_inputs,choose_references,acceptable_box,calibrate_thresholds,train_and_evaluate,summarize_recovery
from f8.identidad.reference_sampling import retain_ocr_candidates

class ReferenceBankTests(unittest.TestCase):
 def input(self,method='jersey_vote'):
  rs=[{'frame':i*3,'time':i*.1,'tracks':[{'id':1,'box':[20,20,50,110],'confidence':.9,'kit':'orange','player_id':'orange-41','person_track_id':'c41'}]} for i in range(4)]
  rows=[{'index':i,'frame':r['frame'],'time':r['time'],'track_id':1} for i,r in enumerate(rs)]
  ev=[{'track_id':1,'readings':[{'frame':rs[i]['frame'],'time':rs[i]['time'],'text':'41','score':.99,'localized':True} for i in (0,2)]}]
  cs=[{'id':'c41','anchor_method':method,'player_id':'orange-41'}];return rs,rows,np.eye(4),[],ev,cs
 def test_appearance_proposals_never_train_their_own_labels(self):
  candidates,pool,frames,trusted=build_inputs(*self.input('calibrated_appearance'));self.assertFalse(candidates);self.assertFalse(trusted)
 def test_two_independent_dorsal_frames_seed_all_pose_frames(self):
  candidates,pool,frames,trusted=build_inputs(*self.input());self.assertEqual(len(pool),4);self.assertEqual(trusted,{'c41'});self.assertTrue(any(c['kind']=='dorsal' for c in candidates[41]))
 def test_multiple_reads_of_one_frame_are_not_independent_seeds(self):
  args=list(self.input());args[4][0]['readings']=args[4][0]['readings'][:1]*3;c,p,f,t=build_inputs(*args);self.assertFalse(t)
 def test_visually_verified_dorsal_can_seed_a_context(self):
  args=list(self.input());args[4][0]['readings']=args[4][0]['readings'][:1];args[4][0]['readings'][0]['source']='verified_training_reference';c,p,f,t=build_inputs(*args);self.assertEqual(t,{'c41'})
 def test_occluded_body_and_too_few_pixels_are_not_references(self):
  b={'box':[0,0,30,100],'confidence':.9};other={'box':[0,0,30,60]};self.assertFalse(acceptable_box(b,[b,other]));b['box']=[0,0,30,40];self.assertFalse(acceptable_box(b,[b]))
 def test_far_views_are_kept_even_with_many_sharp_near_views(self):
  features=np.eye(100);cs=[{'key':str(i),'track_id':i,'context_id':str(i),'frame':i,'time':i,'distance':'far' if i<10 else 'near','kind':'appearance','feature_index':i,'quality':.6 if i<10 else 1} for i in range(100)]
  selected=choose_references(cs,features,64);self.assertEqual(len(selected),64);self.assertEqual(sum(c['distance']=='far' for c in selected),10);self.assertEqual(len({c['key'] for c in selected}),64)
 def test_nearly_identical_instants_are_not_repeated_as_new_photos(self):
  cs=[{'key':str(i),'track_id':i,'context_id':'one','frame':i,'time':i*.1,'distance':'far','kind':'dorsal','feature_index':i,'quality':1} for i in range(4)];self.assertEqual(len(choose_references(cs,np.eye(4))),1)
 def test_far_names_cannot_be_enabled_by_a_single_validation_context(self):
  pred=np.array([[.99,.01]]*10);thresholds,checks=calibrate_thresholds(pred,np.array([41]*10),np.array(['same']*10),np.array([60]*10),[41,22]);self.assertEqual(thresholds['41:far'],1.1)
 def test_safe_far_threshold_requires_precision_and_independent_contexts(self):
  pred=np.array([[.99,.01]]*10);thresholds,checks=calibrate_thresholds(pred,np.array([41]*10),np.array(['a']*5+['b']*5),np.array([60]*10),[41,22]);self.assertLess(thresholds['41:far'],1)
  thresholds,_=calibrate_thresholds(pred,np.array([41]*7+[22]*3),np.array(['a']*5+['b']*5),np.array([60]*10),[41,22]);self.assertEqual(thresholds['41:far'],1.1)
 def test_augmentations_stay_in_their_source_context_fold(self):
  rng=np.random.default_rng(1);xs=[];ys=[];gs=[]
  for n in (22,41):
   for group in range(6):
    for i in range(4):xs.append(np.array([n==22,n==41],float)+rng.normal(0,.01,2));ys.append(n);gs.append(f'{n}-{group}')
  x=np.array(xs);y=np.array(ys);g=np.array(gs);model,thresholds,q,pred=train_and_evaluate(np.vstack([x,x]),np.hstack([y,y]),np.hstack([g,g]),x,y,g,np.array([60]*len(x)),np.ones(len(x),bool))
  self.assertEqual(len(q['folds']),3);self.assertTrue(all(not f['context_leakage'] for f in q['folds']));self.assertGreater(q['heldout_comparison']['far']['expanded_bank_proxy_accuracy'],.9)
 def test_jersey_reference_crops_cover_independent_instants(self):
  cs=[{'file':f'{i}.jpg','frame':i,'time':i*.2,'quality':100-i,'height':65} for i in range(100)]
  kept=retain_ocr_candidates(cs);self.assertEqual(len(kept),24);self.assertTrue(all(b['time']-a['time']>=.55 for a,b in zip(kept,kept[1:])))
 def test_recovery_follows_observations_when_context_ids_are_regenerated(self):
  rs=[{'frame':30,'tracks':[{'id':8,'player_id':'orange-41','person_track_id':'new-context'}]}];ps=[{'accepted':True,'context_id':'old-context','number':41}]
  recovered=summarize_recovery(rs,ps,{'old-context':[(30,'8')]});self.assertTrue(recovered[0]['kept_after_exclusivity']);self.assertEqual(recovered[0]['resolved_context_ids'],['new-context'])
 def test_more_jersey_candidates_preserve_distant_readable_crops(self):
  cs=[{'file':f'{i}.jpg','frame':i,'quality':1000-i,'height':200} for i in range(30)]+[{'file':'far.jpg','frame':50,'quality':20,'height':65}]
  kept=retain_ocr_candidates(cs);self.assertEqual(len(kept),24);self.assertIn('far.jpg',[c['file'] for c in kept])

if __name__=='__main__':unittest.main()
