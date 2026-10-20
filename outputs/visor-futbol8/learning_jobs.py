"""Durable, debounced review-learning queue. Model publication is revision-atomic."""
from pathlib import Path
from contextlib import contextmanager,closing
import hashlib,json,os,sqlite3,subprocess,sys,threading,time
from automatic_core import write_json
from analysis_jobs import alive


def read(path,default):
    path=Path(path);return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf8')).hexdigest()


def stamp(path):
    path=Path(path)
    if not path.exists():return None
    s=path.stat();return [s.st_size,s.st_mtime_ns]


class LearningJobs:
    def __init__(self,root,work=None,python=None,debounce=15):
        self.root=Path(root).resolve();self.directory=self.root/'aprendizaje';self.directory.mkdir(exist_ok=True)
        self.work=Path(work or Path(__file__).resolve().parents[2]/'work');self.python=str(python or self.work/'vision-env/Scripts/python.exe');self.debounce=debounce
        self.db=self.directory/'jobs.sqlite3';self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None;self.loaded={}
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY CHECK(id=1), desired INTEGER NOT NULL, active INTEGER, fingerprint TEXT)')
            db.execute('INSERT OR IGNORE INTO control VALUES(1,0,NULL,NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS jobs (generation INTEGER PRIMARY KEY,payload TEXT NOT NULL)')
    @contextmanager
    def connect(self):
        con=sqlite3.connect(self.db,timeout=15)
        try:
            with con:yield con
        finally:con.close()
    def snapshot(self):
        parts=[{'analysis_root':'.','round':None,'half':None}];registry=self.root/'temporada.sqlite3'
        if registry.exists():
            with closing(sqlite3.connect(f'file:{registry.as_posix()}?mode=ro',uri=True)) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='parts'").fetchone():
                    parts=[{'round':r,'half':h,'analysis_root':d} for r,h,d in db.execute('SELECT round,half,analysis_root FROM parts ORDER BY round,half')]
        result=[]
        for part in parts:
            root=(self.root/part['analysis_root']).resolve()
            if not root.is_relative_to(self.root):raise ValueError('La jornada está fuera del proyecto')
            manifest=read(root/'automatic/review-manifest.json',{});key=manifest.get('source_key')
            if not key:continue
            reviews=[];reviewdb=root/'revisiones.sqlite3'
            if reviewdb.exists():
                with closing(sqlite3.connect(f'file:{reviewdb.as_posix()}?mode=ro',uri=True)) as db:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='automatic_reviews'").fetchone():reviews=[json.loads(row[0]) for row in db.execute('SELECT payload FROM automatic_reviews WHERE source_key=? ORDER BY item_id',(key,))]
            cache=self.work/'automatic-half' if part['analysis_root']=='.' else self.work/'jornadas'/f"j{part['round']:03d}"/f"parte-{part['half']}"
            result.append({**part,'root':str(root),'cache':str(cache),'source_key':key,'reviews':reviews,'review_hash':digest(reviews),'quality_stamp':stamp(root/'automatic/quality.json'),'feature_stamps':{n:stamp(cache/n) for n in ('feature-rows.json','embeddings.npy','physical-features.npy')},'source_stamp':stamp(read(root/'data/metadata.json',{}).get('source','__missing_video__'))})
        return {'schema':1,'parts':result}
    def control(self):
        with self.connect() as db:return db.execute('SELECT desired,active,fingerprint FROM control WHERE id=1').fetchone()
    def job(self,generation=None):
        if generation is None:generation=self.control()[0]
        with self.connect() as db:r=db.execute('SELECT payload FROM jobs WHERE generation=?',(generation,)).fetchone()
        return json.loads(r[0]) if r else {'state':'idle','generation':0,'progress':0}
    def update(self,generation,**values):
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM jobs WHERE generation=?',(generation,)).fetchone()
            if not row:return None
            job={**json.loads(row[0]),**values,'updated_at':time.time()};db.execute('UPDATE jobs SET payload=? WHERE generation=?',(json.dumps(job,ensure_ascii=False),generation));return job
    def sync(self,force=False):
        snapshot=self.snapshot();fingerprint=digest(snapshot)
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE');generation,active,old=db.execute('SELECT desired,active,fingerprint FROM control WHERE id=1').fetchone()
            if not force and (old==fingerprint or old is None and not any(p['reviews'] for p in snapshot['parts'])):return generation
            generation+=1;folder=self.directory/f'g{generation:06d}';folder.mkdir(exist_ok=True);write_json(folder/'input.json',snapshot)
            job={'generation':generation,'state':'queued','progress':0,'stage':'Agrupando las últimas correcciones','created_at':time.time(),'due_at':time.time()+self.debounce,'fingerprint':fingerprint,'reviews':sum(len(p['reviews']) for p in snapshot['parts']),'worker_pid':None}
            db.execute('INSERT INTO jobs VALUES(?,?)',(generation,json.dumps(job,ensure_ascii=False)));db.execute('UPDATE control SET desired=?,fingerprint=? WHERE id=1',(generation,fingerprint))
            db.execute("UPDATE jobs SET payload=json_set(payload,'$.state','superseded') WHERE generation<>? AND json_extract(payload,'$.state')='queued'",(generation,))
            return generation
    def claim(self,generation):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM jobs WHERE generation=?',(generation,)).fetchone()
            if not row:return False
            job=json.loads(row[0])
            if job['state'] not in ('queued','starting'):return False
            if job.get('worker_pid') and job['worker_pid']!=os.getpid() and alive(job['worker_pid']):return False
            job.update(state='running',worker_pid=os.getpid(),updated_at=time.time());db.execute('UPDATE jobs SET payload=? WHERE generation=?',(json.dumps(job,ensure_ascii=False),generation));return True
    def publish(self,generation,bundle):
        # Snapshot again before the transaction: review changes during training cannot win.
        self.sync()
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE');desired=db.execute('SELECT desired FROM control WHERE id=1').fetchone()[0]
            row=db.execute('SELECT payload FROM jobs WHERE generation=?',(generation,)).fetchone();job=json.loads(row[0])
            if desired!=generation:job.update(state='superseded',stage='Hay correcciones más recientes; se entrenará de nuevo')
            else:
                write_json(self.directory/f'g{generation:06d}'/'bundle.json',bundle)
                db.execute('UPDATE control SET active=? WHERE id=1',(generation,));job.update(state='complete',progress=100,stage='Aprendizaje actualizado',result=bundle['summary'],finished_at=time.time())
            db.execute('UPDATE jobs SET payload=? WHERE generation=?',(json.dumps(job,ensure_ascii=False),generation));return desired==generation
    def tick(self,launch=True):
        self.sync();job=self.job()
        # An older worker finishes its immutable snapshot before the next one starts.
        with self.connect() as db:running=[json.loads(r[0]) for r in db.execute("SELECT payload FROM jobs WHERE json_extract(payload,'$.state') IN ('starting','running')")]
        for previous in running:
            pid=previous.get('worker_pid')
            if pid and alive(pid):return
            if time.time()-previous.get('updated_at',previous['created_at'])<30:return
            self.update(previous['generation'],state='failed',stage='El entrenamiento se interrumpió',error='El proceso de entrenamiento dejó de ejecutarse.')
            if previous['generation']==job['generation']:self.sync(force=True);job=self.job()
        if launch and job['state']=='queued' and time.time()>=job['due_at']:
            generation=job['generation']
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE');current=json.loads(db.execute('SELECT payload FROM jobs WHERE generation=?',(generation,)).fetchone()[0])
                if current['state']!='queued':return
                current.update(state='starting',stage='Preparando entrenamiento',updated_at=time.time());db.execute('UPDATE jobs SET payload=? WHERE generation=?',(json.dumps(current,ensure_ascii=False),generation))
            folder=self.directory/f'g{generation:06d}'
            try:
                with (folder/'worker.log').open('a',encoding='utf8') as log:
                    env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1'}
                    child=subprocess.Popen([self.python,'-B',str(Path(__file__).with_name('review_learning.py')),'--root',str(self.root),'--work',str(self.work),'--generation',str(generation)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self.update(generation,worker_pid=child.pid)
            except Exception as error:self.update(generation,state='failed',stage='No se pudo iniciar el entrenamiento',error=str(error)[:500])
    def start(self):
        if self.thread and self.thread.is_alive():return
        def loop():
            while not self.stop_event.is_set():
                try:self.tick()
                except Exception as error:print('Aprendizaje automático: '+str(error),flush=True)
                self.stop_event.wait(3)
        self.thread=threading.Thread(target=loop,name='review-learning',daemon=True);self.thread.start()
    def status(self):
        job=self.job();return {k:v for k,v in job.items() if k not in ('fingerprint','worker_pid')}
    def token(self):
        desired,active,_=self.control();return (desired,active)
    def overlay(self,root):
        desired,active,_=self.control()
        if not active or desired!=active:return {}
        path=self.directory/f'g{active:06d}'/'bundle.json'
        if active not in self.loaded:self.loaded={active:read(path,{})}
        part=self.loaded[active].get('parts',{}).get(str(Path(root).resolve()),{})
        if part.get('quality_stamp')!=stamp(Path(root)/'automatic/quality.json') or part.get('source_key')!=read(Path(root)/'automatic/review-manifest.json',{}).get('source_key'):return {}
        return {**part,'generation':active} if part else {}
