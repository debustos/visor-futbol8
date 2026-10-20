"""Transactional review of v3 uncertainties, with immutable automatic bases and undo."""
from pathlib import Path
from collections import defaultdict
import json,sqlite3,threading,hashlib,math,copy
from analytics_v3 import profiles_for,METRICS
from action_quality import metric_counts,action_diagnostics
from presence_engine import presence_lineup
from sequence_engine import sequence_actions,METRIC_MAP,event_id
from pitch_geometry import recover_matrix

class ReviewEngine:
    def __init__(self,app):
        self.app=app;self.root=app.root/'automatic';self.db=app.db_path;self.lock=threading.RLock();self.cache=None;self.cache_key=None
        with self.app.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS automatic_reviews (item_id TEXT PRIMARY KEY, source_key TEXT NOT NULL, payload TEXT NOT NULL, updated TEXT DEFAULT CURRENT_TIMESTAMP)')
            con.execute('CREATE TABLE IF NOT EXISTS automatic_review_proposals (id TEXT PRIMARY KEY, source_key TEXT NOT NULL, payload TEXT NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS automatic_review_history (id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, source_key TEXT NOT NULL, before_json TEXT, after_json TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    def read(self,name,default):
        p=self.root/(name+'.json');result=json.loads(p.read_text(encoding='utf8')) if p.exists() else default
        if name=='uncertainties':
            with self.app.connect() as db:result=result+[json.loads(r[0]) for r in db.execute('SELECT payload FROM automatic_review_proposals WHERE source_key=?',(self.source_key(),))]
        return result
    def source_key(self):return self.read('review-manifest',{}).get('source_key','unavailable')
    def decisions(self):
        with self.app.connect() as con:return {r[0]:json.loads(r[1]) for r in con.execute('SELECT item_id,payload FROM automatic_reviews WHERE source_key=?',(self.source_key(),))}
    def queue(self):
        decisions=self.decisions();items=self.read('uncertainties',[])
        return [{**v,'decision':decisions.get(v['id']),'review_state':decisions.get(v['id'],{}).get('decision','pending')} for v in items]
    def invalidate(self):self.cache_key=None
    def finite(self,value,name):
        if isinstance(value,bool):raise ValueError(name+': número inválido')
        try:n=float(value)
        except (TypeError,ValueError):raise ValueError(name+': número inválido')
        if not math.isfinite(n):raise ValueError(name+': número no finito')
        return n
    def validate(self,item,value):
        if not isinstance(value,dict):raise ValueError('Revisión inválida')
        if value.get('source_key')!=self.source_key():raise ValueError('El análisis cambió: actualiza antes de revisar')
        decision=value.get('decision')
        if decision not in ('confirmed','corrected','rejected'):raise ValueError('Decisión inválida')
        note=value.get('note','')
        if not isinstance(note,str) or len(note)>2000:raise ValueError('Nota inválida')
        v={'decision':decision,'note':note,'category':item['category'],'item_id':item['id']}
        dependents=[d for d in self.decisions().values() if d.get('kind')=='assist' and d.get('goal_id')==item['id'] and d.get('decision')!='rejected']
        if dependents and (decision=='rejected' or value.get('data',{}).get('kind',item.get('kind'))!='goal' or value.get('data',{}).get('player_id',item.get('player_id')) in {d.get('player_id') for d in dependents}):raise ValueError('Deshaz o corrige primero las asistencias vinculadas a este gol')
        if decision=='rejected':
            if item['category']=='identity':v.update(track_id=item['track_id'],context_id=item.get('context_id'),start=item['start'],end=item['end'])
            return v
        players=self.app.players;duration=self.app.metadata()['duration'];data=value.get('data',{})
        if not isinstance(data,dict):raise ValueError('Datos inválidos')
        def player(key,default=None,optional=False):
            pid=data.get(key,default)
            if optional and pid in (None,''):return None
            if pid not in players:raise ValueError('Selecciona un jugador del equipo')
            return pid
        def moment(key,default):
            t=self.finite(data.get(key,default),key)
            if not 0<=t<=duration:raise ValueError('Tiempo fuera del vídeo')
            return round(t,4)
        if item['category']=='identity':
            v.update(player_id=player('player_id',item.get('player_id')),track_id=item['track_id'],context_id=item.get('context_id'),start=moment('start',item['start']),end=moment('end',item['end']))
            if not item['start']<=v['start']<=v['end']<=item['end']:raise ValueError('Corrige solo dentro del segmento seleccionado')
            for other in self.decisions().values():
                if other.get('item_id')!=item['id'] and other.get('category')=='identity' and other.get('decision')!='rejected' and other.get('player_id')==v['player_id'] and other.get('track_id')!=v['track_id'] and min(other['end'],v['end'])-max(other['start'],v['start'])>.01:raise ValueError('Otra corrección sitúa al jugador simultáneamente en dos trayectorias; deshazla antes')
        elif item['category']=='event':
            kind=data.get('kind',item.get('kind'))
            if kind not in METRIC_MAP:raise ValueError('Acción inválida')
            outcome=data.get('outcome',item.get('outcome','unknown'));allowed={'pass':{'complete','incomplete','unknown'},'shot':{'saved','off_target','blocked','unknown'},'goal':{'goal'},'dribble':{'success','failed'}}
            if outcome not in allowed.get(kind,{'unknown'}):raise ValueError('Resultado incompatible')
            if kind=='dribble' and outcome=='failed':raise ValueError('Un regate fallido no suma a regates efectivos; rechaza o corrige la propuesta')
            v.update(player_id=player('player_id',item.get('player_id')),kind=kind,time=moment('time',item['time']),outcome=outcome,receiver_id=player('receiver_id',item.get('receiver_id'),True) if kind=='pass' else None,goal_id=data.get('goal_id') if kind=='assist' else None)
            if v['receiver_id']==v['player_id']:raise ValueError('Un pase no puede tener el mismo emisor y receptor')
            if kind=='pass' and outcome=='complete' and not v['receiver_id']:raise ValueError('Selecciona el receptor del pase completado')
            if kind=='goal' and any(v['time']<d['time'] for d in dependents):raise ValueError('El gol no puede ocurrir antes de la asistencia vinculada')
            if kind=='assist':
                goal=next((e for e in self.effective()['actions'] if e['id']==v['goal_id'] and e['kind']=='goal' and e['state']=='confirmed'),None)
                if not goal or goal['player_id']==v['player_id'] or goal['time']<v['time']:raise ValueError('Vincula la asistencia a un gol confirmado de otro jugador')
                if any(e['kind']=='assist' and e.get('goal_id')==v['goal_id'] and e['state']=='confirmed' and e['id']!=item['id'] for e in self.effective()['actions']):raise ValueError('El gol ya tiene una asistencia confirmada')
            for e in self.effective()['actions']:
                if e['id']!=item['id'] and e['state']=='confirmed' and e.get('player_id')==v['player_id'] and abs(e['time']-v['time'])<.15 and set(METRIC_MAP[e['kind']])&set(METRIC_MAP[kind]):raise ValueError('La acción o una de sus métricas ya está confirmada en ese instante')
        elif item['category']=='lineup':
            ids=data.get('players',[v['player_id'] for v in item.get('players',[])])
            if not isinstance(ids,list) or len(ids)!=8 or len(set(ids))!=8 or any(pid not in players for pid in ids):raise ValueError('La alineación debe contener ocho jugadores distintos')
            v['players']=ids
        elif item['category']=='substitution':
            v.update(out_id=player('out_id',item.get('out_id')),in_id=player('in_id',item.get('in_id')),time=moment('time',item['time']))
            if v['out_id']==v['in_id']:raise ValueError('Entrante y saliente deben ser distintos')
        elif item['category']=='geometry':
            state=data.get('state','accepted')
            if state not in ('accepted','rejected'):raise ValueError('Estado de plano inválido')
            v['state']=state
        else:raise ValueError('Categoría inválida')
        return v
    def propose(self,value):
        if self.source_key()=='unavailable':raise ValueError('Analiza primero esta parte para poder revisar sus incidencias')
        import uuid
        if not isinstance(value,dict) or value.get('source_key')!=self.source_key():raise ValueError('Actualiza el análisis antes de añadir una incidencia')
        category=value.get('category','event')
        if category not in ('event','substitution'):raise ValueError('Solo se añaden jugadas o cambios omitidos')
        t=self.finite(value.get('time'),'Momento');duration=self.app.metadata()['duration']
        if not 0<=t<=duration:raise ValueError('Tiempo fuera del vídeo')
        item={'id':'manual-'+uuid.uuid4().hex,'category':category,'priority':1,'time':round(t,4),'evidence_start':max(0,t-3),'evidence_end':min(duration,t+4),'manual_proposal':True,'state':'candidate','reason':'Incidencia añadida por el usuario; pendiente de confirmar','player_id':None,'kind':'pass' if category=='event' else None,'outcome':'unknown','source_track':None,'out_id':None,'in_id':None}
        with self.app.connect() as db:db.execute('INSERT INTO automatic_review_proposals(id,source_key,payload) VALUES (?,?,?)',(item['id'],self.source_key(),json.dumps(item,ensure_ascii=False)))
        self.invalidate();return item
    def save(self,item_id,value):
        with self.lock:
            item=next((v for v in self.read('uncertainties',[]) if v['id']==item_id),None)
            if item is None:raise ValueError('Incertidumbre inexistente')
            v=self.validate(item,value);key=self.source_key()
            with self.app.connect() as con:
                previous=con.execute('SELECT payload FROM automatic_reviews WHERE item_id=?',(item_id,)).fetchone();before=previous[0] if previous else None;payload=json.dumps(v,ensure_ascii=False)
                con.execute('INSERT INTO automatic_reviews(item_id,source_key,payload) VALUES (?,?,?) ON CONFLICT(item_id) DO UPDATE SET source_key=excluded.source_key,payload=excluded.payload,updated=CURRENT_TIMESTAMP',(item_id,key,payload));con.execute('INSERT INTO automatic_review_history(item_id,source_key,before_json,after_json) VALUES (?,?,?,?)',(item_id,key,before,payload))
            self.invalidate();return v
    def undo(self,item_id):
        with self.lock,self.app.connect() as con:
            row=con.execute('SELECT payload FROM automatic_reviews WHERE item_id=? AND source_key=?',(item_id,self.source_key())).fetchone()
            if not row:raise ValueError('No existe decisión para deshacer')
            dependents=[d for d in self.decisions().values() if d.get('kind')=='assist' and d.get('goal_id')==item_id and d.get('decision')!='rejected']
            if dependents:raise ValueError('Deshaz antes la asistencia vinculada a este gol')
            con.execute('DELETE FROM automatic_reviews WHERE item_id=?',(item_id,));con.execute('INSERT INTO automatic_review_history(item_id,source_key,before_json,after_json) VALUES (?,?,?,NULL)',(item_id,self.source_key(),row[0]))
            self.invalidate();return {'removed':item_id}
    def effective(self):
        with self.lock:
            learner=getattr(self.app,'learning_manager',None);learning_token=learner.token() if learner else None;overlay=learner.overlay(self.app.root) if learner else {}
            key=(learning_token,self.source_key(),(self.root/'quality.json').stat().st_mtime_ns if (self.root/'quality.json').exists() else 0,json.dumps(self.decisions(),sort_keys=True),(self.app.data/'action-reference.json').stat().st_mtime_ns if (self.app.data/'action-reference.json').exists() else 0)
            if key==self.cache_key:return self.cache
            decisions=self.decisions();actions=copy.deepcopy(self.read('actions',[]));
            actions.extend(q for q in self.read('uncertainties',[]) if q.get('manual_proposal') and q['category']=='event')
            for event in actions:event.setdefault('id',event_id(event))
            lineup=copy.deepcopy(self.read('lineup',{}));profiles=copy.deepcopy(self.read('profiles',[]));records=None
            identities=[d for d in decisions.values() if d['category']=='identity'];geometries=[d for d in decisions.values() if d['category']=='geometry']
            if identities or geometries or overlay.get('identities') or overlay.get('actions'):
                records=[]
                for path in sorted((self.root/'chunks').glob('*.json')):records.extend(json.loads(path.read_text(encoding='utf8')))
                queue={q['id']:q for q in self.read('uncertainties',[])}
                for r in records:
                    manual=[]
                    for b in r['tracks']:
                        matches=[d for d in identities if (d['track_id']==b['id'] or (d.get('context_id') and d['context_id']==b.get('person_track_id'))) and (d.get('start',queue[d['item_id']]['start'])<=r['time']<=d.get('end',queue[d['item_id']]['end']))]
                        if matches:
                            d=matches[-1];b['review_context_id']=d.get('context_id');b['player_id']=d.get('player_id') if d['decision']!='rejected' else None;b['identity']={'method':'manual_review','state':'confirmed' if b['player_id'] else 'rejected'}
                            if b['player_id']:manual.append(b)
                    for b in manual:
                        for other in r['tracks']:
                            if other is not b and other.get('player_id')==b['player_id']:other['player_id']=None;other['identity']={'method':'review_conflict','state':'conflict'}
                    for d in geometries:
                        item=queue[d['item_id']]
                        if item['start']<=r['time']<=item['end']:r['geometry']={'state':'reviewed_relative' if d['decision']!='rejected' and d.get('state')=='accepted' else 'rejected','metric_dimensions_known':False}
                if identities and self.read('quality',{}).get('version',0)>=7:
                    from trajectory_identity import stabilize
                    stabilize(records,self.read('identity-segments',[]),self.read('memory-quality',{}).get('cuts',[]),identities)
                if overlay:
                    from review_learning import apply_overlay
                    apply_overlay(records,actions,overlay)
                # Update action actors using their original contact times, not generic nearest identity.
                times=[r['time'] for r in records]
                from bisect import bisect_left
                for e in actions:
                    idx=min(len(records)-1,bisect_left(times,e['time']));near=records[max(0,idx-1):idx+1]
                    match=min(near,key=lambda r:abs(r['time']-e['time'])) if near else None
                    b=next((b for b in match['tracks'] if b['id']==e.get('source_track')),None) if match else None
                    # A derived contact name depends on the adjacent measured bodies.
                    # Rejecting/correcting those references must update this action too.
                    support=e.get('sequence',{}).get('source_contact_identity') or {}
                    if support and identities:
                        observed=[];affected=False
                        for ref in support.get('support',[]):
                            affected=affected or any((d['track_id']==ref['track_id'] or (d.get('context_id') and d['context_id']==ref.get('context_id'))) and d.get('start',-1)<=ref['time']<=d.get('end',-1) for d in identities)
                            k=min(len(records)-1,bisect_left(times,ref['time']));rr=min(records[max(0,k-1):k+1],key=lambda r:abs(r['time']-ref['time']))
                            measured=next((q for q in rr['tracks'] if q['id']==ref['track_id']),None) if abs(rr['time']-ref['time'])<.025 else None
                            observed.append(measured.get('player_id') if measured else None)
                        if affected:e['player_id']=observed[0] if observed and observed[0] and len(set(observed))==1 else None
                    if b and identities:
                        related=[d for d in identities if (d['track_id']==e.get('source_track') or (d.get('context_id') and d['context_id']==e.get('sequence',{}).get('source_context_id'))) and d.get('start',-1)<=e['time']<=d.get('end',-1)]
                        if related:e['player_id']=b.get('player_id')
                    rt=e.get('sequence',{}).get('reception_time')
                    if rt is not None:
                        idx=min(len(records)-1,bisect_left(times,rt));match=min(records[max(0,idx-1):idx+1],key=lambda r:abs(r['time']-rt));b=next((b for b in match['tracks'] if b['id']==e.get('target_track')),None)
                        if b and identities and any(d['track_id']==e.get('target_track') and d.get('start',-1)<=rt<=d.get('end',-1) for d in identities):e['receiver_id']=b.get('player_id')
                    if e['kind']=='pass' and e.get('player_id') and e.get('player_id')==e.get('receiver_id'):
                        e['state']='candidate';e['reason']='La corrección sitúa al mismo jugador como emisor y receptor; hay que resolver la trayectoria.'
                    if not e.get('player_id') and not(e['kind']=='pass' and e.get('outcome')=='complete'):e['state']='candidate'
                lineup=presence_lineup(records)
            for e in actions:
                d=decisions.get(e['id'])
                if d and d['category']=='event':
                    if d['decision']=='rejected':e['state']='rejected'
                    else:e.update({k:v for k,v in d.items() if k not in ('category','item_id','decision')});e['state']='confirmed';e['reviewed']=True
            for item in self.read('uncertainties',[]):
                d=decisions.get(item['id'])
                if not d:continue
                if item['category']=='lineup':
                    if d['decision']=='rejected':lineup['state']='rejected';lineup['identified_candidates']=[];lineup['unidentified_slots']=8
                    else:lineup.update(identified_candidates=[{'player_id':p,'state':'confirmed'} for p in d['players']],state='confirmed',unidentified_slots=0)
                if item['category']=='substitution':
                    lineup['substitutions']=[s for s in lineup.get('substitutions',[]) if s.get('id')!=item['id'] and not(s.get('out_id')==item.get('out_id') and s.get('in_id')==item.get('in_id') and abs(s.get('time',-100)-item['time'])<3)]
                    if d['decision']!='rejected':lineup.setdefault('substitutions',[]).append({**item,**d,'state':'confirmed','id':item['id']})
            actions=[e for e in actions if e['state']!='rejected'];roster=list(self.app.players.values())
            if records:profiles=profiles_for(records,actions,roster,self.app.metadata()['duration'])
            else:
                for p in profiles:
                    own=[e for e in actions if e.get('player_id')==p['id']];p['actions']=own
                    for k,m in p['metrics'].items():
                        est=sum(k in METRIC_MAP[e['kind']] for e in own if e['state']=='estimated');conf=sum(k in METRIC_MAP[e['kind']] for e in own if e['state']=='confirmed');cand=sum(k in METRIC_MAP[e['kind']] for e in own if e['state']=='candidate');m.update(metric_counts(k,est,conf,cand,p.get('samples',0)>0))
            from pass_engine import pass_summary
            reference_path=self.app.data/'action-reference.json'
            reference=json.loads(reference_path.read_text(encoding='utf8')) if reference_path.exists() else None
            diagnostics=action_diagnostics(actions,self.read('quality',{}),reference,self.source_key())
            self.cache={'action_diagnostics':diagnostics,'team_passes':pass_summary(actions),'profiles':profiles,'actions':actions,'lineup':lineup,'records':records,'reviewed_items':len(decisions),'learning_generation':overlay.get('generation'),'source_key':self.source_key()};self.cache_key=key;return self.cache
    def chunk(self,minute):
        records=self.effective()['records']
        return [r for r in records if int(r['time']//60)==minute] if records is not None else self.read('chunks/'+f'{minute:03}',[])
    def export(self):
        effective=self.effective();return {'source_key':self.source_key(),'action_diagnostics':effective['action_diagnostics'],'team_passes':effective['team_passes'],'profiles':effective['profiles'],'actions':effective['actions'],'lineup':effective['lineup'],'decisions':self.decisions(),'scope':'Reviewed actions and partial automatic observations; no certified complete totals.'}
    def evaluation(self):
        items={q['id']:q for q in self.read('uncertainties',[])};counts=defaultdict(lambda:{'reviewed':0,'confirmed':0,'corrected':0,'rejected':0})
        for key,d in self.decisions().items():
            q=items.get(key)
            if not q:continue
            category=q.get('kind') if q['category']=='event' else q['category'];counts[category]['reviewed']+=1;counts[category][d['decision']]+=1
        return {'by_category':dict(counts),'reviewed_items':len(self.decisions()),'scope':'Decisions on reviewed proposals only. No recall or full-match accuracy claim; unreviewed proposals and missed events are unknown.'}
    def history(self):
        with self.app.connect() as db:return [{'id':r[0],'item_id':r[1],'before':json.loads(r[2]) if r[2] else None,'after':json.loads(r[3]) if r[3] else None,'created':r[4]} for r in db.execute('SELECT id,item_id,before_json,after_json,created FROM automatic_review_history WHERE source_key=? ORDER BY id DESC LIMIT 200',(self.source_key(),))]
    def training_export(self):
        items={q['id']:q for q in self.read('uncertainties',[])};decisions=self.decisions()
        return {'source_key':self.source_key(),'labels':[{'proposal':items[k],'review':v} for k,v in decisions.items() if k in items],'scope':'Human-reviewed proposal labels. Unreviewed intervals are not negatives; recall cannot be measured from this export alone.'}
