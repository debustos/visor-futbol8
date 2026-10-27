"""Detached, durable analysis worker. One model pipeline runs at a time."""
from pathlib import Path
import argparse,json,os,queue,subprocess,sys,threading,time
from f8.plataforma.analysis_jobs import AnalysisJobs,now
from f8.plataforma.pipeline import pipeline_steps
from f8.core.paths import APP_DIR

STEPS=[('prepare','Preparando el campo','prepare_video.py',[],3),('detection','Detectando jugadores','analyze_automatic.py',['--scan-only'],25),('temporal','Buscando jugadas','temporal_actions.py',[],8),('jersey','Leyendo dorsales','analyze_automatic.py',['--resume'],10),('ball','Siguiendo el balón','refine_ball.py',[],12),('fusion','Relacionando jugadores y acciones','analyze_automatic.py',['--resume','--reuse-ocr'],1),('appearance','Aprendiendo la apariencia','extract_appearance_parts.py',[],4),('memory','Construyendo memoria visual','upgrade_v3.py',[],1),('dense_ball','Revisando contactos y pases','adaptive_ball.py',[],19),('ball_continuity','Comprobando la trayectoria del balón','ball_continuity.py',[],2),('jersey_text','Comprobando dorsales completos','read_jersey_text.py',[],8),('identities','Reconstruyendo identidades','repair_identity_v5.py',[],2),('context','Fijando identidades por trayectoria','commit_v5.py',[],1),('dorsal_guard_seed','Validando dorsales antes de aprender apariencia','dorsal_guard.py',[],2),('references','Ampliando referencias a distintas distancias','reference_bank.py',[],5),('far_identity','Reconociendo jugadores lejanos con contexto','far_identity.py',[],3),('native_ball','Revisando vuelos del balón a velocidad original','native_ball.py',['--no-pose'],24),('dorsal_guard_final','Comprobando identidades después del seguimiento','dorsal_guard.py',[],2),('visual_shots','Buscando vuelos hacia las porterías','visual_shots.py',[],3),('commit','Generando estadísticas','commit_v5.py',[],1),('gallery','Preparando fichas','make_gallery.py',[],1),('maps','Dibujando mapas de calor','export_heatmaps.py',[],1),('validation','Comprobando los resultados','validate_v5.py',[],1),('playback','Preparando el vídeo del visor','make_playback.py',[],3)]

def fraction(message,duration):
    pairs=[('done','total'),('done_seconds','total_seconds')]
    for a,b in pairs:
        if isinstance(message.get(a),(int,float)) and isinstance(message.get(b),(int,float)) and message[b]>0:return max(0,min(1,message[a]/message[b]))
    if message.get('stage')=='temporal' and isinstance(message.get('seconds'),(int,float)) and duration>0:return max(0,min(1,message['seconds']/duration))
    return None

