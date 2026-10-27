"""Persistent, per-video analysis jobs. Commands are selected only from registered videos."""
from pathlib import Path
from datetime import datetime,timezone
import ctypes,hashlib,json,os,sqlite3,subprocess,sys,time,uuid
from f8.core.paths import APP_DIR,PACKAGE_DIR,WORK_DIR

ACTIVE=('queued','running')
def now():return datetime.now(timezone.utc).isoformat()
def alive(pid):
    if not pid:return False
    if os.name!='nt':
        try:os.kill(pid,0);return True
        except OSError:return False
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
    handle=kernel.OpenProcess(0x1000,False,int(pid))
    if not handle:return ctypes.get_last_error()==5
    try:
        code=ctypes.c_ulong();return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
    finally:kernel.CloseHandle(handle)

class AnalysisJobs:
    def __init__(self,store,python_executable=None,worker_script=None):
        self.store=store;self.root=store.root;self.master=APP_DIR
        self.work=WORK_DIR;self.python=Path(python_executable or self.work/'vision-env/Scripts/python.exe')
        self.worker_script=Path(worker_script) if worker_script else None;self.worker=self.worker_script or PACKAGE_DIR/'plataforma'/'analysis_worker.py'
        self.log_root=self.work/'analysis-jobs'/hashlib.sha256(str(self.root.resolve()).encode()).hexdigest()[:12]
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS analysis_jobs (id TEXT PRIMARY KEY, round INTEGER NOT NULL, half INTEGER NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL)')
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_analysis_per_part ON analysis_jobs(round,half) WHERE state IN ('queued','running')")
    def get(self,job_id):
        with self.store.connect() as db:r=db.execute('SELECT payload FROM analysis_jobs WHERE id=?',(job_id,)).fetchone()
        if not r:raise ValueError('Análisis no encontrado')
        return json.loads(r[0])
    def update(self,job_id,**values):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT payload FROM analysis_jobs WHERE id=?',(job_id,)).fetchone()
            if not r:raise ValueError('Análisis no encontrado')
            value=json.loads(r[0]);value.update(values,updated_at=now())
            db.execute('UPDATE analysis_jobs SET state=?,payload=? WHERE id=?',(value['state'],json.dumps(value,ensure_ascii=False),job_id))
        return value
    def list(self,recover=True):
        with self.store.connect() as db:jobs=[json.loads(r[0]) for r in db.execute('SELECT payload FROM analysis_jobs ORDER BY created')]
        if recover:
            for i,j in enumerate(jobs):
                age=time.time()-datetime.fromisoformat(j['created_at']).timestamp()
                if j['state'] in ACTIVE and ((j.get('worker_pid') and age>3 and not alive(j['worker_pid'])) or (not j.get('worker_pid') and age>15)):
                    jobs[i]=self.update(j['id'],state='failed',stage='interrupted',stage_label='Análisis interrumpido',error='El proceso se interrumpió. Puedes volver a intentarlo.',finished_at=now())
        return jobs
    def latest(self,round_number,half):
        return next((j for j in reversed(self.list()) if (j['round'],j['half'])==(round_number,half)),None)
    def public(self,j):
        return {k:v for k,v in j.items() if k not in ('root','cache','source','worker_pid','source_fingerprint')}
    def snapshot(self):return {'jobs':[self.public(j) for j in self.list()]}
    def start(self,round_number,half,launch=True,force=False):
        if isinstance(round_number,bool) or not isinstance(round_number,int) or not 1<=round_number<=9999 or isinstance(half,bool) or not isinstance(half,int) or half not in (1,2):raise ValueError('Jornada y parte inválidas')
        rows=self.store.rows(round_number,half)
        if not rows:raise ValueError('Esta parte todavía no tiene vídeo registrado')
        row=rows[0];target=self.store.directory(row['analysis_root']);source=Path(row['source'])
        previous=self.latest(round_number,half)
        if previous and previous['state'] in ACTIVE:return {**self.public(previous),'started':False}
        status_path=target/'automatic/status.json';status=json.loads(status_path.read_text(encoding='utf-8-sig')) if status_path.exists() else {}
        if not force and status.get('state')=='complete' and (target/'automatic/profiles.json').exists() and not(previous and previous['state']=='failed'):
            return {'round':round_number,'half':half,'state':'complete','progress':100,'stage_label':'Análisis terminado','started':False,'already_complete':True}
        if not source.is_file():raise ValueError('No se encuentra el vídeo original. Comprueba que su unidad esté conectada.')
        if not self.python.is_file() or not self.worker.is_file():raise ValueError('No está disponible el entorno local de análisis')
        base=self.work if self.root.resolve()==self.master else self.log_root/'cache'
        cache=base/'automatic-half' if row['analysis_root']=='.' else base/'jornadas'/f'j{round_number:03d}'/f'parte-{half}'
        stat=source.stat();created=now();job={'id':uuid.uuid4().hex,'round':round_number,'half':half,'state':'queued','stage':'queued','stage_label':'En cola','progress':0,'stage_progress':None,'created_at':created,'updated_at':created,'root':str(target),'cache':str(cache),'source':str(source),'source_fingerprint':{'size':stat.st_size,'mtime_ns':stat.st_mtime_ns},'worker_pid':None,'warning':None,'error':None}
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');other=db.execute("SELECT payload FROM analysis_jobs WHERE round=? AND half=? AND state IN ('queued','running')",(round_number,half)).fetchone()
            if other:return {**self.public(json.loads(other[0])),'started':False}
            db.execute('INSERT INTO analysis_jobs VALUES (?,?,?,?,?,?)',(job['id'],round_number,half,job['state'],json.dumps(job,ensure_ascii=False),created))
        if not launch:return {**self.public(self.get(job['id'])),'started':False,'created':True}
        try:
            self.log_root.mkdir(parents=True,exist_ok=True)
            with (self.log_root/(job['id']+'.log')).open('ab') as log:
                target=[str(self.worker_script)] if self.worker_script else ['-m','f8.plataforma.analysis_worker']
                process=subprocess.Popen([str(self.python),'-u',*target,'--root',str(self.root),'--job',job['id']],cwd=str(APP_DIR),stdout=log,stderr=log,stdin=subprocess.DEVNULL,close_fds=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.update(job['id'],worker_pid=process.pid)
        except OSError as e:
            self.update(job['id'],state='failed',stage_label='No se pudo iniciar',error='No se pudo iniciar el proceso de análisis: '+str(e))
        return {**self.public(self.get(job['id'])),'started':True}
