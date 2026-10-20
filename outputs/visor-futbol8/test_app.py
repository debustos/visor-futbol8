"""Meaningful isolated tests: accounting, conflicts, persistence, HTTP video seeking."""
import json,shutil,tempfile,threading,unittest,urllib.error,urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from domain import aggregate,contributions,validate_event,validate_assignment
from server import App,handler_for,ROOT

PLAYERS={'orange-41':{},'orange-5':{},'orange-1':{}}
def event(**changes):
    return validate_event({'player_id':'orange-41','kind':'pass','time':10,'status':'confirmed','outcome':'complete',**changes},PLAYERS,100)

class AccountingTests(unittest.TestCase):
    def test_pending_does_not_count(self):
        self.assertEqual(sum(contributions(event(status='pending',ball_into_box=True,big_chance=True)).values()),0)
    def test_goal_counts_once_as_goal_and_shot(self):
        e=event(kind='shot',outcome='goal');c=contributions(e);self.assertEqual((c['goals'],c['shots'],sum(c.values())),(1,1,2))
    def test_multilabel_pass(self):
        c=contributions(event(ball_into_box=True,big_chance=True));self.assertEqual((c['passes'],c['balls_into_box'],c['big_chances']), (1,1,1))
    def test_failed_pass_is_not_automatically_loss(self):
        self.assertEqual(contributions(event(outcome='incomplete'))['turnovers'],0)
        self.assertEqual(contributions(event(outcome='incomplete',turnover=True))['turnovers'],1)
    def test_only_successful_dribbles_count(self):
        self.assertEqual(contributions(event(kind='dribble',outcome='failed'))['successful_dribbles'],0)
        self.assertEqual(contributions(event(kind='dribble',outcome='success'))['successful_dribbles'],1)
    def test_all_eleven_metrics_and_pass_results(self):
        events=[event(kind='shot',outcome='goal'),event(kind='assist',outcome='unknown'),event(kind='big_chance',outcome='unknown'),event(kind='ball_into_box',outcome='unknown'),event(kind='foul_won',outcome='unknown'),event(kind='foul_committed',outcome='unknown'),event(kind='recovery',outcome='unknown'),event(kind='dribble',outcome='success'),event(),event(kind='turnover',outcome='unknown')]
        row=aggregate(events,PLAYERS)[0];self.assertTrue(all(v==1 for v in row['metrics'].values()));self.assertEqual(row['passes_completed'],1)
    def test_rejects_invalid_data(self):
        for changes in [{'time':float('nan')},{'time':float('inf')},{'time':-1},{'time':101},{'player_id':'rival-1'},{'kind':'inventado'},{'outcome':'inventado'},{'turnover':'yes'},{'kind':'shot','outcome':'goal','big_chance':True}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):event(**changes)
    def test_interval_identity_not_entire_fragment(self):
        fragments={4:{'runs':[{'start':0,'end':30}]}}
        first=validate_assignment({'player_id':'orange-41','track_id':4,'start':25,'end':30},PLAYERS,100,fragments,[])
        self.assertEqual(first['start'],25)
        with self.assertRaises(ValueError):validate_assignment({'player_id':'orange-5','track_id':4,'start':29,'end':31},PLAYERS,100,fragments,[first])
        second=validate_assignment({'player_id':'orange-5','track_id':4,'start':0,'end':20},PLAYERS,100,fragments,[first]);self.assertEqual(second['player_id'],'orange-5')

