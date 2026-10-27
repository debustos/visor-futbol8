import importlib.util,json,re,tempfile,threading,unittest,urllib.error,urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from f8.plataforma.pipeline import pipeline_steps,validate
from f8.plataforma.rutas import load_routes,find_route
from f8.plataforma.paginas import render_index
from f8.plataforma.analysis_worker import STEPS
from f8.plataforma.server import App,ROOT,handler_for

# Order before Phase 0 (analysis_worker.STEPS). Moving a stage changes results.
PREVIOUS_ORDER=['prepare','detection','temporal','jersey','ball','fusion','appearance','memory','dense_ball','ball_continuity','jersey_text','identities','context','dorsal_guard_seed','references','far_identity','native_ball','dorsal_guard_final','visual_shots','commit','gallery','maps','validation','playback']

class StageRegistryTests(unittest.TestCase):
    def test_declared_stages_keep_the_previous_pipeline_order(self):
        self.assertEqual([s[1] for s in pipeline_steps()],PREVIOUS_ORDER)
        self.assertEqual([s[0] for s in STEPS],PREVIOUS_ORDER)
    def test_every_stage_runs_an_existing_module_of_its_owner(self):
        for owner,module in __import__('f8.core.registro',fromlist=['x']).declarations('etapas'):
            for entry in module.ETAPAS:
                self.assertIsNotNone(importlib.util.find_spec(entry[3]),entry[3])
                self.assertEqual(entry[3].split('.')[1],owner,'Una etapa ejecuta código de su propio módulo')
    def test_duplicate_positions_or_keys_are_rejected(self):
        a=(10,'a','A','f8.x.a',[],1)
        with self.assertRaisesRegex(ValueError,'Orden 10'):validate([('m1',a),('m2',(10,'b','B','f8.x.b',[],1))])
        with self.assertRaisesRegex(ValueError,'Clave a'):validate([('m1',a),('m2',(20,'a','B','f8.x.b',[],1))])
        self.assertEqual([e[1] for e in validate([('m2',(20,'b','B','f8.x.b',[],1)),('m1',a)])],['a','b'])

class RouteRegistryTests(unittest.TestCase):
    def test_routes_from_modules_are_combined_and_duplicates_rejected(self):
        one=SimpleNamespace(RUTAS={('GET',r'/api/x/(\d+)'):lambda app,m,q:int(m[1])})
        routes=load_routes([('x',one)]);handler,match=find_route(routes,'GET','/api/x/7')
        self.assertEqual(handler(None,match,{}),7);self.assertEqual(find_route(routes,'POST','/api/x/7'),(None,None))
        with self.assertRaisesRegex(ValueError,'declarada en x y y'):load_routes([('x',one),('y',one)])

class PageTests(unittest.TestCase):
    def test_index_loads_every_web_module_in_name_order_with_content_versions(self):
        page=render_index();names=re.findall(r'src="/modulos/([^"?]+)\?v=[0-9a-f]{10}"',page)
        self.assertEqual(names,sorted(p.name for p in (ROOT/'web'/'modulos').glob('*.js')));self.assertNotIn('<!--modulos-->',page)
        self.assertRegex(page,r'href="/style\.css\?v=[0-9a-f]{10}"')
    def test_server_serves_page_modules_and_declared_routes_only_inside_web(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir();(root/'plantilla.json').write_bytes((ROOT/'plantilla.json').read_bytes());(root/'data/metadata.json').write_text(json.dumps({'source':'unused','duration':10}))
            extra=[('GET',re.compile(r'/api/demo'),lambda app,m,q:{'ok':q.get('a')})]
            with patch('f8.plataforma.server.load_routes',return_value=extra):http=ThreadingHTTPServer(('127.0.0.1',0),handler_for(App(root)))
            t=threading.Thread(target=http.serve_forever,daemon=True);t.start();url=f'http://127.0.0.1:{http.server_port}'
            try:
                self.assertIn('/modulos/10-app.js',urllib.request.urlopen(url+'/').read().decode('utf8'))
                self.assertEqual(urllib.request.urlopen(url+'/modulos/10-app.js').status,200)
                self.assertEqual(json.load(urllib.request.urlopen(url+'/api/demo?a=1')),{'ok':['1']})
                for bad in ('/modulos/../index.html','/app.js','/f8/plataforma/server.py'):
                    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(url+bad)
                    self.assertEqual(error.exception.code,404,bad)
            finally:http.shutdown();http.server_close();t.join()

if __name__=='__main__':unittest.main()
