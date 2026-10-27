"""Train appearance and action-proposal classifiers from persisted review snapshots.

Predicted names never become labels. Folds contain disjoint physical trajectories.
A rejected identity is an exclusion, not a guessed replacement identity.
"""
from contextlib import closing
import argparse,copy,json,os,time
from pathlib import Path
from collections import defaultdict,Counter
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from threadpoolctl import threadpool_limits
from f8.core.io import write_json
from f8.identidad.reference_bank import build_inputs,feature_matrix,acceptable_box,calibrate_thresholds
from f8.identidad.far_identity import feature_scale
from f8.revision.learning_jobs import LearningJobs,read,digest
from f8.core.paths import APP_DIR


def matches(review,r,b):
    return (str(review.get('track_id'))==str(b['id']) or review.get('context_id') and review['context_id']==b.get('person_track_id')) and review.get('start',-1)<=r['time']<=review.get('end',-1)


def encode_model(model,scale=None):
    return {'coef':model.coef_.tolist(),'intercept':model.intercept_.tolist(),'classes':model.classes_.tolist(),'scale':None if scale is None else scale.tolist()}


def probabilities(model,x):
    x=np.asarray(x,float);scale=model.get('scale');z=(x*(np.array(scale) if scale is not None else 1))@np.array(model['coef']).T+model['intercept']
    if z.shape[1]==1:
        p=1/(1+np.exp(-np.clip(z[:,0],-40,40)));return np.column_stack([1-p,p])
    z-=z.max(axis=1,keepdims=True);p=np.exp(z);return p/p.sum(axis=1,keepdims=True)


def align(model,x,classes):
    result=np.zeros((len(x),len(classes)));p=model.predict_proba(x)
    for i,c in enumerate(model.classes_):result[:,np.flatnonzero(classes==c)[0]]=p[:,i]
    return result


def train_identity(x,y,groups,heights,baseline_labels):
    counts={int(c):len(set(groups[y==c])) for c in set(y)};classes=np.array(sorted(c for c,n in counts.items() if c!=1 and n>=3),int)
    report={'training_samples':len(y),'independent_contexts':len(set(groups)),'contexts_per_player':counts,'active':False,'scope':'Validación por trayectorias con etiquetas de dorsal y revisión; no mide la precisión total del partido.'}
    if len(classes)<2:return None,{}, {**report,'reason':'Faltan al menos tres trayectorias independientes de dos jugadores.'}
    keep=np.isin(y,classes);x=x[keep];y=y[keep];groups=groups[keep];heights=heights[keep];baseline_labels=baseline_labels[keep];scale=feature_scale('physical');xx=x*scale
    folds=list(StratifiedGroupKFold(n_splits=3,shuffle=True,random_state=20261007).split(xx,y,groups));pred=np.zeros((len(y),len(classes)));base=np.zeros_like(pred);fold_report=[]
    with threadpool_limits(limits=3):
        for tr,te in folds:
            assert not set(groups[tr])&set(groups[te])
            model=LogisticRegression(C=2,max_iter=600,class_weight='balanced').fit(xx[tr],y[tr]);pred[te]=align(model,xx[te],classes)
            old=tr[np.isin(baseline_labels[tr],classes)]
            if len(set(baseline_labels[old]))>=2:
                control=LogisticRegression(C=2,max_iter=600,class_weight='balanced').fit(xx[old],baseline_labels[old]);base[te]=align(control,xx[te],classes)
            fold_report.append({'training_contexts':len(set(groups[tr])),'validation_contexts':len(set(groups[te])),'context_leakage':False})
        model=LogisticRegression(C=2,max_iter=600,class_weight='balanced').fit(xx,y)
    def accuracy(p):
        correct=classes[p.argmax(axis=1)]==y
        return float(np.mean([np.mean(correct[groups==g]) for g in set(groups)]))
    score=accuracy(pred);control=accuracy(base);thresholds,checks=calibrate_thresholds(pred,y,groups,heights,classes)
    active=score>=control and any(v<=1 for v in thresholds.values())
    report.update(active=bool(active),context_balanced_validation_accuracy=round(score,4),reference_control_accuracy=round(control,4),classes=classes.tolist(),folds=fold_report,class_checks=checks,reason='Modelo validado para las clases con apoyo suficiente.' if active else 'El candidato no supera el control o faltan ejemplos fiables por jugador.')
    return encode_model(model,scale),thresholds,report