class Pipeline:
    def __init__(self,manager,steps=None,script_root=None):self.manager=manager;self.steps=steps or STEPS;self.script_root=Path(script_root or Path(__file__).resolve().parent)
    def execute(self,job):
        manager=self.manager;source_stat=Path(job['source']).stat()
        if job.get('source_fingerprint')!={'size':source_stat.st_size,'mtime_ns':source_stat.st_mtime_ns}:raise RuntimeError('El vídeo cambió después de iniciar el análisis. Vuelve a registrarlo antes de continuar.')
        root=Path(job['root']);cache=Path(job['cache']);cache.mkdir(parents=True,exist_ok=True);(root/'automatic').mkdir(exist_ok=True)
        metadata=json.loads((root/'data/metadata.json').read_text(encoding='utf-8-sig'));metadata['match_context']={'round':job['round'],'half':job['half']};meta_path=root/'data/metadata.json';temp=meta_path.with_suffix('.json.tmp');temp.write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf8');temp.replace(meta_path);duration=metadata['duration']
        env={**os.environ,'FOOTBALL_VIEWER_ROOT':str(root),'FOOTBALL_MASTER_ROOT':str(manager.root),'FOOTBALL_CACHE_ROOT':str(cache),'FOOTBALL_VIDEO_SOURCE':job['source'],'PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1','PYTHONPATH':os.pathsep.join(filter(None,[str(APP_DIR),os.environ.get('PYTHONPATH')])),'TEMP':str(cache),'TMP':str(cache)}
        offset=0;total_weight=sum(s[4] for s in self.steps)
        for stage,label,script,args,weight in self.steps:
            manager.update(job['id'],stage=stage,stage_label=label,progress=round(min(99,offset/total_weight*100),1),stage_progress=0)
            if stage=='playback' and (root/'media/primera-compatible.mp4').exists():offset+=weight;continue
            log_queue=queue.Queue();last_fraction=0;tail=[];last_update=0
            with subprocess.Popen([str(manager.python),'-u',*([str(self.script_root/script)] if script.endswith('.py') else ['-m',script]),*args],cwd=str(APP_DIR),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace',env=env,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as process:
                def read_output():
                    for line in process.stdout:log_queue.put(line)
                    log_queue.put(None)
                thread=threading.Thread(target=read_output,daemon=True);thread.start();ended=False
                while not ended:
                    try:line=log_queue.get(timeout=1)
                    except queue.Empty:line=''
                    if line is None:ended=True
                    elif line:
                        print(line.rstrip(),flush=True);tail.append(line.strip());tail=tail[-12:]
                        try:message=json.loads(line)
                        except (ValueError,TypeError):message={}
                        if isinstance(message,dict):
                            f=fraction(message,duration)
                            if f is not None:last_fraction=max(last_fraction,f)
                            if message.get('warning'):manager.update(job['id'],warning=message['warning'])
                    if time.monotonic()-last_update>=1 or ended:
                        manager.update(job['id'],progress=round(min(99,(offset+weight*last_fraction)/total_weight*100),1),stage_progress=round(last_fraction*100,1),worker_pid=os.getpid());last_update=time.monotonic()
                if process.wait()!=0:raise RuntimeError(label+': '+(tail[-1] if tail else 'El proceso terminó con error'))
            offset+=weight
        if not(root/'automatic/profiles.json').exists():raise RuntimeError('El análisis terminó sin generar fichas')
        manager.update(job['id'],state='complete',stage='done',stage_label='Análisis terminado',progress=100,stage_progress=100,finished_at=now(),error=None)

def run(manager,job_id,omit=()):
    manager.update(job_id,worker_pid=os.getpid());lock_path=manager.work/'football-analysis.lock';lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open('a+b') as lock:
        if lock_path.stat().st_size==0:lock.write(b'0');lock.flush()
        acquired=False
        try:
            while not acquired:
                lock.seek(0)
                try:
                    if os.name=='nt':
                        import msvcrt;msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl;fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    acquired=True
                except (OSError,BlockingIOError):time.sleep(1);continue
                queued=[j for j in manager.list() if j['state']=='queued']
                if queued and queued[0]['id']!=job_id:
                    if os.name=='nt':msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
                    else:fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
                    acquired=False;time.sleep(1)
            job=manager.get(job_id)
            if job['state']!='queued':return
            job=manager.update(job_id,state='running',started_at=now(),stage_label='Iniciando análisis')
            Pipeline(manager,[s for s in STEPS if s[0] not in omit]).execute(job)
        except Exception as e:manager.update(job_id,state='failed',stage_label='Análisis interrumpido',error=str(e)[:600],finished_at=now());print(str(e),flush=True)
        finally:
            if acquired:
                lock.seek(0)
                if os.name=='nt':msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(lock.fileno(),fcntl.LOCK_UN)

def main():
    parser=argparse.ArgumentParser(description='Run a queued job (--job), or analyse a registered part in the foreground (--round/--half).');parser.add_argument('--root',required=True);parser.add_argument('--job');parser.add_argument('--round',type=int);parser.add_argument('--half',type=int);parser.add_argument('--omit',default='',help='Comma-separated stage keys to skip, e.g. detection,jersey');args=parser.parse_args()
    from f8.plataforma.server import App
    from f8.plataforma.season_store import SeasonStore
    manager=AnalysisJobs(SeasonStore(App(args.root)),python_executable=sys.executable)
    if args.job:return run(manager,args.job)
    if args.round is None or args.half is None:parser.error('Indica --job, o --round y --half')
    omit={s for s in args.omit.split(',') if s};unknown=omit-{s[0] for s in STEPS}
    if unknown:parser.error('Etapas desconocidas: '+', '.join(sorted(unknown)))
    try:job=manager.start(args.round,args.half,launch=False,force=True)
    except ValueError as e:sys.exit(str(e))
    if not job.get('created'):sys.exit('Ya hay un análisis activo para esta parte')
    run(manager,job['id'],omit);job=manager.get(job['id'])
    if job['state']!='complete':sys.exit(job.get('error') or 'El análisis no terminó')
    print(f'Jornada {args.round}, parte {args.half} actualizada.',flush=True)
if __name__=='__main__':main()
