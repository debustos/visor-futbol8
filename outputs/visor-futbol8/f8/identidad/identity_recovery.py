"""Camera-aware image continuity and calibrated appearance recovery."""
from collections import defaultdict,Counter
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from threadpoolctl import threadpool_limits

def camera_offsets(records):
    offsets={};cumulative=np.zeros(2);previous=None
    for r in records:
        if previous:
            before={b['id']:b for b in previous['tracks']};moves=[]
            for b in r['tracks']:
                a=before.get(b['id'])
                if a and a.get('box') and b.get('box'):
                    p=np.array([(a['box'][0]+a['box'][2])/2,a['box'][3]]);q=np.array([(b['box'][0]+b['box'][2])/2,b['box'][3]]);moves.append(q-p)
            if len(moves)>=4:cumulative+=np.median(moves,axis=0)
        offsets[r['time']]=cumulative.copy();previous=r
    return offsets

def foot(box):return np.array([(box[0]+box[2])/2,box[3]])
def discontinuity(ra,ba,rb,bb,offsets):
    dt=rb['time']-ra['time']
    if dt>1.2:return True
    if not ba.get('box') or not bb.get('box'):
        a=ba.get('position');b=bb.get('position');return a is not None and b is not None and np.linalg.norm(np.array(a)-b)>max(8,dt*35)
    delta=foot(bb['box'])-foot(ba['box'])-(offsets[rb['time']]-offsets[ra['time']]);height=max(40,(ba['box'][3]-ba['box'][1]+bb['box'][3]-bb['box'][1])/2)
    return np.linalg.norm(delta)/height>max(.85,dt*3)

