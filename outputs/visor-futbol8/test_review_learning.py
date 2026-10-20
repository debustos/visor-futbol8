from contextlib import closing
import json,sqlite3,tempfile,unittest,copy,sys,time
from pathlib import Path
from unittest.mock import patch
import numpy as np
from learning_jobs import LearningJobs
from review_learning import train_identity,identity_predictions,train_actions,action_labels,apply_overlay,probabilities,part_inputs
from automatic_core import write_json


class LearningQueueTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'automatic').mkdir();(self.root/'data').mkdir();write_json(self.root/'data/metadata.json',{'duration':10});write_json(self.root/'automatic/review-manifest.json',{'source_key':'video-A'});write_json(self.root/'automatic/quality.json',{'version':9});self.manager=LearningJobs(self.root,self.root/'work',python=sys.executable,debounce=15)
  with closing(sqlite3.connect(self.root/'revisiones.sqlite3')) as db,db:db.execute('CREATE TABLE automatic_reviews(item_id TEXT,source_key TEXT,payload TEXT)')
 def tearDown(self):self.tmp.cleanup()
 def review(self,pid='orange-7',key='video-A'):
  with closing(sqlite3.connect(self.root/'revisiones.sqlite3')) as db,db:
   db.execute('DELETE FROM automatic_reviews');db.execute('INSERT INTO automatic_reviews VALUES(?,?,?)',('i',key,json.dumps({'item_id':'i','category':'identity','decision':'corrected','track_id':1,'start':0,'end':2,'player_id':pid})))
 def test_changes_queue_and_group_without_duplicate_generation(self):
  self.review();one=self.manager.sync();self.assertEqual(self.manager.sync(),one);self.assertEqual(self.manager.job()['state'],'queued');self.assertGreater(self.manager.job()['due_at'],time.time());self.review('orange-22');two=self.manager.sync();self.assertEqual(two,one+1);self.assertEqual(self.manager.job(one)['state'],'superseded')
 def test_stale_training_cannot_publish_over_newer_correction(self):
  self.review();one=self.manager.sync();self.manager.claim(one);self.review('orange-22');self.assertFalse(self.manager.publish(one,{'summary':{},'parts':{}}));self.assertIsNone(self.manager.control()[1]);self.assertEqual(self.manager.job(one)['state'],'superseded')
 def test_undo_invalidates_active_model_and_removes_label(self):
  self.review();one=self.manager.sync();part=self.manager.snapshot()['parts'][0];bundle={'summary':{},'parts':{str(self.root.resolve()):{'source_key':'video-A','quality_stamp':part['quality_stamp'],'identities':[1]}}};self.assertTrue(self.manager.publish(one,bundle));self.assertTrue(self.manager.overlay(self.root))
  with closing(sqlite3.connect(self.root/'revisiones.sqlite3')) as db,db:db.execute('DELETE FROM automatic_reviews')
  self.manager.sync();self.assertEqual(self.manager.overlay(self.root),{});self.assertEqual(self.manager.snapshot()['parts'][0]['reviews'],[])
 def test_old_video_reviews_do_not_train_current_source(self):
  self.review(key='video-old');self.assertEqual(self.manager.sync(),0);self.assertEqual(self.manager.snapshot()['parts'][0]['reviews'],[])
 def test_same_generation_can_only_be_claimed_once(self):
  self.review();g=self.manager.sync();self.assertTrue(self.manager.claim(g));self.assertFalse(self.manager.claim(g))
 def test_restart_recovers_unfinished_worker(self):
  self.review();g=self.manager.sync();self.manager.update(g,state='running',worker_pid=987654)
  with self.manager.connect() as db:
   q=self.manager.job(g);q['updated_at']=0;db.execute('UPDATE jobs SET payload=? WHERE generation=?',(json.dumps(q),g))
  with patch('learning_jobs.alive',return_value=False):self.manager.tick(launch=False)
  self.assertEqual(self.manager.job(g)['state'],'failed');self.assertGreater(self.manager.control()[0],g)
 def test_dirty_source_analysis_disables_existing_overlay(self):
  self.review();g=self.manager.sync();part=self.manager.snapshot()['parts'][0];self.manager.publish(g,{'summary':{},'parts':{str(self.root.resolve()):{'source_key':'video-A','quality_stamp':part['quality_stamp']}}});write_json(self.root/'automatic/quality.json',{'version':10});self.assertEqual(self.manager.overlay(self.root),{})