class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);assert self.root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve());shutil.copyfile(ROOT/'plantilla.json',self.root/'plantilla.json');(self.root/'data').mkdir();self.media=self.root/'fixture.mp4';self.media.write_bytes(bytes(range(256))*10)
        (self.root/'data'/'metadata.json').write_text(json.dumps({'duration':100,'source':str(self.media)}));(self.root/'data'/'fragments.json').write_text(json.dumps([{'id':4,'runs':[{'start':0,'end':30}]}]));self.app=App(self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_persistence_and_audit(self):
        e=self.app.add('event',event());self.assertEqual(App(self.root).items('event')[0]['id'],e['id']);self.app.delete('event',e['id']);self.assertFalse(self.app.items('event'))
        with self.app.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM history').fetchone()[0],2)
    def test_duplicate_metrics_rejected(self):
        self.app.add('event',event(big_chance=True))
        with self.assertRaises(ValueError):self.app.add('event',event(kind='big_chance',outcome='unknown'))
    def test_assist_requires_goal_and_cannot_assist_self(self):
        with self.assertRaises(ValueError):self.app.add('event',event(kind='assist',outcome='unknown'))
        goal=self.app.add('event',event(kind='shot',outcome='goal',time=20))
        with self.assertRaises(ValueError):self.app.add('event',event(kind='assist',outcome='unknown',goal_event_id=goal['id']))
        assist=self.app.add('event',event(player_id='orange-5',kind='assist',outcome='unknown',goal_event_id=goal['id']))
        with self.assertRaises(ValueError):self.app.add('event',event(player_id='orange-1',kind='assist',outcome='unknown',goal_event_id=goal['id']))
        with self.assertRaises(ValueError):self.app.delete('event',goal['id'])
        with self.assertRaises(ValueError):self.app.update_event(goal['id'],event(kind='shot',outcome='off_target',time=20))
        self.app.update_event(assist['id'],{**assist,'status':'pending'});self.app.delete('event',goal['id'])
    def test_pending_edit_updates_statistics(self):
        e=self.app.add('event',event(status='pending'));self.assertEqual(self.app.statistics()[11]['metrics']['passes'],0)
        self.app.update_event(e['id'],event());self.assertEqual(self.app.statistics()[11]['metrics']['passes'],1)
    def test_http_range_and_session_token(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.app));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}'
        try:
            req=urllib.request.Request(url+'/media',headers={'Range':'bytes=10-29'})
            with urllib.request.urlopen(req) as r:self.assertEqual(r.status,206);self.assertEqual(r.headers['Content-Range'],'bytes 10-29/2560');self.assertEqual(r.read(),self.media.read_bytes()[10:30])
            with urllib.request.urlopen(urllib.request.Request(url+'/media',headers={'Range':'bytes=-10'})) as r:self.assertEqual(r.read(),self.media.read_bytes()[-10:])
            with urllib.request.urlopen(urllib.request.Request(url+'/media',method='HEAD')) as r:self.assertEqual(r.headers['Content-Length'],'2560');self.assertEqual(r.read(),b'')
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(urllib.request.Request(url+'/media',headers={'Range':'bytes=9999-'}))
            self.assertEqual(error.exception.code,416)
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(urllib.request.Request(url+'/api/events',data=json.dumps(event()).encode(),method='POST'))
            self.assertEqual(error.exception.code,403)
            with urllib.request.urlopen(urllib.request.Request(url+'/api/events',data=json.dumps(event()).encode(),headers={'X-Review-Token':self.app.token},method='POST')) as r:self.assertEqual(r.status,201)
        finally:server.shutdown();server.server_close();thread.join()

    def test_automatic_export_keeps_unknown_separate_from_zero_and_manual_events(self):
        from domain import METRICS
        self.app.add('event',event())
        auto=self.root/'automatic';auto.mkdir();metrics={k:{'value':None,'state':'unavailable','candidates':2 if k=='shots' else 0} for k in METRICS}
        profiles=[{'jersey_number':41,'nickname':'busi','visible_seconds':10,'metrics':metrics}]
        (auto/'profiles.json').write_text(json.dumps(profiles));(auto/'quality.json').write_text(json.dumps({'manual_annotation_inputs':0}))
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.app));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(url+'/api/automatic/export') as r:bundle=json.loads(r.read());self.assertIsNone(bundle['profiles'][0]['metrics']['passes']['value']);self.assertEqual(bundle['profiles'][0]['metrics']['shots']['candidates'],2)
            with urllib.request.urlopen(url+'/api/automatic/stats.csv') as r:raw=r.read().decode('utf-8-sig');import csv,io;rows=list(csv.reader(io.StringIO(raw)));self.assertEqual(rows[1][3:14],['N/D']*11);self.assertEqual(rows[1][25:36],['N/D']*11);self.assertIn('candidatos',raw)
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main(verbosity=2)
