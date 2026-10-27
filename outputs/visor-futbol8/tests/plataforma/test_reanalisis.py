import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from f8.plataforma.server import App,ROOT
from f8.plataforma.season_store import SeasonStore
from f8.plataforma.analysis_jobs import AnalysisJobs
from f8.plataforma.analysis_worker import run,STEPS

class ForegroundReanalysisTests(unittest.TestCase):
    """reanalizar.ps1 uses the same stages and job queue as the Analizar button."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'data').mkdir();(self.root/'plantilla.json').write_bytes((ROOT/'plantilla.json').read_bytes());(self.root/'data/metadata.json').write_text(json.dumps({'source':'unused','duration':10}))
        self.app=App(self.root);self.store=SeasonStore(self.app);self.app.season=self.store;self.manager=AnalysisJobs(self.store,python_executable=sys.executable);self.manager.work=self.root/'work'
        self.source=self.root/'video.mp4';self.source.write_bytes(b'video')
        with patch.object(self.store,'probe',side_effect=lambda s:(str(s),str(s),{'source':str(s),'duration':10})):self.store.register({'round':3,'parts':[{'half':1,'source':str(self.source)}]})
        auto=self.store.context(3,1).root/'automatic';(auto/'status.json').write_text('{"state":"complete"}');(auto/'profiles.json').write_text('[]')
    def tearDown(self):self.temp.cleanup()
    def test_force_creates_a_job_for_a_complete_part_without_spawning_a_worker(self):
        self.assertTrue(self.manager.start(3,1).get('already_complete'))
        with patch('f8.plataforma.analysis_jobs.subprocess.Popen') as popen:job=self.manager.start(3,1,launch=False,force=True)
        popen.assert_not_called();self.assertTrue(job['created']);self.assertEqual(job['state'],'queued')
        again=self.manager.start(3,1,launch=False,force=True);self.assertFalse(again.get('created'));self.assertEqual(again['id'],job['id'])
    def test_omitted_stages_are_not_run(self):
        job=self.manager.start(3,1,launch=False,force=True)
        with patch('f8.plataforma.analysis_worker.Pipeline') as pipeline:run(self.manager,job['id'],{'detection','jersey'})
        steps=pipeline.call_args[0][1];self.assertEqual(len(steps),len(STEPS)-2);self.assertNotIn('detection',[s[0] for s in steps])

if __name__=='__main__':unittest.main()
