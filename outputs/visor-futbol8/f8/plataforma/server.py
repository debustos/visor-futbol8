"""Loopback-only football review app; range streaming and transactional SQLite storage."""
from __future__ import annotations
import argparse,csv,io,json,mimetypes,re,secrets,sqlite3,threading,time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from f8.plataforma.season_store import SeasonStore
from f8.plataforma.analysis_jobs import AnalysisJobs
from f8.revision.analytics_review import ReviewEngine
from f8.revision.learning_jobs import LearningJobs
from f8.plataforma.domain import METRICS,EVENTS,DEFINITIONS,aggregate,contributions,validate_assignment,validate_event,number

from f8.plataforma.rutas import load_routes,find_route
from f8.plataforma.paginas import render_index
from f8.core.paths import APP_DIR,WEB_DIR

ROOT=APP_DIR
class App:
    def __init__(self,root=ROOT):
        self.root=Path(root);self.data=self.root/'data';self.db_path=self.root/'revisiones.sqlite3';self.lock=threading.RLock();self.token=secrets.token_urlsafe(24)
        raw=json.loads((self.root/'plantilla.json').read_text(encoding='utf8'))
        self.players={f"orange-{p['jersey_number']}":{**p,'id':f"orange-{p['jersey_number']}"} for p in raw['players']}
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, payload TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
            db.execute('CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, action TEXT NOT NULL, category TEXT NOT NULL, payload TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP)')
        self.review_engine=ReviewEngine(self)
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.db_path,timeout=10)
        try:
            with db:yield db
        finally:db.close()
    def metadata(self):
        result=json.loads((self.data/'metadata.json').read_text(encoding='utf-8-sig'))
        if hasattr(self,'match_context'):result['match_context']=self.match_context
        return result
    def items(self,category):
        with self.connect() as db:
            return [{'id':r[0],**json.loads(r[1]),'created':r[2]} for r in db.execute('SELECT id,payload,created FROM items WHERE category=? ORDER BY id',(category,))]
    def fragments(self):return {r['id']:r for r in json.loads((self.data/'fragments.json').read_text(encoding='utf8'))} if (self.data/'fragments.json').exists() else {}
    def validate_context(self,valid,item_id=None):
        events=self.items('event');others=[e for e in events if e['id']!=item_id]
        metrics={k for k,v in contributions({**valid,'status':'confirmed'}).items() if v}
        for e in others:
            other_metrics={k for k,v in contributions({**e,'status':'confirmed'}).items() if v}
            if e['player_id']==valid['player_id'] and abs(e['time']-valid['time'])<.08 and (e['kind']==valid['kind'] or metrics&other_metrics):raise ValueError('La acción o una de sus etiquetas ya está registrada en ese momento')
        if valid['kind']=='assist' and valid['status']=='confirmed':
            goal=next((e for e in others if e['id']==valid['goal_event_id']),None)
            if not goal or goal['kind']!='shot' or goal['outcome']!='goal' or goal['status']!='confirmed':raise ValueError('Vincula la asistencia a un gol confirmado')
            if goal['player_id']==valid['player_id']:raise ValueError('Un jugador no puede asistirse a sí mismo')
            if valid['time']>goal['time']:raise ValueError('La asistencia no puede ocurrir después del gol')
            if any(e['kind']=='assist' and e['status']=='confirmed' and e.get('goal_event_id')==goal['id'] for e in others):raise ValueError('Este gol ya tiene una asistencia confirmada')
        linked=[e for e in others if e['kind']=='assist' and e['status']=='confirmed' and e.get('goal_event_id')==item_id]
        if linked and (valid['kind']!='shot' or valid['outcome']!='goal' or valid['status']!='confirmed' or any(e['player_id']==valid['player_id'] or e['time']>valid['time'] for e in linked)):raise ValueError('Revisa primero la asistencia vinculada a este gol')
    def add(self,category,value):
        with self.lock:
            if category=='assignment':valid=validate_assignment(value,self.players,self.metadata()['duration'],self.fragments(),self.items(category))
            elif category=='event':
                valid=validate_event(value,self.players,self.metadata()['duration']);self.validate_context(valid)
            elif category=='review':
                start=number(value['start'],'Inicio');end=number(value['end'],'Fin');note=value.get('note','')
                if not 0<=start<end<=self.metadata()['duration'] or not isinstance(note,str) or len(note)>2000:raise ValueError('Revisión inválida')
                valid={'start':start,'end':end,'note':note}
            else:raise ValueError('Categoría desconocida')
            with self.connect() as db:
                payload=json.dumps(valid,ensure_ascii=False)
                cur=db.execute('INSERT INTO items(category,payload) VALUES (?,?)',(category,payload))
                db.execute('INSERT INTO history(action,category,payload) VALUES (?,?,?)',('add',category,payload))
                return {'id':cur.lastrowid,**valid}
    def delete(self,category,item_id):
        with self.lock,self.connect() as db:
            if category=='event' and any(e['kind']=='assist' and e['status']=='confirmed' and e.get('goal_event_id')==item_id for e in self.items('event')):raise ValueError('Retira o deja pendiente la asistencia vinculada antes de retirar el gol')
            row=db.execute('SELECT payload FROM items WHERE category=? AND id=?',(category,item_id)).fetchone()
            if not row:raise ValueError('Registro inexistente')
            db.execute('DELETE FROM items WHERE category=? AND id=?',(category,item_id))
            db.execute('INSERT INTO history(action,category,payload) VALUES (?,?,?)',('remove',category,row[0]))
        return {'removed':item_id}
    def statistics(self):return aggregate(self.items('event'),self.players)
    def update_event(self,item_id,value):
        with self.lock:
            valid=validate_event(value,self.players,self.metadata()['duration'])
            self.validate_context(valid,item_id)
            with self.connect() as db:
                previous=db.execute("SELECT payload FROM items WHERE category='event' AND id=?",(item_id,)).fetchone()
                if not previous:raise ValueError('Acción inexistente')
                payload=json.dumps(valid,ensure_ascii=False)
                db.execute("UPDATE items SET payload=? WHERE category='event' AND id=?",(payload,item_id))
                db.execute('INSERT INTO history(action,category,payload) VALUES (?,?,?)',('update','event',json.dumps({'id':item_id,'before':json.loads(previous[0]),'after':valid},ensure_ascii=False)))
            return {'id':item_id,**valid}
    def export(self):return {'schema_version':1,'part':'primera','match_format':'futbol_8','source':self.metadata(),'players':list(self.players.values()),'assignments':self.items('assignment'),'events':self.items('event'),'reviewed_intervals':self.items('review'),'statistics':self.statistics(),'statistic_scope':'confirmed recorded events, not certified match totals'}

