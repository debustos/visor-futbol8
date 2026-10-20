"""Identity, sequence and persistent review regressions, using isolated fixtures."""
import unittest,tempfile,json,shutil,sqlite3,threading,urllib.request,urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
import numpy as np
from server import App,ROOT,handler_for
from visual_memory import reconstruct
from sequence_engine import sequence_actions
from analytics_v3 import profiles_for
from pitch_geometry import marking_evidence

class ReconstructionTests(unittest.TestCase):
    def test_conflicting_numbers_split_a_track_instead_of_labelling_every_frame(self):
        records=[{'time':i*.2,'tracks':[{'id':1,'kit':'orange','position':[40+i*.1,50]}]} for i in range(10)]
        readings=[{'time':i*.2,'frame':i,'text':'41' if i<5 else '7','score':.99,'localized':True} for i in (1,2,7,8)]
        result,segments,memory,q=reconstruct(records,[],np.zeros((0,2)),[{'track_id':1,'readings':readings}],{41:{},7:{}})
        self.assertEqual(len(segments),2);self.assertEqual(result[0]['tracks'][0]['player_id'],'orange-41');self.assertEqual(result[-1]['tracks'][0]['player_id'],'orange-7')
    def test_no_double_identity_in_same_frame(self):
        records=[{'time':i*.2,'tracks':[{'id':j,'kit':'orange','position':[j*10,50]} for j in (1,2)]} for i in range(3)]
        evidence=[{'track_id':j,'readings':[{'frame':i,'time':i*.2,'text':'41','score':.99,'localized':True} for i in (0,2)]} for j in (1,2)]
        result,_,_,q=reconstruct(records,[],np.zeros((0,2)),evidence,{41:{}})
        self.assertTrue(all(sum(b.get('player_id')=='orange-41' for b in r['tracks'])<=1 for r in result));self.assertGreater(q['duplicate_claims_rejected'],0)
    def test_dense_frames_do_not_triple_observed_seconds(self):
        roster=[{'jersey_number':41,'nickname':'busi'}]
        def records(fps):return [{'time':i/fps,'tracks':[{'id':1,'kit':'orange','player_id':'orange-41','position':[50,50],'identity':{'method':'jersey_vote'}}]} for i in range(fps)]
        self.assertEqual(profiles_for(records(5),[],roster,1)[0]['visible_seconds'],1)
        self.assertEqual(profiles_for(records(15),[],roster,1)[0]['visible_seconds'],1)
    def test_geometry_rejected_samples_are_excluded(self):
        r=[{'time':0,'geometry':{'state':'rejected'},'tracks':[{'id':1,'player_id':'orange-41','position':[50,50]}]}]
        p=profiles_for(r,[],[{'jersey_number':41}],1)[0];self.assertEqual(p['mapped_samples'],0);self.assertGreater(p['visible_seconds'],0)
    def test_missing_ball_path_does_not_make_an_estimated_pass(self):
        rs=[]
        for i in (0,1,8,9):
            tid=1 if i<2 else 2;x=10 if tid==1 else 30
            rs.append({'time':i*.1,'ball':{'confidence':.9,'position':[x,50]},'possession':{'track_id':tid,'distance':.1},'tracks':[{'id':tid,'kit':'orange','player_id':f'orange-{tid}','position':[x,50]}]})
        es,q=sequence_actions(rs,[]);self.assertEqual(len(es),1);self.assertEqual(es[0]['state'],'candidate')
    def test_reviewed_identity_can_seed_memory_without_a_dorsal(self):
        records=[{'time':i*.2,'tracks':[{'id':1,'kit':'orange','position':[50,50]}]} for i in range(5)]
        rows=[{'index':i,'track_id':1,'time':i*.2,'frame':i} for i in range(5)];features=np.tile([1.,0.],(5,1));reviews=[{'category':'identity','track_id':1,'start':0,'end':.8,'player_id':'orange-41','decision':'confirmed'}]
        result,_,memory,q=reconstruct(records,rows,features,[],{41:{}},reviews=reviews)
        self.assertTrue(all(r['tracks'][0]['player_id']=='orange-41' for r in result));self.assertEqual(memory[0]['references'][0]['source'],'manual_review')
    def test_rejected_identity_is_not_relearned_from_ocr(self):
        records=[{'time':i*.2,'tracks':[{'id':1,'kit':'orange','position':[50,50]}]} for i in range(3)];evidence=[{'track_id':1,'readings':[{'frame':i,'time':i*.2,'text':'41','score':.99,'localized':True} for i in (0,2)]}];review=[{'category':'identity','track_id':1,'start':0,'end':.4,'decision':'rejected'}]
        result,_,memory,q=reconstruct(records,[],np.zeros((0,2)),evidence,{41:{}},reviews=review);self.assertTrue(all(r['tracks'][0]['player_id'] is None for r in result));self.assertEqual(memory,[])
    def test_small_sided_line_shape_works_with_opencv5(self):
        import cv2
        img=np.full((1080,1920,3),(70,130,70),np.uint8);cv2.line(img,(100,700),(1800,700),(150,60,30),4)
        q=marking_evidence(img,np.eye(3));self.assertIn(q['state'],('approximate','line_supported','rejected'))

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);shutil.copyfile(ROOT/'plantilla.json',self.root/'plantilla.json');(self.root/'data').mkdir();(self.root/'automatic/chunks').mkdir(parents=True)
        self.write('data/metadata',{'duration':100,'source':'fixture.mp4'});self.write('automatic/review-manifest',{'source_key':'fixture-v3'});self.write('automatic/quality',{})
        self.events=[{'id':'event-a','category':'event','time':1,'kind':'pass','player_id':'orange-41','receiver_id':'orange-7','outcome':'complete','state':'candidate','source_track':1}, {'id':'event-b','category':'event','time':1,'kind':'pass','player_id':'orange-41','receiver_id':'orange-7','outcome':'complete','state':'candidate','source_track':1}, {'id':'event-g','category':'event','time':20,'kind':'goal','player_id':'orange-7','outcome':'goal','state':'candidate'}, {'id':'event-assist','category':'event','time':19,'kind':'assist','player_id':'orange-41','outcome':'unknown','state':'candidate'}]
        self.ident={'id':'identity-A1-S0','category':'identity','track_id':1,'player_id':None,'start':0,'end':2,'time':0}
        self.write('automatic/uncertainties',[*self.events,self.ident,{'id':'lineup','category':'lineup','time':0,'players':[]}]);self.write('automatic/actions',self.events);self.write('automatic/lineup',{'identified_candidates':[],'substitutions':[]});self.records=[{'time':i*.2,'tracks':[{'id':1,'kit':'orange','player_id':None,'position':[50,50]}]} for i in range(11)];self.write('automatic/chunks/000',self.records)
        roster=json.loads((self.root/'plantilla.json').read_text())['players'];self.write('automatic/profiles',profiles_for(self.records,self.events,roster,100));self.app=App(self.root);self.engine=self.app.review_engine
    def write(self,name,data):(self.root/(name+'.json')).write_text(json.dumps(data),encoding='utf8')
    def save(self,id,data=None,decision='confirmed'):return self.engine.save(id,{'source_key':'fixture-v3','decision':decision,'data':data or {}})
    def tearDown(self):self.tmp.cleanup()
    def test_confirm_persist_undo_and_never_write_old_events(self):
        self.save('event-a');p=next(p for p in self.engine.effective()['profiles'] if p['id']=='orange-41');self.assertEqual(p['metrics']['passes']['confirmed_value'],1);self.assertIsNone(p['metrics']['passes']['value']);self.assertEqual(App(self.root).review_engine.decisions()['event-a']['decision'],'confirmed');self.assertEqual(self.app.items('event'),[]);self.engine.undo('event-a');self.assertFalse(self.engine.decisions())
    def test_identity_interval_updates_heatmap_and_undo_restores(self):
        self.save(self.ident['id'],{'player_id':'orange-41','start':.4,'end':.8},'corrected');rs=self.engine.chunk(0);self.assertEqual(sum(b['player_id']=='orange-41' for r in rs for b in r['tracks']),3);p=next(p for p in self.engine.effective()['profiles'] if p['id']=='orange-41');self.assertEqual(p['mapped_samples'],3);self.engine.undo(self.ident['id']);self.assertEqual(sum(bool(b.get('player_id')) for r in self.engine.chunk(0) for b in r['tracks']),0)
    def test_rejected_action_does_not_count(self):
        self.save('event-a',decision='rejected');self.assertNotIn('event-a',[e['id'] for e in self.engine.effective()['actions']])
    def test_duplicate_confirmed_pass_rejected(self):
        self.save('event-a')
        with self.assertRaises(ValueError):self.save('event-b')
    def test_stale_analysis_rejected(self):
        with self.assertRaises(ValueError):self.engine.save('event-a',{'source_key':'old','decision':'confirmed'})
    def test_lineup_requires_eight_distinct_players(self):
        with self.assertRaises(ValueError):self.save('lineup',{'players':['orange-41']*8})
        ids=list(self.app.players)[:8];self.save('lineup',{'players':ids});self.assertEqual(self.engine.effective()['lineup']['state'],'confirmed')
    def test_assistance_dependency_survives_rejection_and_undo(self):
        with self.assertRaises(ValueError):self.save('event-assist',{'goal_id':'event-g'})
        self.save('event-g');self.save('event-assist',{'goal_id':'event-g'})
        with self.assertRaises(ValueError):self.save('event-g',decision='rejected')
        with self.assertRaises(ValueError):self.engine.undo('event-g')
        self.engine.undo('event-assist');self.engine.undo('event-g')
    def test_omitted_action_is_persistent_and_counts_only_when_confirmed(self):
        item=self.engine.propose({'source_key':'fixture-v3','category':'event','time':30});self.assertIn(item['id'],[q['id'] for q in App(self.root).review_engine.queue()]);self.save(item['id'],{'player_id':'orange-41','kind':'goal','outcome':'goal','time':30});p=next(p for p in self.engine.effective()['profiles'] if p['id']=='orange-41');self.assertEqual(p['metrics']['goals']['confirmed_value'],1);self.assertEqual(p['metrics']['shots']['confirmed_value'],1)
    def test_review_requires_session_token_and_survives_http_reload(self):
        http=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.app));thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{http.server_port}'
        try:
            payload=json.dumps({'source_key':'fixture-v3','decision':'confirmed','data':{}}).encode()
            with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(urllib.request.Request(url+'/api/review/decisions/event-a',data=payload))
            self.assertEqual(err.exception.code,403)
            with urllib.request.urlopen(urllib.request.Request(url+'/api/review/decisions/event-a',data=payload,headers={'X-Review-Token':self.app.token})) as r:self.assertEqual(r.status,201)
            with urllib.request.urlopen(url+'/api/review/queue') as r:self.assertEqual(json.loads(r.read())[0]['review_state'],'confirmed')
        finally:http.shutdown();http.server_close();thread.join()
if __name__=='__main__':unittest.main()
