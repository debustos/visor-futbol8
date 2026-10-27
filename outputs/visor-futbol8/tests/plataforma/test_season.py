"""Match isolation and accounting across halves, rounds, reviews and weighted maps."""
import copy,csv,io,json,os,sqlite3,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from f8.plataforma.domain import METRICS
from f8.plataforma.server import App,handler_for,ROOT
from f8.plataforma.season_store import SeasonStore,aggregate_parts

PLAYERS=[{'id':'orange-41','jersey_number':41,'nickname':'busi'},{'id':'orange-1','jersey_number':1,'nickname':'razquin'}]
def part(round=2,half=1,state='complete',direction='up'):
    return {'round':round,'half':half,'duration':100,'state':state,'attack_direction':direction}
def profile(confirmed=None,estimated=None,points=None):
    return {'id':'orange-41','jersey_number':41,'nickname':'busi','visible_seconds':10,'metrics':{k:{'confirmed_value':confirmed if k=='passes' else None,'value':estimated if k=='passes' else None,'candidates':2 if k=='shots' else 0} for k in METRICS},'heatmap_points':points or [],'actions':[{'id':'same-id','time':5,'kind':'pass','state':'candidate','player_id':'orange-41'}]}
def total(parts,profiles):
    return aggregate_parts(PLAYERS,parts,{(p['round'],p['half']):{'profiles':[q]} for p,q in zip(parts,profiles)}, {'kind':'season'})
class SeasonAccountingTests(unittest.TestCase):
    def test_all_eleven_metrics_sum_separate_states_across_halves_and_rounds(self):
        parts=[part(),part(2,2),part(3,1)];profiles=[profile(2,1),profile(3,4),profile(1,2)]
        p=total(parts,profiles)['players'][0];self.assertEqual(len(p['metrics']),11);self.assertEqual(p['metrics']['passes']['confirmed_value'],6);self.assertEqual(p['metrics']['passes']['value'],7);self.assertEqual(p['metrics']['shots']['candidates'],6)
    def test_unknown_stays_unknown(self):
        p=total([part(),part(2,2)],[profile(),profile()])['players'][0];self.assertIsNone(p['metrics']['passes']['value']);self.assertIsNone(p['metrics']['passes']['confirmed_value'])
    def test_explicit_zero_preserved_by_aggregation(self):
        p=total([part(),part(2,2)],[profile(0,0),profile()])['players'][0];self.assertEqual(p['metrics']['passes']['confirmed_value'],0);self.assertEqual(p['metrics']['passes']['value'],0)
    def test_pending_half_is_missing_and_not_zero(self):
        r=total([part(),part(2,2,state='waiting')],[profile(2,1)]);self.assertEqual((r['analyzed_parts'],r['expected_parts'],r['recorded_seconds'],r['analyzed_seconds']),(1,2,200,100));self.assertEqual(r['players'][0]['metrics']['passes']['value'],1)
    def test_attack_down_rotates_both_axes_and_pools_seconds(self):
        point={'x':25,'y':75,'time':1,'weight_seconds':.07};r=total([part(),part(3,1,direction='down')],[profile(points=[point]),profile(points=[point])]);p=r['players'][0];self.assertEqual([(x['x'],x['y']) for x in p['heatmap_points']],[(25,75),(75,25)]);self.assertEqual(p['mapped_seconds'],.14)
    def test_unknown_direction_excluded_and_reported(self):
        r=total([part(direction='unknown')],[profile(points=[{'x':5,'y':10,'time':1,'weight_seconds':.2}])]);self.assertEqual(r['players'][0]['mapped_seconds'],0);self.assertEqual(r['players'][0]['excluded_direction_seconds'],.2)
    def test_bad_geometry_excluded(self):
        points=[{'x':5,'y':10,'time':1,'weight_seconds':.2,'calibration_state':'rejected'},{'x':float('nan'),'y':10,'time':2},{'x':10,'y':15,'time':3,'weight_seconds':-.1}];r=total([part()],[profile(points=points)]);self.assertEqual(r['players'][0]['mapped_seconds'],0)
    def test_same_local_event_id_is_scoped(self):
        r=total([part(),part(3,1)],[profile(),profile()]);events=r['players'][0]['actions'];self.assertNotEqual(events[0]['id'],events[1]['id']);self.assertEqual(events[0]['original_id'],events[1]['original_id']);self.assertEqual([e['round'] for e in events],[2,3])
    def test_missing_player_not_treated_as_did_not_play(self):
        r=total([part()],[profile()]);self.assertIsNone(r['players'][1]['metrics']['passes']['value']);self.assertEqual(r['players'][1]['visible_seconds'],0)

class SeasonRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'data').mkdir();(self.root/'plantilla.json').write_text((ROOT/'plantilla.json').read_text(encoding='utf8'),encoding='utf8');(self.root/'data/metadata.json').write_text(json.dumps({'source':'unused','duration':100,'width':100,'height':100}),encoding='utf8');self.app=App(self.root);self.store=SeasonStore(self.app);self.app.season=self.store
        self.probe=patch.object(self.store,'probe',side_effect=lambda src:(str(src),str(src),{'source':str(src),'duration':100,'width':100,'height':100}));self.probe.start()
    def tearDown(self):self.probe.stop();self.temp.cleanup()
    def register(self,round=2,half=1,source='video-one'):
        return self.store.register({'round':round,'parts':[{'half':half,'source':source}]})
    def analyzed(self,round=2,half=1):
        app=self.store.context(round,half);auto=app.root/'automatic';p=profile();event=p['actions'][0];event.update(category='event',outcome='unknown',source_track=None,priority=1,reason='fixture')
        (auto/'profiles.json').write_text(json.dumps([p]),encoding='utf8');(auto/'actions.json').write_text(json.dumps([event]),encoding='utf8');(auto/'uncertainties.json').write_text(json.dumps([event]),encoding='utf8');(auto/'review-manifest.json').write_text(json.dumps({'source_key':f'fixture-{round}-{half}'}),encoding='utf8');(auto/'status.json').write_text(json.dumps({'state':'complete'}),encoding='utf8');return app
    def test_persists_registry_and_preserves_idempotent_analysis(self):
        self.register();app=self.analyzed();self.register();self.assertTrue((app.root/'automatic/profiles.json').exists());again=SeasonStore(self.app);self.assertEqual(again.registry()['matches'][0]['round'],2);self.assertEqual(again.registry()['matches'][0]['analyzed_parts'],1)
    def test_duplicate_video_in_other_round_rejected_without_partial_match(self):
        self.register();
        with self.assertRaises(ValueError):self.register(3,1)
        self.assertEqual([m['round'] for m in self.store.registry()['matches']],[2])
    def test_existing_half_cannot_be_overwritten(self):
        self.register();
        with self.assertRaises(ValueError):self.register(source='different-video')
        self.assertEqual(self.store.rows()[0]['source'],'video-one')
    def test_two_halves_and_two_rounds_have_separate_databases_and_tokens(self):
        for r,h in [(2,1),(2,2),(3,1)]:self.register(r,h,f'video-{r}-{h}')
        apps=[self.store.context(r,h) for r,h in [(2,1),(2,2),(3,1)]];self.assertEqual(len({a.db_path for a in apps}),3);self.assertEqual(len({a.token for a in apps}),3)
    def test_review_updates_season_without_polluting_other_half(self):
        self.register();self.register(2,2,'video-two');a=self.analyzed();b=self.analyzed(2,2);before=self.store.summary();self.assertIsNone(before['players'][11]['metrics']['recoveries']['confirmed_value'])
        a.review_engine.save('same-id',{'source_key':a.review_engine.source_key(),'decision':'corrected','data':{'kind':'recovery','player_id':'orange-41','time':5,'outcome':'unknown'}})
        p=next(p for p in self.store.summary()['players'] if p['id']=='orange-41');self.assertEqual(p['metrics']['recoveries']['confirmed_value'],1);self.assertEqual(b.review_engine.decisions(),{})
        a.review_engine.undo('same-id');p=next(p for p in self.store.summary()['players'] if p['id']=='orange-41');self.assertIsNone(p['metrics']['recoveries']['confirmed_value'])
    def test_new_proposal_invalidates_season_candidate_counts(self):
        self.register();a=self.analyzed();before=self.store.summary();a.review_engine.propose({'category':'event','time':15,'source_key':a.review_engine.source_key()});after=self.store.summary();self.assertIsNot(before,after)
    def test_csv_preserves_unknown_and_separate_columns(self):
        self.register();self.analyzed();rows=list(csv.reader(io.StringIO(self.store.csv(self.store.summary()).decode('utf-8-sig'))));self.assertIn('Pases confirmadas',rows[0]);self.assertIn('N/D',rows[1])
    def test_invalid_round_and_half_rejected(self):
        for r,h in [(True,1),(0,1),(2,3),(2,True),(2,1.0)]:
            with self.subTest(r=r,h=h),self.assertRaises(ValueError):self.store.register({'round':r,'parts':[{'half':h,'source':'x'}]})
    def test_real_video_probe_duration_and_duplicate_copy(self):
        import cv2,numpy as np,shutil
        self.probe.stop()
        first=self.root/'test-video.mp4';second=self.root/'same-video-copy.mp4'
        writer=cv2.VideoWriter(str(first),cv2.VideoWriter_fourcc(*'mp4v'),10,(64,48))
        for i in range(20):writer.write(np.full((48,64,3),i*10,dtype=np.uint8))
        writer.release();shutil.copyfile(first,second)
        self.store.register({'round':2,'parts':[{'half':1,'source':str(first)}]})
        self.assertAlmostEqual(self.store.registry()['matches'][0]['parts'][0]['duration'],2)
        with self.assertRaises(ValueError):self.store.register({'round':3,'parts':[{'half':1,'source':str(second)}]})
    def test_scoped_runtime_uses_registered_source_and_independent_cache(self):
        import subprocess,sys
        env={**os.environ,'FOOTBALL_VIEWER_ROOT':str(self.root/'jornadas/j003/parte-2'),'FOOTBALL_CACHE_ROOT':str(self.root/'cache'),'FOOTBALL_VIDEO_SOURCE':'fixture-video-second.mp4'}
        out=subprocess.check_output([sys.executable,'-c','from f8.core import runtime_context as r; print(r.ROOT); print(r.CACHE); print(r.SOURCE)'],cwd=ROOT,env=env,text=True).splitlines()
        self.assertEqual(Path(out[0]),Path(env['FOOTBALL_VIEWER_ROOT']));self.assertEqual(Path(out[1]),Path(env['FOOTBALL_CACHE_ROOT']));self.assertEqual(out[2],env['FOOTBALL_VIDEO_SOURCE'])
    def test_http_context_media_and_review_token_are_isolated(self):
        self.register();self.register(2,2,'video-two');a=self.analyzed();b=self.analyzed(2,2)
        for app,text in [(a,b'first-half'),(b,b'second-half')]: (app.root/'media/primera-compatible.mp4').write_bytes(text)
        http=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.app));t=threading.Thread(target=http.serve_forever,daemon=True);t.start();url=f'http://127.0.0.1:{http.server_port}'
        try:
            for h,text,app in [(1,b'first-half',a),(2,b'second-half',b)]:
                self.assertEqual(urllib.request.urlopen(url+f'/media?round=2&half={h}').read(),text);boot=json.load(urllib.request.urlopen(url+f'/api/bootstrap?round=2&half={h}'));self.assertEqual(boot['token'],app.token);self.assertEqual(boot['metadata']['match_context']['half'],h)
            payload=json.dumps({'category':'event','time':5}).encode();req=urllib.request.Request(url+'/api/review/proposals?round=2&half=2',data=payload,headers={'X-Review-Token':a.token},method='POST')
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
            self.assertEqual(e.exception.code,403)
            registration=json.dumps({'round':3,'parts':[{'half':1,'source':'video-third'}]}).encode()
            req=urllib.request.Request(url+'/api/season/matches',data=registration,headers={'X-Review-Token':a.token},method='POST')
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
            self.assertEqual(e.exception.code,403)
            req=urllib.request.Request(url+'/api/season/matches',data=registration,headers={'X-Review-Token':self.app.token},method='POST')
            with urllib.request.urlopen(req) as response:self.assertEqual(response.status,201)
            self.assertEqual(self.store.rows(3)[0]['source'],'video-third')
            compact=json.load(urllib.request.urlopen(url+'/api/season/summary?round=2&compact=1'));self.assertNotIn('heatmap_points',compact['players'][0]);self.assertEqual(compact['analyzed_parts'],2)
        finally:http.shutdown();http.server_close();t.join()
if __name__=='__main__':unittest.main()