class LearningModelTests(unittest.TestCase):
 def test_binary_serialized_probability_has_two_classes(self):
  p=probabilities({'coef':[[2]],'intercept':[0],'classes':[7,22],'scale':None},[[1]]);self.assertEqual(p.shape,(1,2));self.assertAlmostEqual(float(p.sum()),1);self.assertGreater(p[0,1],p[0,0])
 def dataset(self):
  rng=np.random.default_rng(5);y=np.repeat([7,22],24);x=rng.normal(0,.01,(48,872));x[:,0]=np.where(y==7,30,-30);groups=np.array([f'{n}-g{i//8}' for n in (7,22) for i in range(24)]);return x,y,groups,np.full(48,70),y.copy()
 def test_validation_groups_are_separate_and_candidate_is_usable(self):
  model,thresholds,q=train_identity(*self.dataset());self.assertTrue(q['active']);self.assertTrue(all(not f['context_leakage'] for f in q['folds']));self.assertEqual(q['context_balanced_validation_accuracy'],1)
 def test_one_trajectory_per_player_does_not_validate_itself(self):
  x,y,g,h,b=self.dataset();g=np.array([str(v) for v in y]);model,thresholds,q=train_identity(x,y,g,h,b);self.assertIsNone(model);self.assertFalse(q['active'])
 def test_single_reviewed_action_does_not_enable_detector(self):
  models,q=train_actions([{'kind':'goal','label':1,'x':[0]*16,'group':'one'}]);self.assertEqual(models,{});self.assertFalse(q['goal']['active'])
 def test_corrected_type_is_negative_for_original_type(self):
  d={'part':{'source_key':'v'},'queue':[],'events':[{'id':'e','kind':'pass','time':1,'outcome':'complete'}],'reviews':[{'item_id':'e','category':'event','decision':'corrected','kind':'shot'}]};labels=action_labels(d);self.assertEqual(labels[0]['label'],0);self.assertEqual(labels[0]['kind'],'pass')
 def test_overlapping_action_clips_stay_in_same_validation_group(self):
  es=[{'id':str(i),'kind':'pass','time':t,'evidence_start':t-3,'evidence_end':t+3,'outcome':'complete'} for i,t in enumerate((2,6,20))];d={'part':{'source_key':'v'},'queue':[],'events':es,'reviews':[{'item_id':e['id'],'category':'event','decision':'confirmed','kind':'pass','outcome':'complete'} for e in es]};ls=action_labels(d);self.assertEqual(ls[0]['group'],ls[1]['group']);self.assertNotEqual(ls[1]['group'],ls[2]['group'])
 def records(self,manual=False,duplicate=False):
  rs=[]
  for i in range(8):
   b={'id':1,'player_id':None,'kit':'orange','person_track_id':'p','box':[0,0,40,100],'identity':{'method':'manual_review','state':'rejected'} if manual else {'state':'unknown'}};bs=[b]
   if duplicate:bs.append({'id':2,'player_id':'orange-7','kit':'orange','person_track_id':'other','box':[100,0,140,100],'identity':{'state':'confirmed'}})
   rs.append({'frame':i,'time':i,'tracks':bs,'ball':None})
  return rs
 def overlay(self):return {'generation':1,'identities':[{'player_id':'orange-7','score':.95,'observations':[[i,'1'] for i in range(8)]}],'actions':{}}
 def test_unknown_body_keeps_one_learned_identity_for_context(self):
  rs=self.records();self.assertEqual(apply_overlay(rs,[],self.overlay()),1);self.assertTrue(all(r['tracks'][0]['player_id']=='orange-7' for r in rs))
 def test_manual_rejection_is_never_refilled_by_learning(self):
  rs=self.records(manual=True);self.assertEqual(apply_overlay(rs,[],self.overlay()),0);self.assertIsNone(rs[0]['tracks'][0]['player_id'])
 def test_learning_cannot_put_one_player_in_two_bodies(self):self.assertEqual(apply_overlay(self.records(duplicate=True),[],self.overlay()),0)

if __name__=='__main__':unittest.main()
