"""Queue, persistence and completion boundaries for browser-triggered analysis."""
import json,os,sys,tempfile,threading,time,unittest,urllib.request,urllib.error
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from f8.plataforma.server import App,ROOT,handler_for
from f8.plataforma.season_store import SeasonStore
from f8.plataforma.analysis_jobs import AnalysisJobs
from f8.plataforma.analysis_worker import Pipeline,fraction,run

class AnalysisJobTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'data').mkdir();(self.root/'plantilla.json').write_bytes((ROOT/'plantilla.json').read_bytes());(self.root/'data/metadata.json').write_text(json.dumps({'source':'unused','duration':10,'width':1920,'height':1080}));self.app=App(self.root);self.store=SeasonStore(self.app);self.app.season=self.store;self.manager=AnalysisJobs(self.store,python_executable=sys.executable);self.app.analysis_jobs=self.manager;self.manager.work=self.root/'worker-test-work'
  self.probe=patch.object(self.store,'probe',side_effect=lambda source:(str(source),str(source),{'source':str(source),'duration':10,'width':1920,'height':1080}));self.probe.start();self.spawn=patch('f8.plataforma.analysis_jobs.subprocess.Popen',return_value=SimpleNamespace(pid=os.getpid()));self.popen=self.spawn.start();self.source=self.root/'test video.mp4';self.source.write_bytes(b'video');self.store.register({'round':2,'parts':[{'half':2,'source':str(self.source)}]})
 def tearDown(self):self.spawn.stop();self.probe.stop();self.temp.cleanup()
 def start(self):return self.manager.start(2,2)
 def test_double_click_and_concurrent_requests_launch_only_one_worker(self):
  jobs=[];threads=[threading.Thread(target=lambda:jobs.append(self.start())) for i in range(8)]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(len(jobs),8);self.assertEqual(len({j['id'] for j in jobs}),1);self.assertEqual(self.popen.call_count,1)
 def test_only_registered_parts_and_integer_identifiers(self):
  for r,h in [(2,1),(99,2),(True,2),(2,True),(2,2.0)]:
   with self.subTest(r=r,h=h),self.assertRaises(ValueError):self.manager.start(r,h)
  self.popen.assert_not_called()
 def test_missing_original_does_not_launch(self):
  self.source.unlink()
  with self.assertRaises(ValueError):self.start()
  self.popen.assert_not_called();self.assertFalse(self.manager.list())
 def test_completed_part_is_not_reanalysed(self):
  auto=self.store.context(2,2).root/'automatic';(auto/'status.json').write_text('{"state":"complete"}');(auto/'profiles.json').write_text('[]')
  self.assertTrue(self.start()['already_complete']);self.popen.assert_not_called()
 def test_progress_persists_across_manager_reload(self):
  j=self.start();self.manager.update(j['id'],state='running',progress=42.5,stage_label='Siguiendo el balón')
  again=AnalysisJobs(SeasonStore(self.app),python_executable=sys.executable);self.assertEqual(again.snapshot()['jobs'][0]['progress'],42.5);self.assertEqual(again.start(2,2)['id'],j['id'])
 def test_failed_job_can_retry_even_if_intermediate_stats_were_written(self):
  j=self.start();self.manager.update(j['id'],state='failed');auto=self.store.context(2,2).root/'automatic';(auto/'status.json').write_text('{"state":"complete"}');(auto/'profiles.json').write_text('[]')
  again=self.start();self.assertNotEqual(again['id'],j['id']);self.assertEqual(again['state'],'queued');self.assertEqual(self.popen.call_count,2)
 def test_intermediate_complete_status_does_not_count_as_analyzed(self):
  j=self.start();self.manager.update(j['id'],state='running',progress=75);auto=self.store.context(2,2).root/'automatic';(auto/'status.json').write_text('{"state":"complete"}');(auto/'profiles.json').write_text('[]')
  summary=self.store.summary();self.assertEqual(summary['analyzed_parts'],0);self.assertEqual(summary['parts'][0]['state'],'processing')
  self.manager.update(j['id'],state='complete',progress=100);self.assertEqual(self.store.summary()['analyzed_parts'],1)
 def test_dead_process_reports_failure_and_never_fake_completion(self):
  j=self.start();self.manager.update(j['id'],state='running',progress=33,created_at=(datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat())
  with patch('f8.plataforma.analysis_jobs.alive',return_value=False):result=self.manager.list()[0]
  self.assertEqual(result['state'],'failed');self.assertEqual(result['progress'],33)
 def test_worker_failure_becomes_retryable(self):
  j=self.start()
  with patch('f8.plataforma.analysis_worker.Pipeline') as pipeline:
   pipeline.return_value.execute.side_effect=RuntimeError('No se pudo leer el vídeo');run(self.manager,j['id'])
  self.assertEqual(self.manager.get(j['id'])['state'],'failed');self.assertIn('leer el vídeo',self.manager.get(j['id'])['error'])
 def test_partial_progress_does_not_export_private_paths(self):
  j=self.start();value=self.manager.snapshot()['jobs'][0];self.assertEqual(value['progress'],0);self.assertNotIn('root',value);self.assertNotIn('cache',value);self.assertNotIn('source',value)
 def test_http_requires_host_token_and_starts_the_selected_part(self):
  http=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.app));t=threading.Thread(target=http.serve_forever,daemon=True);t.start();url=f'http://127.0.0.1:{http.server_port}'
  try:
   data=json.dumps({'round':2,'half':2}).encode()
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(urllib.request.Request(url+'/api/season/analysis',data=data))
   self.assertEqual(error.exception.code,403);self.popen.assert_not_called()
   request=urllib.request.Request(url+'/api/season/analysis',data=data,headers={'X-Review-Token':self.app.token})
   with urllib.request.urlopen(request) as response:self.assertEqual(response.status,202);job=json.load(response)
   self.assertEqual(job['half'],2);self.manager.update(job['id'],state='running',progress=64)
   status=json.load(urllib.request.urlopen(url+'/api/automatic/status?round=2&half=2'));self.assertEqual(status['state'],'processing');self.assertEqual(status['done'],64)
   self.assertEqual(json.load(urllib.request.urlopen(url+'/api/season/analysis/jobs'))['jobs'][0]['progress'],64)
  finally:http.shutdown();http.server_close();t.join()
 def test_job_without_started_worker_becomes_retryable_after_restart(self):
  j=self.start();self.manager.update(j['id'],worker_pid=None,created_at=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat())
  again=AnalysisJobs(SeasonStore(self.app),python_executable=sys.executable);self.assertEqual(again.latest(2,2)['state'],'failed');self.assertNotEqual(again.start(2,2)['id'],j['id'])
 def test_modified_original_fails_before_running_model_steps(self):
  j=self.start();self.source.write_bytes(b'changed original video')
  with self.assertRaisesRegex(RuntimeError,'vídeo cambió'):Pipeline(self.manager).execute(self.manager.get(j['id']))
  self.assertEqual(self.popen.call_count,1)
 def test_fraction_uses_actual_phase_samples_and_clamps(self):
  self.assertEqual(fraction({'done':3,'total':10},20),.3);self.assertEqual(fraction({'done_seconds':30,'total_seconds':20},20),1);self.assertEqual(fraction({'stage':'temporal','seconds':10},20),.5);self.assertIsNone(fraction({'state':'complete'},20))
if __name__=='__main__':unittest.main()