def motion_links(segments,offsets,features):
    edges=[];incoming=defaultdict(list);outgoing=defaultdict(list);count=0
    starts=sorted((s['start'],i) for i,s in enumerate(segments))
    from bisect import bisect_left,bisect_right
    times=[v[0] for v in starts]
    for i,a in enumerate(segments):
        if a['state']=='rejected' or a['number']==1:continue
        ab=a['observations'][-1][1]
        if not ab.get('box'):continue
        for _,j in starts[bisect_left(times,a['end']+.03):bisect_right(times,a['end']+1.2)]:
            b=segments[j]
            if b['state']=='rejected' or b['number']==1:continue
            if a['number'] is not None and b['number'] is not None and a['number']!=b['number']:continue
            bb=b['observations'][0][1]
            if not bb.get('box'):continue
            ah=ab['box'][3]-ab['box'][1];bh=bb['box'][3]-bb['box'][1]
            if not .60<ah/max(bh,1)<1.65:continue
            gap=b['start']-a['end'];delta=foot(bb['box'])-foot(ab['box'])-(offsets[b['start']]-offsets[a['end']]);distance=float(np.linalg.norm(delta))/max(40,(ah+bh)/2)
            if distance>.45+gap*.65:continue
            ai=a['feature_indices'][-2:];bi=b['feature_indices'][:2];visual=float(np.median(np.max(features[ai]@features[bi].T,axis=1))) if ai and bi else .75
            if ai and bi and visual<.60:continue
            cost=.70*distance/(.45+gap*.65)+.30*(1-visual)
            if a['track_id']==b['track_id']:cost*=.55
            edge=(cost,i,j,visual,distance);edges.append(edge);outgoing[i].append(edge);incoming[j].append(edge)
    parent=list(range(len(segments)));members={i:[i] for i in parent};labels={i:s['number'] for i,s in enumerate(segments)}
    def find(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for e in sorted(edges):
        cost,i,j,visual,distance=e
        if cost>.43:continue
        out=sorted(outgoing[i]);inc=sorted(incoming[j])
        if out[0]!=e or inc[0]!=e:continue
        if len(out)>1 and out[1][0]-cost<.09 or len(inc)>1 and inc[1][0]-cost<.09:continue
        a,b=find(i),find(j)
        if a==b:continue
        if labels[a] is not None and labels[b] is not None and labels[a]!=labels[b]:continue
        if any(min(segments[x]['end'],segments[y]['end'])-max(segments[x]['start'],segments[y]['start'])>.08 for x in members[a] for y in members[b]):continue
        parent[b]=a;members[a]+=members.pop(b);labels[a]=labels[a] if labels[a] is not None else labels[b];count+=1
    recovered=0
    for i,s in enumerate(segments):
        n=labels[find(i)]
        if s['number'] is None and n is not None and s['state']!='rejected':s.update(number=n,method='motion_memory',state='estimated',link={'method':'mutual_image_continuity','component':find(i)});recovered+=1
    return {'motion_edges':count,'motion_recovered_segments':recovered}

def calibrated_appearance(segments,features,physical):
    X=features.astype(np.float32)
    if physical is not None:
        parts=[]
        for k in (0,1,2,3,4):
            q=physical[:,k*72:(k+1)*72];parts.append(q/np.maximum(np.linalg.norm(q,axis=1,keepdims=True),1e-8))
        X=np.column_stack([X,np.column_stack(parts)*.4])
    train_rows=[];y=[];groups=[]
    for s in segments:
        if s['number'] in (None,1) or s['method'] not in ('jersey_vote','review_reference'):continue
        times=[r['time'] for r in s['readings'] if r.get('text')==str(s['number']) and r.get('score',0)>=.70]
        near=[r['index'] for r in s['feature_rows'] if s['method']=='review_reference' or times and min(abs(r['time']-t) for t in times)<=3]
        for i in near[::max(1,len(near)//12)]:train_rows.append(i);y.append(s['number']);groups.append(s['track_id'])
    if len(set(y))<2:return {'appearance_recovered_segments':0,'reason':'Insufficient distinct dorsal seeds'}
    y=np.array(y);groups=np.array(groups);train_rows=np.array(train_rows);classes=np.unique(y);support={int(n):len(set(groups[y==n])) for n in classes};eligible=[n for n in classes if support[int(n)]>=3]
    keep=np.isin(y,eligible);y=y[keep];groups=groups[keep];train_rows=train_rows[keep];classes=np.unique(y)
    if len(classes)<2:return {'appearance_recovered_segments':0,'reason':'Insufficient independent tracks per class'}
    folds=StratifiedGroupKFold(n_splits=3,shuffle=True,random_state=20261005);pred=np.zeros((len(y),len(classes)),np.float32)
    with threadpool_limits(limits=4):
        for tr,te in folds.split(X[train_rows],y,groups):
            model=LogisticRegression(C=20,max_iter=400,class_weight='balanced');model.fit(X[train_rows[tr]],y[tr]);values=model.predict_proba(X[train_rows[te]])
            for column,n in enumerate(model.classes_):pred[te,np.flatnonzero(classes==n)[0]]=values[:,column]
        full=LogisticRegression(C=20,max_iter=500,class_weight='balanced');full.fit(X[train_rows],y)
        thresholds={};checks=[];guess=classes[pred.argmax(axis=1)];conf=pred.max(axis=1)
        for n in classes:
            threshold=1.1;stats={}
            for t in (.65,.70,.75,.80,.85,.90,.95):
                mask=(guess==n)&(conf>=t);total=int(mask.sum());ng=len(set(groups[mask]));correct=int(np.sum(y[mask]==n))
                if total>=8 and ng>=2 and correct/total>=.90:threshold=t;stats={'samples':total,'heldout_tracks':ng,'precision_against_dorsal_seeds':correct/total};break
            thresholds[int(n)]=threshold;checks.append({'number':int(n),'threshold':threshold,**stats})
        proposals=[]
        for s in segments:
            ids=s['feature_indices']
            if s['number'] is not None or s['state']=='rejected' or len(ids)<2:continue
            values=full.predict_proba(X[ids]);average=values.mean(axis=0);order=np.argsort(-average);n=int(full.classes_[order[0]]);score=float(np.median(values[:,order[0]]));margin=float(average[order[0]]-average[order[1]]);agreement=float(np.mean(values.argmax(axis=1)==order[0]))
            s['proposal']={'number':n,'similarity':round(score,4),'margin':round(margin,4),'agreement':round(agreement,3),'method':'calibrated_appearance'}
            if score>=thresholds[n] and margin>=.16 and agreement>=.66:proposals.append((score,s,n))
    recovered=0
    for score,s,n in sorted(proposals,key=lambda v:-v[0]):
        # Exclusivity is resolved at each frame, rather than rejecting a whole
        # trajectory because a competing fragment overlaps for a few seconds.
        s.update(number=n,method='calibrated_appearance',state='estimated');recovered+=1
    return {'appearance_recovered_segments':recovered,'training_samples':len(y),'seed_tracks':len(set(groups)),'classes':classes.tolist(),'heldout_accuracy_against_dorsal_seeds':round(float(np.mean(guess==y)),4),'class_checks':checks,'evaluation_scope':'Held-out track OCR proxy labels; sporting identity accuracy not independently certified.'}