def handler_for(host_app):
    routes=load_routes()
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def handle(self):
            try:super().handle()
            except (ConnectionResetError,ConnectionAbortedError,BrokenPipeError):pass
        def log_message(self,*args):pass
        def respond_headers(self,status,ctype,length,extra=None):
            self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(length));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
            if extra:
                for k,v in extra.items():self.send_header(k,v)
            self.end_headers()
        def json(self,value,status=200):
            raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf8');self.respond_headers(status,'application/json; charset=utf-8',len(raw));self.wfile.write(raw)
        def file(self,path,ctype=None,head=False,download=None):
            if not path.is_file():return self.json({'error':'Archivo no disponible'},404)
            size=path.stat().st_size;start=0;end=size-1;status=200;extra={'Accept-Ranges':'bytes'}
            requested=self.headers.get('Range')
            if requested:
                m=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
                if not m or not any(m.groups()):return self.range_error(size)
                a,b=m.groups()
                if a:start=int(a);end=min(size-1,int(b)) if b else size-1
                else:start=max(0,size-int(b))
                if start>=size or end<start:return self.range_error(size)
                status=206;extra['Content-Range']=f'bytes {start}-{end}/{size}'
            if download:extra['Content-Disposition']=f'attachment; filename="{download}"'
            self.respond_headers(status,ctype or mimetypes.guess_type(path.name)[0] or 'application/octet-stream',end-start+1,extra)
            if not head:
                with path.open('rb') as f:
                    f.seek(start);remaining=end-start+1
                    try:
                        while remaining:
                            data=f.read(min(1024*1024,remaining))
                            if not data:break
                            self.wfile.write(data);remaining-=len(data)
                    except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        def page(self,head=False):
            raw=render_index().encode('utf8');self.respond_headers(200,'text/html; charset=utf-8',len(raw))
            if not head:self.wfile.write(raw)
        def range_error(self,size):
            self.respond_headers(416,'text/plain',0,{'Content-Range':f'bytes */{size}'})
        def scope(self):
            query=parse_qs(urlsplit(self.path).query)
            if 'round' not in query and 'half' not in query:return host_app
            if 'round' not in query or 'half' not in query:raise ValueError('Selecciona jornada y parte')
            if not hasattr(host_app,'season'):raise ValueError('Registro de jornadas no disponible')
            return host_app.season.context(int(query['round'][0]),int(query['half'][0]))
        def queue_learning(self):
            manager=getattr(host_app,'learning_manager',None)
            if manager:
                try:manager.sync()
                except Exception as error:print('No se pudo poner en cola el aprendizaje: '+str(error),flush=True)
        def analysis_jobs(self):
            if not hasattr(host_app,'analysis_jobs'):host_app.analysis_jobs=AnalysisJobs(host_app.season)
            return host_app.analysis_jobs
        def analysis_for(self,app):
            manager=getattr(host_app,'analysis_jobs',None)
            if manager is None:return None
            return next((j for j in reversed(manager.list()) if Path(j['root']).resolve()==app.root.resolve()),None)
        def season_summary(self):
            query=parse_qs(urlsplit(self.path).query)
            round_number=int(query['round'][0]) if 'round' in query else None
            half=int(query['half'][0]) if 'half' in query else None
            if half is not None and (round_number is None or half not in (1,2)):raise ValueError('Selecciona jornada y parte')
            result=host_app.season.summary(round_number,half)
            if query.get('compact')==['1']:
                result={**result,'players':[{k:v for k,v in p.items() if k not in ('heatmap_points','actions')} for p in result['players']]}
            return result
        def do_HEAD(self):self.route(head=True)
        def do_GET(self):self.route()
        def route(self,head=False):
            path=urlsplit(self.path).path
            try:
                if path=='/api/season/analysis/jobs':return self.json(self.analysis_jobs().snapshot())
                if path=='/api/season/registry':return self.json(host_app.season.registry())
                if path in ('/api/season/summary','/api/season/export'):return self.json(self.season_summary())
                if path=='/api/season/stats.csv':
                    summary=self.season_summary();raw=host_app.season.csv(summary)
                    self.respond_headers(200,'text/csv; charset=utf-8',len(raw),{'Content-Disposition':'attachment; filename="estadisticas-jornadas.csv"'})
                    return self.wfile.write(raw)
                app=self.scope() if path.startswith(('/api/','/media')) else host_app
                if path=='/api/bootstrap':return self.json({'token':app.token,'players':list(app.players.values()),'metadata':app.metadata(),'metrics':METRICS,'events':EVENTS,'definitions':DEFINITIONS})
                if path=='/api/automatic/status':
                    job=self.analysis_for(app)
                    if job and job['state'] in ('queued','running','failed'):return self.json({'state':'failed' if job['state']=='failed' else 'processing','stage':job['stage'],'done':job['progress'],'total':100,'job':self.analysis_jobs().public(job)})
                if path=='/api/automatic/export':
                    automatic=app.root/'automatic';names=('metadata','quality','lineup','profiles','actions','gallery','unassigned-events','temporal-metadata','ball-refinement-quality','ball-continuity-quality')
                    bundle={n:json.loads((automatic/(n+'.json')).read_text(encoding='utf8')) for n in names if (automatic/(n+'.json')).exists()}
                    bundle['scope']='Automatic partial observations and candidates. Null is unknown, not zero. No certified full-half totals.'
                    raw=json.dumps(bundle,ensure_ascii=False,indent=2).encode('utf8');self.respond_headers(200,'application/json; charset=utf-8',len(raw),{'Content-Disposition':'attachment; filename="analisis-automatico-primera-parte.json"'});return self.wfile.write(raw)
                if path=='/api/automatic/stats.csv':
                    automatic=app.root/'automatic';target=automatic/'profiles.json';profiles=json.loads(target.read_text(encoding='utf8')) if target.exists() else []
                    stream=io.StringIO();wr=csv.writer(stream);wr.writerow(['dorsal','nombre','segundos_identificados',*[v for k,v in METRICS.items()],*[v+' candidatos' for k,v in METRICS.items()],*[v+' detectados en tramos observados' for v in METRICS.values()],'alcance'])
                    for p in profiles:wr.writerow([p['jersey_number'],p['nickname'],p['visible_seconds'],*[p['metrics'][k]['value'] if p['metrics'][k]['value'] is not None else 'N/D' for k in METRICS],*[p['metrics'][k].get('candidates',0) for k in METRICS],*[p['metrics'][k].get('detected_value') if p['metrics'][k].get('detected_value') is not None else 'N/D' for k in METRICS],'acciones estimadas; cobertura parcial; candidatos no suman; no totales certificados'])
                    raw=('\ufeff'+stream.getvalue()).encode('utf8');self.respond_headers(200,'text/csv; charset=utf-8',len(raw),{'Content-Disposition':'attachment; filename="estadisticas-automaticas-primera-parte.csv"'});return self.wfile.write(raw)
                if re.fullmatch(r'/api/automatic/(status|profiles|quality|lineup|gallery|metadata|actions|unassigned-events|temporal-candidates|ball-status|native-ball-status|native-ball-quality)',path):
                    filename=path.rsplit('/',1)[-1]+'.json';target=app.root/'automatic'/filename
                    if not target.exists():return self.json({'state':'waiting','stage':'pending'} if filename=='status.json' else [] if filename in ('profiles.json','actions.json','gallery.json') else {})
                    return self.file(target,'application/json')
                if re.fullmatch(r'/api/automatic/chunks/\d{3}',path):return self.file(app.root/'automatic'/'chunks'/(path[-3:]+'.json'),'application/json')
                if re.fullmatch(r'/api/automatic/portraits/\d+-(number|pose-[0-9]+)\.jpg',path):return self.file(app.root/'automatic'/'portraits'/path.rsplit('/',1)[-1],'image/jpeg',head)
                if path=='/api/review/learning':
                    manager=getattr(host_app,'learning_manager',None)
                    return self.json(manager.status() if manager else {'state':'idle','generation':0})
                if path=='/api/review/queue':return self.json(app.review_engine.queue())
                if path=='/api/review/status':
                    with app.connect() as db:revision=db.execute('SELECT COALESCE(MAX(id),0) FROM automatic_review_history').fetchone()[0]
                    return self.json({'source_key':app.review_engine.source_key(),'revision':revision,'reviewed':len(app.review_engine.decisions()),'learning_token':getattr(host_app,'learning_manager').token() if hasattr(host_app,'learning_manager') else None})
                if path=='/api/review/action-diagnostics':return self.json(app.review_engine.effective()['action_diagnostics'])
                if path=='/api/review/pass-summary':return self.json({'summary':app.review_engine.effective()['team_passes'],'actions':[e for e in app.review_engine.effective()['actions'] if e['kind']=='pass' and not e.get('player_id')]})
                if path in ('/api/review/profiles','/api/review/actions','/api/review/lineup'):return self.json(app.review_engine.effective()[path.rsplit('/',1)[-1]])
                if path=='/api/review/export':return self.json(app.review_engine.export())
                if path=='/api/review/history':return self.json(app.review_engine.history())
                if path=='/api/review/evaluation':return self.json(app.review_engine.evaluation())
                if path=='/api/review/labels':return self.json(app.review_engine.training_export())
                if re.fullmatch(r'/api/review/chunks/\d{3}',path):return self.json(app.review_engine.chunk(int(path[-3:])))
                if path=='/api/review/stats.csv':
                    stream=io.StringIO();wr=csv.writer(stream);wr.writerow(['dorsal','nombre',*[v+' confirmadas' for v in METRICS.values()],*[v+' estimadas' for v in METRICS.values()],*[v+' candidatas' for v in METRICS.values()],*[v+' detectados en tramos observados' for v in METRICS.values()]])
                    for p in app.review_engine.effective()['profiles']:wr.writerow([p['jersey_number'],p['nickname'],*[p['metrics'][k].get('confirmed_value') if p['metrics'][k].get('confirmed_value') is not None else 'N/D' for k in METRICS],*[p['metrics'][k]['value'] if p['metrics'][k]['value'] is not None else 'N/D' for k in METRICS],*[p['metrics'][k]['candidates'] for k in METRICS],*[p['metrics'][k].get('detected_value') if p['metrics'][k].get('detected_value') is not None else 'N/D' for k in METRICS]])
                    raw=('\ufeff'+stream.getvalue()).encode('utf8');self.respond_headers(200,'text/csv; charset=utf-8',len(raw),{'Content-Disposition':'attachment; filename="estadisticas-con-revision.csv"'});return self.wfile.write(raw)
                if path=='/api/status':return self.file(app.data/'status.json','application/json')
                if path=='/api/fragments':return self.json(list(app.fragments().values()))
                if path=='/api/assignments':return self.json(app.items('assignment'))
                if path=='/api/events':return self.json(app.items('event'))
                if path=='/api/reviews':return self.json(app.items('review'))
                if path=='/api/stats':return self.json(app.statistics())
                if path=='/api/export':
                    raw=json.dumps(app.export(),ensure_ascii=False,indent=2).encode('utf8');self.respond_headers(200,'application/json; charset=utf-8',len(raw),{'Content-Disposition':'attachment; filename="revision-primera-parte.json"'});return self.wfile.write(raw)
                if path=='/api/stats.csv':
                    stream=io.StringIO();wr=csv.writer(stream);wr.writerow(['dorsal','nombre',*METRICS.values(),'acciones_confirmadas','acciones_pendientes','alcance'])
                    for row in app.statistics():
                        p=app.players[row['player_id']];wr.writerow([p['jersey_number'],p['nickname'],*row['metrics'].values(),row['confirmed_events'],row['pending_events'],'acciones registradas; no totales certificados'])
                    raw=('\ufeff'+stream.getvalue()).encode('utf8');self.respond_headers(200,'text/csv; charset=utf-8',len(raw),{'Content-Disposition':'attachment; filename="estadisticas-registradas.csv"'});return self.wfile.write(raw)
                if re.fullmatch(r'/api/chunks/\d{3}',path):return self.file(app.data/'chunks'/(path[-3:]+'.json'),'application/json')
                if path=='/media':
                    compatible=app.root/'media'/'primera-compatible.mp4';return self.file(compatible if compatible.exists() else Path(app.metadata()['source']),'video/mp4',head)
                if path=='/media/original':return self.file(Path(app.metadata()['source']),'video/mp4',head)
                if path in ('/','/index.html'):return self.page(head)
                if re.fullmatch(r'/(style\.css|modulos/[\w.-]+\.(js|css))',path):return self.file(WEB_DIR/path[1:],head=head)
                found,match=find_route(routes,'GET',path)
                if found:return self.json(found(app,match,parse_qs(urlsplit(self.path).query)))
                return self.json({'error':'Ruta desconocida'},404)
            except (ValueError,KeyError,FileNotFoundError) as e:return self.json({'error':str(e)},400)
        def do_POST(self):
            try:app=host_app if urlsplit(self.path).path in ('/api/season/matches','/api/season/analysis') else self.scope()
            except ValueError as e:return self.json({'error':str(e)},400)
            if self.headers.get('X-Review-Token')!=app.token:return self.json({'error':'Sesión de revisión inválida'},403)
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=32768:return self.json({'error':'Solicitud demasiado grande o vacía'},413)
                value=json.loads(self.rfile.read(length));path=urlsplit(self.path).path
                if not isinstance(value,dict):raise ValueError('Solicitud inválida')
                if path=='/api/season/analysis':
                    job=self.analysis_jobs().start(value.get('round'),value.get('half'));return self.json(job,200 if job['state']=='complete' else 202)
                if path=='/api/season/matches':return self.json(host_app.season.register(value),201)
                if path=='/api/review/proposals':return self.json(app.review_engine.propose(value),201)
                m=re.fullmatch(r'/api/review/decisions/([A-Za-z0-9_.-]+)',path)
                if m:
                    saved=app.review_engine.save(m[1],value);self.queue_learning();return self.json(saved,201)
                category={'/api/assignments':'assignment','/api/events':'event','/api/reviews':'review'}.get(path)
                if not category:
                    found,match=find_route(routes,'POST',path)
                    return self.json(found(app,match,value)) if found else self.json({'error':'Ruta desconocida'},404)
                return self.json(app.add(category,value),201)
            except (ValueError,KeyError,TypeError) as e:return self.json({'error':str(e)},400)
        def do_DELETE(self):
            try:app=self.scope()
            except ValueError as e:return self.json({'error':str(e)},400)
            if self.headers.get('X-Review-Token')!=app.token:return self.json({'error':'Sesión de revisión inválida'},403)
            decision_match=re.fullmatch(r'/api/review/decisions/([A-Za-z0-9_.-]+)',urlsplit(self.path).path)
            if decision_match:
                try:
                    saved=app.review_engine.undo(decision_match[1]);self.queue_learning();return self.json(saved)
                except ValueError as e:return self.json({'error':str(e)},400)
            m=re.fullmatch(r'/api/(assignments|events|reviews)/(\d+)',urlsplit(self.path).path)
            if not m:return self.json({'error':'Ruta desconocida'},404)
            category={'assignments':'assignment','events':'event','reviews':'review'}[m[1]]
            try:return self.json(app.delete(category,int(m[2])))
            except ValueError as e:return self.json({'error':str(e)},400)
        def do_PUT(self):
            try:app=self.scope()
            except ValueError as e:return self.json({'error':str(e)},400)
            if self.headers.get('X-Review-Token')!=app.token:return self.json({'error':'Sesión de revisión inválida'},403)
            m=re.fullmatch(r'/api/events/(\d+)',urlsplit(self.path).path)
            if not m:return self.json({'error':'Ruta desconocida'},404)
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=32768:return self.json({'error':'Solicitud demasiado grande o vacía'},413)
                value=json.loads(self.rfile.read(length));return self.json(app.update_event(int(m[1]),value))
            except (ValueError,KeyError,TypeError) as e:return self.json({'error':str(e)},400)
    return Handler

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8768);parser.add_argument('--root',default=str(ROOT));args=parser.parse_args()
    app=App(args.root);app.season=SeasonStore(app);app.analysis_jobs=AnalysisJobs(app.season);app.season.seed_current();app.learning_manager=LearningJobs(app.root);app.learning_manager.start();server=ThreadingHTTPServer(('127.0.0.1',args.port),handler_for(app));server.daemon_threads=True
    print(f'Visor local: http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:app.learning_manager.stop_event.set();server.server_close()
if __name__=='__main__':main()