def part_inputs(part):
    root=Path(part['root']);cache=Path(part['cache']);key=part['source_key'];reviews=part['reviews'];identity_reviews=[d for d in reviews if d['category']=='identity']
    events=read(root/'automatic/actions.json',[]);queue=read(root/'automatic/uncertainties.json',[])
    with_db=root/'revisiones.sqlite3'
    if with_db.exists():
        import sqlite3
        with closing(sqlite3.connect(f'file:{with_db.as_posix()}?mode=ro',uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='automatic_review_proposals'").fetchone():queue += [json.loads(r[0]) for r in db.execute('SELECT payload FROM automatic_review_proposals WHERE source_key=?',(key,))]
    result={'part':part,'events':events,'queue':queue,'reviews':reviews,'x':np.zeros((0,872)),'y':np.array([],int),'groups':np.array([],str),'heights':np.array([]),'baseline':np.array([],int),'targets':[],'manual_samples':0}
    if not all((cache/n).exists() for n in ('feature-rows.json','embeddings.npy','physical-features.npy')):
        result['reason']='Faltan características visuales de esta parte.';return result
    records=[r for f in sorted((root/'automatic/chunks').glob('*.json')) for r in read(f,[])];contexts=read(root/'automatic/identity-contexts.json',[]);segments=read(root/'automatic/identity-segments.json',[]);evidence=read(root/'automatic/jersey-evidence-v5.json',[])
    rows=read(cache/'feature-rows.json',[]);emb=np.load(cache/'embeddings.npy');physical=np.load(cache/'physical-features.npy');features=feature_matrix(emb,physical)
    if len(rows)!=len(features):raise ValueError('Las características no corresponden a los fotogramas guardados.')
    _,base_pool,frames,_=build_inputs(records,rows,emb,segments,evidence,contexts);baseline={c['feature_index']:c['number'] for c in base_pool}
    ctx={c['id']:c for c in contexts};all_contexts=defaultdict(list);manual_contexts=set();targets=defaultdict(list);observations=defaultdict(list);blocked=set()
    for r in records:
        for b in r['tracks']:
            cid=b.get('person_track_id')
            if not cid:continue
            all_contexts[cid].append((r,b));observations[cid].append([r['frame'],str(b['id'])])
            if b.get('player_id') or b.get('kit')!='orange' or b.get('identity',{}).get('state') in ('conflict','rejected') or b.get('identity',{}).get('reason')=='competing_trajectory':blocked.add(cid)
            if any(matches(d,r,b) for d in identity_reviews):manual_contexts.add(cid);blocked.add(cid)
    for cid in manual_contexts:
        for r,b in all_contexts[cid]:
            relevant=[d for d in identity_reviews if matches(d,r,b)]
            b['player_id']=None
            if relevant:
                d=relevant[-1]
                if d['decision']!='rejected':b['player_id']=d.get('player_id')
                b['identity']={'method':'manual_review','state':'accepted' if b['player_id'] else 'rejected'}
        if cid in ctx:ctx[cid]={**ctx[cid],'anchor_method':'manual_review'}
    _,pool,frames,_=build_inputs(records,rows,emb,segments,evidence,list(ctx.values()))
    # Conflicting labels in one physical group are excluded from both training and validation.
    labels=defaultdict(set)
    for c in pool:labels[c['context_id']].add(c['number'])
    pool=[c for c in pool if len(labels[c['context_id']])==1]
    indices=np.array([c['feature_index'] for c in pool],int)
    result.update(x=features[indices],y=np.array([c['number'] for c in pool],int),groups=np.array([key+':'+c['context_id'] for c in pool]),heights=np.array([c['height'] for c in pool]),baseline=np.array([baseline.get(c['feature_index'],-1) for c in pool]),manual_samples=sum(c['context_id'] in manual_contexts for c in pool),excluded_conflicting_contexts=sum(len(v)>1 for v in labels.values()))
    for row in rows:
        r=frames.get(row['frame']);b=next((b for b in r['tracks'] if str(b['id'])==str(row['track_id'])),None) if r else None
        if not b:continue
        cid=b.get('person_track_id')
        if not cid or cid in blocked or not acceptable_box(b,r['tracks']):continue
        targets[cid].append((row['index'],r['time'],b['box'][3]-b['box'][1]))
    result['targets']=[{'context_id':cid,'x':features[[v[0] for v in values]],'times':np.array([v[1] for v in values]),'heights':np.array([v[2] for v in values]),'observations':observations[cid]} for cid,values in targets.items() if len(values)>=8]
    return result


def identity_predictions(data,model,thresholds):
    if model is None:return []
    result=[];classes=np.array(model['classes'])
    for target in data['targets']:
        times=target['times'];height=target['heights'];p=probabilities(model,target['x']);order=np.argsort(-p.mean(axis=0));column=order[0];number=int(classes[column]);score=float(np.median(p[:,column]));agreement=float(np.mean(p.argmax(axis=1)==column));margin=float(p[:,column].mean()-p[:,order[1]].mean())
        far=np.any(height<80);threshold=max(.80,thresholds.get(f'{number}:all',1.1),thresholds.get(f'{number}:far',1.1) if far else 0)
        if len(times)<8 or times.max()-times.min()<6 or max(np.diff(np.sort(times)))>2.1 or score<threshold or agreement<.85 or margin<.20:continue
        result.append({'context_id':target['context_id'],'player_id':f'orange-{number}','score':round(score,4),'threshold':threshold,'samples':len(times),'start':float(times.min()),'end':float(times.max()),'observations':target['observations'],'method':'review_trained_appearance'})
    return result


def action_features(e):
    seq=e.get('sequence') or {};release=e.get('actor_evidence') or {};visual=e.get('visual_evidence') or {};temporal=e.get('temporal_evidence') or []
    def n(value,limit=100):
        try:v=float(value)
        except (TypeError,ValueError):return 0
        return float(np.clip(v,0,limit))/limit if np.isfinite(v) else 0
    return [n(e.get('score'),1),n(seq.get('contact_confidence'),1),float(bool(seq.get('travel_verified'))),float(bool(seq.get('image_travel_verified'))),n(seq.get('free_flight_samples'),30),n(seq.get('measured_path_samples'),40),n(seq.get('largest_sample_gap'),5),float(bool(seq.get('blocking_contact'))),float(release.get('state')=='measured_release'),n(release.get('release_samples'),30),n(release.get('screen_travel_pixels'),600),n(visual.get('path_samples'),30),n(visual.get('neural_samples'),30),n(max([t.get('score',0) for t in temporal]+[0]),1),float(e.get('team')=='orange'),float(e.get('outcome')=='complete')]


def action_labels(data):
    items={q['id']:q for q in data['queue'] if q.get('category')=='event'};items.update({q['id']:q for q in data['events']});labels=[]
    reviews=sorted([d for d in data['reviews'] if d['category']=='event' and d['item_id'] in items],key=lambda d:items[d['item_id']]['time']);end=-1;group=0
    for d in reviews:
        original=items[d['item_id']];start=original.get('evidence_start',original['time']-3)
        if start>end:group+=1
        end=max(end,original.get('evidence_end',original['time']+3));kind=original['kind'];accepted=d['decision']!='rejected' and d.get('kind',kind)==kind
        if kind=='pass' and d.get('outcome',original.get('outcome'))!=original.get('outcome'):accepted=False
        labels.append({'kind':kind,'label':int(accepted),'x':action_features(original),'group':data['part']['source_key']+f':action-{group}','item_id':d['item_id']})
        # A corrected type is kept in the exported labels, not synthesized as a detector hit.
    return labels


def train_actions(labels):
    models={};reports={}
    for kind in sorted({l['kind'] for l in labels}):
        rows=[l for l in labels if l['kind']==kind];x=np.array([l['x'] for l in rows]);y=np.array([l['label'] for l in rows]);groups=np.array([l['group'] for l in rows]);counts=Counter(y);group_counts={c:len(set(groups[y==c])) for c in (0,1)}
        report={'active':False,'reviewed_examples':len(y),'positive_examples':counts[1],'negative_examples':counts[0],'independent_groups':group_counts,'reason':'Se necesitan al menos 10 ejemplos aceptados y 10 rechazados, en 3 secuencias independientes de cada tipo.'};reports[kind]=report
        if min(counts[0],counts[1])<10 or min(group_counts.values())<3:continue
        pred=np.zeros(len(y))
        with threadpool_limits(limits=3):
            for tr,te in StratifiedGroupKFold(3,shuffle=True,random_state=20261007).split(x,y,groups):
                if len(set(y[tr]))<2:continue
                model=LogisticRegression(C=1,max_iter=500,class_weight='balanced').fit(x[tr],y[tr]);pred[te]=model.predict_proba(x[te])[:,1]
            threshold=None
            for t in (.8,.85,.9,.95):
                mask=pred>=t
                if mask.sum()>=5 and len(set(groups[mask]))>=3 and np.mean(y[mask])>=.95:threshold=t;break
            if threshold is None:report['reason']='La validación todavía no alcanza suficiente precisión.';continue
            model=LogisticRegression(C=1,max_iter=500,class_weight='balanced').fit(x,y)
        models[kind]={**encode_model(model),'threshold':threshold};report.update(active=True,threshold=threshold,validation_precision=round(float(np.mean(y[pred>=threshold])),4),reason='Clasificador de propuestas validado en secuencias separadas.')
    return models,reports


def apply_overlay(records,actions,overlay):
    """Enrich unknown physical contexts only, after applying human corrections."""
    wanted={(frame,tid):p for p in overlay.get('identities',[]) for frame,tid in p['observations']};contexts=defaultdict(list);occupied=defaultdict(set);proposals=defaultdict(list);learned=0
    for r in records:
        for b in r['tracks']:
            cid=b.get('person_track_id')
            if cid:contexts[cid].append((r,b))
            if b.get('player_id'):occupied[b['player_id']].add(r['frame'])
            p=wanted.get((r['frame'],str(b['id'])))
            if p and cid:proposals[cid].append(p)
    for cid,pp in sorted(proposals.items(),key=lambda pair:-max(p['score'] for p in pair[1])):
        rows=contexts[cid];ids={p['player_id'] for p in pp}
        if len(ids)!=1 or any(b.get('player_id') or b.get('kit')!='orange' or b.get('identity',{}).get('state') in ('rejected','conflict') or b.get('identity',{}).get('method') in ('manual_review','review_conflict') for r,b in rows):continue
        pid=next(iter(ids));frames={r['frame'] for r,b in rows}
        if frames&occupied[pid]:continue
        for r,b in rows:b['player_id']=pid;b['identity']={'method':'review_trained_appearance','state':'estimated','locked':True,'context_id':cid,'generation':overlay.get('generation'),'score':max(p['score'] for p in pp)}
        occupied[pid].update(frames);learned+=1
    from bisect import bisect_left
    times=[r['time'] for r in records]
    for event in actions:
        for field,track,t in [('player_id',event.get('source_track'),event['time']),('receiver_id',event.get('target_track'),event.get('sequence',{}).get('reception_time'))]:
            if event.get(field) or t is None or not records:continue
            k=bisect_left(times,t);near=records[max(0,k-1):min(len(records),k+1)]
            r=min(near,key=lambda r:abs(r['time']-t)) if near else None
            b=next((b for b in r['tracks'] if b['id']==track and b.get('identity',{}).get('method')=='review_trained_appearance'),None) if r and abs(r['time']-t)<.08 else None
            if b:event[field]=b['player_id'];event['learned_identity_generation']=overlay.get('generation')
    for e in actions:
        decision=overlay.get('actions',{}).get(e.get('id'))
        if decision and e.get('state')=='candidate' and e.get('player_id') and e.get('team')=='orange' and e.get('player_id')!=e.get('receiver_id'):
            e.update(state='estimated',learned_action_generation=overlay.get('generation'),learned_score=decision['score'],reason='Estimación aprendida de jugadas revisadas; recuento parcial.')
    return learned


def train(manager,generation):
    folder=manager.directory/f'g{generation:06d}';snapshot=read(folder/'input.json',{});manager.update(generation,state='running',worker_pid=os.getpid(),stage='Preparando ejemplos corregidos',progress=5);datasets=[]
    for i,part in enumerate(snapshot['parts']):
        datasets.append(part_inputs(part));manager.update(generation,stage='Preparando referencias visuales',progress=10+25*(i+1)/max(1,len(snapshot['parts'])))
    usable=[d for d in datasets if len(d['y'])];model=None;thresholds={};quality={'active':False,'reason':'Todavía no hay suficientes ejemplos visuales utilizables.'}
    manager.update(generation,stage='Entrenando y validando por trayectorias',progress=40)
    if usable:model,thresholds,quality=train_identity(*[np.concatenate([d[name] for d in usable]) for name in ('x','y','groups','heights','baseline')])
    labels=[label for d in datasets for label in action_labels(d)];manager.update(generation,stage='Aprendiendo de las jugadas revisadas',progress=75);action_models,action_quality=train_actions(labels)
    write_json(folder/'identity-model.json',{'model':model,'thresholds':thresholds,'quality':quality});write_json(folder/'action-models.json',{'models':action_models,'quality':action_quality});write_json(folder/'reviewed-labels.json',{'parts':[{'source_key':p['source_key'],'reviews':p['reviews']} for p in snapshot['parts']],'action_examples':labels})
    parts={};predicted=0
    for d in datasets:
        identities=identity_predictions(d,model,thresholds) if quality['active'] else [];predicted+=len(identities);event_predictions={}
        for e in d['events']:
            m=action_models.get(e['kind'])
            if m is None or e.get('state')!='candidate' or any(v['item_id']==e['id'] for v in d['reviews']):continue
            score=float(probabilities(m,[action_features(e)])[0,1])
            if score>=m['threshold']:event_predictions[e['id']]={'score':round(score,4)}
        p=d['part'];parts[p['root']]={'source_key':p['source_key'],'quality_stamp':p['quality_stamp'],'review_hash':p['review_hash'],'identities':identities,'actions':event_predictions}
    categories=Counter(d['category'] for p in snapshot['parts'] for d in p['reviews']);summary={'identity_model_active':quality['active'],'identity_training_samples':quality.get('training_samples',0),'manual_visual_samples':sum(d['manual_samples'] for d in datasets),'proposed_identity_contexts':predicted,'identity_validation':quality,'action_validation':action_quality,'review_categories':dict(categories),'active_action_models':len(action_models),'scope':'Las identidades y las propuestas de jugada se aprenden por separado. Alineación, cambios y plano conservan sus correcciones, pero no se convierten en etiquetas visuales de jugador.'}
    manager.update(generation,stage='Comprobando la versión de las correcciones',progress=95);manager.publish(generation,{'schema':1,'generation':generation,'summary':summary,'parts':parts});print(json.dumps(summary,ensure_ascii=False),flush=True)


def run(manager,generation):
    if not manager.claim(generation):return
    # Share the model pipeline lock so training does not compete with match analysis.
    lockpath=manager.work/'football-analysis.lock';lockpath.parent.mkdir(parents=True,exist_ok=True)
    with lockpath.open('a+b') as lock:
        if lockpath.stat().st_size==0:lock.write(b'0');lock.flush()
        manager.update(generation,state='running',worker_pid=os.getpid(),stage='Esperando a que termine el análisis en curso',progress=1)
        try:
            while True:
                lock.seek(0)
                try:
                    if os.name=='nt':
                        import msvcrt;msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl;fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except (OSError,BlockingIOError):time.sleep(1)
            try:train(manager,generation)
            finally:
                lock.seek(0)
                if os.name=='nt':msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
        except Exception as error:
            manager.update(generation,state='failed',stage='El entrenamiento se interrumpió',error=str(error)[:600]);raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(APP_DIR));p.add_argument('--work');p.add_argument('--generation',type=int);p.add_argument('--watch',action='store_true');p.add_argument('--once',action='store_true');args=p.parse_args();manager=LearningJobs(args.root,args.work,python=os.sys.executable)
    if args.generation is not None:return run(manager,args.generation)
    if args.watch:
        print('Aprendizaje automático activo. Cada cambio guardado se agrupa y reentrena.',flush=True)
        while True:manager.tick();time.sleep(3)
    else:
        generation=manager.sync(force=True);run(manager,generation)
if __name__=='__main__':main()
