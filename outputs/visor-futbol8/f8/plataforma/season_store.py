"""Persistent match registry and partial, review-aware season accounting."""
from __future__ import annotations
import copy,csv,hashlib,io,json,math,sqlite3,threading
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from f8.plataforma.domain import METRICS


def read_json(path,default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def aggregate_parts(players,parts,bundles,scope):
    """Sum known counts separately; pool seconds on an attack-normalized relative pitch."""
    from f8.acciones.pass_engine import pass_summary
    team_actions=[];action_checks=[]
    result={p['id']:{**p,'metrics':{k:{'confirmed_value':None,'value':None,'detected_value':None,'detected_parts':0,'candidates':0,'confirmed_parts':0,'estimated_parts':0,'state':'unavailable'} for k in METRICS},'heatmap_points':[],'actions':[],'visible_seconds':0,'mapped_seconds':0,'excluded_direction_seconds':0,'observed_parts':0,'part_coverage':[]} for p in players}
    recorded=sum(p.get('duration',0) for p in parts)
    analyzed=sum(p.get('duration',0) for p in parts if p['state']=='complete')
    for part in parts:
        bundle=bundles.get((part['round'],part['half']),{})
        if bundle.get('action_diagnostics'):action_checks.append({**bundle['action_diagnostics'],'round':part['round'],'half':part['half']})
        team_actions.extend({**e,'round':part['round'],'half':part['half']} for e in bundle.get('actions',[]) if e.get('kind')=='pass')
        for profile in bundle.get('profiles',[]):
            out=result.get(profile['id'])
            if out is None:continue
            visible=profile.get('visible_seconds',0) or 0
            out['visible_seconds']+=visible
            out['observed_parts']+=int(visible>0)
            out['part_coverage'].append({'round':part['round'],'half':part['half'],'visible_seconds':visible,'duration':part['duration'],'state':part['state']})
            for k,m in profile.get('metrics',{}).items():
                if k not in METRICS:continue
                dest=out['metrics'][k]
                for field,counter in [('confirmed_value','confirmed_parts'),('value','estimated_parts'),('detected_value','detected_parts')]:
                    value=m.get(field)
                    if value is not None:
                        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError('Recuento inválido en '+k)
                        dest[field]=(dest[field] if dest[field] is not None else 0)+value
                        dest[counter]+=1
                dest['candidates']+=m.get('candidates',0)
                dest['analysis_state']=m.get('analysis_state',dest.get('analysis_state','candidate_only'))
                dest['state']='partial' if dest['confirmed_value'] is not None or dest['value'] is not None else 'unavailable'
            for point in profile.get('heatmap_points',[]):
                x,y=point['x'],point['y'];weight=point.get('weight_seconds',.2)
                if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (x,y,weight)) or not (0<=x<=100 and 0<=y<=100 and weight>0):continue
                if point.get('calibration_state') in ('rejected','unavailable'):continue
                if part['attack_direction'] not in ('up','down'):
                    out['excluded_direction_seconds']+=weight;continue
                if part['attack_direction']=='down':x,y=100-x,100-y
                out['heatmap_points'].append({**point,'x':x,'y':y,'round':part['round'],'half':part['half'],'weight_seconds':weight})
                out['mapped_seconds']+=weight
            for event in profile.get('actions',[]):
                out['actions'].append({**event,'original_id':event.get('id'),'id':f"j{part['round']}-p{part['half']}-"+str(event.get('id',event.get('time'))),'round':part['round'],'half':part['half']})
    for out in result.values():
        for field in ('visible_seconds','mapped_seconds','excluded_direction_seconds'):out[field]=round(out[field],2)
        out['coverage_percent']=round(100*out['visible_seconds']/recorded,2) if recorded else 0
        out['analyzed_coverage_percent']=round(100*out['visible_seconds']/analyzed,2) if analyzed else 0
        out['mapped_coverage_percent']=round(100*out['mapped_seconds']/recorded,2) if recorded else 0
        out['actions'].sort(key=lambda e:(e['round'],e['half'],e['time']))
        out['mapped_samples']=len(out['heatmap_points'])
    return {'action_diagnostics':action_checks,'team_passes':pass_summary(team_actions),'unattributed_passes':[e for e in team_actions if not e.get('player_id')],'schema_version':4,'scope':scope,'players':list(result.values()),'parts':parts,'recorded_seconds':round(recorded,2),'analyzed_seconds':round(analyzed,2),'registered_parts':len(parts),'analyzed_parts':sum(p['state']=='complete' for p in parts),'expected_parts':2*len({p['round'] for p in parts}),'metrics_scope':'Sumas parciales de acciones confirmadas y estimadas por separado. N/D no es cero. Candidatos no suman.','heatmap_scope':'Segundos de posiciones observadas en plano relativo aproximado; ataque hacia arriba; orientación desconocida excluida.'}


class SeasonStore:
    def __init__(self,host):
        self.host=host;self.root=host.root;self.db=self.root/'temporada.sqlite3';self.lock=threading.RLock();self.apps={str(self.root.resolve()):host};self.cache={}
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS matches (round INTEGER PRIMARY KEY, date TEXT, opponent TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
            db.execute('CREATE TABLE IF NOT EXISTS parts (round INTEGER NOT NULL, half INTEGER NOT NULL, source TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE, analysis_root TEXT NOT NULL UNIQUE, metadata TEXT NOT NULL, direction TEXT NOT NULL DEFAULT "unknown", PRIMARY KEY(round,half), FOREIGN KEY(round) REFERENCES matches(round), CHECK(half IN (1,2)))')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.db,timeout=20);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:yield db
        finally:db.close()
    def directory(self,relative):
        target=(self.root/relative).resolve()
        if not target.is_relative_to(self.root.resolve()):raise ValueError('Carpeta de análisis fuera del visor')
        return target
    def probe(self,source):
        source=Path(source).resolve()
        if source.suffix.lower() not in ('.mp4','.mov','.mkv','.avi') or not source.is_file():raise ValueError('Vídeo local no disponible: '+str(source))
        import cv2
        cap=cv2.VideoCapture(str(source))
        try:
            fps=cap.get(cv2.CAP_PROP_FPS);frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        finally:cap.release()
        if not fps>0 or not frames>0 or not width>0 or not height>0:raise ValueError('No se pudo leer el vídeo: '+str(source))
        digest=hashlib.sha256()
        with source.open('rb') as stream:
            for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
        return str(source),digest.hexdigest(),{'source':str(source),'source_fps':fps,'source_frames':frames,'duration':frames/fps,'width':width,'height':height,'analysis_fps':5,'planned_samples':math.ceil(frames/fps*5),'part':'primera' if 'PRIMERA' in source.name.upper() else 'segunda'}
    def register(self,value,legacy=False):
        if not isinstance(value,dict):raise ValueError('Jornada inválida')
        number=value.get('round')
        if isinstance(number,bool) or not isinstance(number,int) or not 1<=number<=9999:raise ValueError('La jornada debe ser un número entre 1 y 9999')
        matchdate=value.get('date') or None;opponent=value.get('opponent') or None
        if matchdate:date.fromisoformat(matchdate)
        if opponent and (not isinstance(opponent,str) or len(opponent)>100):raise ValueError('Nombre del rival inválido')
        entries=value.get('parts',[])
        if not isinstance(entries,list) or not entries or len(entries)>2:raise ValueError('Añade una o dos partes')
        seen=set();prepared=[]
        for entry in entries:
            half=entry.get('half')
            if isinstance(half,bool) or not isinstance(half,int) or half not in (1,2) or half in seen:raise ValueError('Partes repetidas o inválidas')
            seen.add(half)
            source,fingerprint,meta=self.probe(entry.get('source',''))
            relative='.' if legacy and half==1 else f'jornadas/j{number:03d}/parte-{half}'
            meta['part']='primera' if half==1 else 'segunda'
            direction='up' if legacy and half==1 else 'unknown'
            prepared.append((half,source,fingerprint,relative,meta,direction))
        with self.lock,self.connect() as db:
            for half,source,fingerprint,relative,meta,direction in prepared:
                old=db.execute('SELECT * FROM parts WHERE round=? AND half=?',(number,half)).fetchone()
                duplicate=db.execute('SELECT round,half FROM parts WHERE fingerprint=?',(fingerprint,)).fetchone()
                if duplicate and (duplicate['round'],duplicate['half'])!=(number,half):raise ValueError(f"Este vídeo ya está en jornada {duplicate['round']}, parte {duplicate['half']}")
                if old and old['fingerprint']!=fingerprint:raise ValueError('Esta parte ya tiene otro vídeo. No se sustituye para conservar su análisis y revisiones.')
            db.execute('INSERT OR IGNORE INTO matches(round,date,opponent) VALUES (?,?,?)',(number,matchdate,opponent))
            if matchdate is not None:db.execute('UPDATE matches SET date=? WHERE round=?',(matchdate,number))
            if opponent is not None:db.execute('UPDATE matches SET opponent=? WHERE round=?',(opponent,number))
            for half,source,fingerprint,relative,meta,direction in prepared:
                if db.execute('SELECT 1 FROM parts WHERE round=? AND half=?',(number,half)).fetchone():continue
                target=self.directory(relative)
                if relative!='.':
                    for folder in ('data','automatic','media'): (target/folder).mkdir(parents=True,exist_ok=True)
                    (target/'plantilla.json').write_bytes((self.root/'plantilla.json').read_bytes())
                    (target/'data'/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf8')
                    status={'state':'waiting','stage':'pending','message':'Vídeo recibido; análisis pendiente'}
                    for folder in ('data','automatic'):(target/folder/'status.json').write_text(json.dumps(status),encoding='utf8')
                db.execute('INSERT INTO parts(round,half,source,fingerprint,analysis_root,metadata,direction) VALUES (?,?,?,?,?,?,?)',(number,half,source,fingerprint,relative,json.dumps(meta),direction))
            self.cache.clear()
        return {'registered_round':number,'registry':self.registry()}
    def seed_current(self):
        with self.connect() as db:
            if db.execute('SELECT COUNT(*) FROM matches').fetchone()[0]:return
        meta=read_json(self.root/'data'/'metadata.json',{})
        if not meta.get('source') or not Path(meta['source']).exists():return
        entries=[{'half':1,'source':meta['source']}]
        second=Path(meta['source']).parent/'SEGUNDA PARTE.MP4'
        if second.is_file():entries.append({'half':2,'source':str(second)})
        self.register({'round':2,'parts':entries},legacy=True)
    def rows(self,round_number=None,half=None):
        with self.connect() as db:
            rows=[dict(r) for r in db.execute('SELECT parts.*,matches.date,matches.opponent FROM parts JOIN matches USING(round) ORDER BY round,half')]
        if round_number is not None:rows=[r for r in rows if r['round']==round_number]
        if half is not None:rows=[r for r in rows if r['half']==half]
        return rows
    def context(self,round_number,half):
        rows=self.rows(round_number,half)
        if not rows:raise ValueError('Jornada o parte no registrada')
        row=rows[0];target=self.directory(row['analysis_root']);key=str(target)
        with self.lock:
            if key not in self.apps:self.apps[key]=type(self.host)(target)
            app=self.apps[key]
            if hasattr(self.host,'learning_manager'):app.learning_manager=self.host.learning_manager
            app.match_context={'round':round_number,'half':half,'label':f'Jornada {round_number} · '+('primera parte' if half==1 else 'segunda parte')}
            return app
    def part_info(self,row):
        target=self.directory(row['analysis_root']);meta=read_json(target/'data'/'metadata.json',json.loads(row['metadata']));status=read_json(target/'automatic'/'status.json',{})
        complete=status.get('state')=='complete' and (target/'automatic'/'profiles.json').exists()
        manager=getattr(self.host,'analysis_jobs',None);job=manager.latest(row['round'],row['half']) if manager else None
        if job and job['state'] in ('queued','running','failed'):complete=False
        current_state='complete' if complete else 'processing' if job and job['state']=='running' else job['state'] if job and job['state'] in ('queued','failed') else status.get('state','waiting')
        direction=row['direction'];basis='existing_relative_calibration' if direction!='unknown' else 'unknown'
        if direction=='unknown' and complete:
            keeper=next((p for p in self.context(row['round'],row['half']).review_engine.effective()['profiles'] if p['id']=='orange-1'),{})
            points=keeper.get('heatmap_points',[])
            if sum(p.get('weight_seconds',.2) for p in points)>=20:
                ys=sorted(p['y'] for p in points);median=ys[len(ys)//2]
                if median<30 or median>70:direction='down' if median<30 else 'up';basis='inferred_from_goalkeeper'
        return {'round':row['round'],'half':row['half'],'duration':meta['duration'],'source':row['source'],'state':current_state,'stage':job['stage'] if job else status.get('stage','pending'),'analysis_job':manager.public(job) if job else None,'attack_direction':direction,'direction_basis':basis,'analysis_root':row['analysis_root'],'date':row['date'],'opponent':row['opponent']}
    def summary(self,round_number=None,half=None):
        rows=self.rows(round_number,half)
        if round_number is not None and not rows:raise ValueError('Jornada no registrada')
        key=[]
        manager=getattr(self.host,'analysis_jobs',None);jobs={(j['round'],j['half']):j for j in manager.list()} if manager else {}
        for row in rows:
            target=self.directory(row['analysis_root']);app=self.context(row['round'],row['half'])
            with app.connect() as db:
                revision=db.execute('SELECT COALESCE(MAX(id),0) FROM automatic_review_history').fetchone()[0]
                proposals=db.execute('SELECT COUNT(*) FROM automatic_review_proposals').fetchone()[0]
            job=jobs.get((row['round'],row['half']),{})
            key.append((row['round'],row['half'],row['direction'],revision,proposals,job.get('id'),job.get('state'),*[(target/'automatic'/f).stat().st_mtime_ns if (target/'automatic'/f).exists() else 0 for f in ('quality.json','profiles.json','actions.json','lineup.json','uncertainties.json','status.json','review-manifest.json')]))
        reference_stamps=tuple((Path(r['analysis_root'])/'data/action-reference.json').stat().st_mtime_ns if (Path(r['analysis_root'])/'data/action-reference.json').exists() else 0 for r in rows)
        cachekey=(round_number,half,tuple(key),reference_stamps,self.host.learning_manager.token() if hasattr(self.host,'learning_manager') else None)
        with self.lock:
            if cachekey in self.cache:return self.cache[cachekey]
            parts=[self.part_info(r) for r in rows];bundles={}
            for p in parts:
                if p['state']=='complete':bundles[(p['round'],p['half'])]=self.context(p['round'],p['half']).review_engine.effective()
            scope={'kind':'season' if round_number is None else 'round' if half is None else 'half','round':round_number,'half':half,'label':'Total de temporada' if round_number is None else f'Jornada {round_number}'+(f' · parte {half}' if half else '')}
            result=aggregate_parts(list(self.host.players.values()),parts,bundles,scope)
            if half is not None:result['expected_parts']=1
            if len(self.cache)>12:self.cache.clear()
            self.cache[cachekey]=result
            return result
    def registry(self):
        with self.connect() as db:matches=[dict(r) for r in db.execute('SELECT * FROM matches ORDER BY round')]
        result=[]
        manager=getattr(self.host,'analysis_jobs',None);jobs={(j['round'],j['half']):manager.public(j) for j in manager.list()} if manager else {}
        for match in matches:
            summary=self.summary(match['round']);parts=[{**p,'analysis_job':jobs.get((p['round'],p['half']),p.get('analysis_job'))} for p in summary['parts']]
            result.append({**match,'parts':parts,'analyzed_parts':summary['analyzed_parts'],'registered_parts':len(parts),'expected_parts':2,'recorded_seconds':summary['recorded_seconds'],'analyzed_seconds':summary['analyzed_seconds'],'players_observed':sum(p['visible_seconds']>0 for p in summary['players']),'mapped_seconds':round(sum(p['mapped_seconds'] for p in summary['players']),1),'metrics':{k:{f:sum(p['metrics'][k][f] or 0 for p in summary['players']) if any(p['metrics'][k][f] is not None for p in summary['players']) else None for f in ('confirmed_value','value')} for k in METRICS}})
        return {'schema_version':4,'matches':result,'players':list(self.host.players.values()),'token':self.host.token,'match_format':'futbol_8','parts_per_match':2}
    def csv(self,summary):
        stream=io.StringIO();wr=csv.writer(stream)
        wr.writerow(['alcance','dorsal','nombre','segundos_identificados','segundos_mapa','partes_analizadas','partes_esperadas',*[v+' confirmadas' for v in METRICS.values()],*[v+' estimadas' for v in METRICS.values()],*[v+' candidatas' for v in METRICS.values()],*[v+' detecciones contabilizadas' for v in METRICS.values()]])
        for p in summary['players']:
            wr.writerow([summary['scope']['label'],p['jersey_number'],p['nickname'],p['visible_seconds'],p['mapped_seconds'],summary['analyzed_parts'],summary['expected_parts'],*[p['metrics'][k]['confirmed_value'] if p['metrics'][k]['confirmed_value'] is not None else 'N/D' for k in METRICS],*[p['metrics'][k]['value'] if p['metrics'][k]['value'] is not None else 'N/D' for k in METRICS],*[p['metrics'][k]['candidates'] for k in METRICS],*[p['metrics'][k].get('detected_value') if p['metrics'][k].get('detected_value') is not None else 'N/D' for k in METRICS]])
        return ('\ufeff'+stream.getvalue()).encode('utf8')
