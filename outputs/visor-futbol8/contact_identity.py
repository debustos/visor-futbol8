"""Resolve the name of an action contact from a unique adjacent measured body.

This enriches the contact actor only. It does not join whole trajectories or move
an identity through an occlusion merely because two people are nearby.
"""
import numpy as np
from bisect import bisect_left,bisect_right


def overlap(a,b):
    x=max(0,min(a[2],b[2])-max(a[0],b[0]));y=max(0,min(a[3],b[3])-max(a[1],b[1]))
    intersection=x*y;area=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/max(area,1)


def resolve_contact(ep,records,times,offsets):
    actor=ep['actor']
    if actor.get('player_id') or actor.get('kit') not in ('orange','keeper'):return None
    identity=actor.get('identity',{})
    if identity.get('state') in ('conflict','rejected') or identity.get('method') in ('manual_review','review_conflict') or actor.get('dorsal_guard'):return None
    contact=ep['last'];box=actor.get('box')
    if not box:return None
    t=contact['time'];height=box[3]-box[1];foot=np.array([(box[0]+box[2])/2,box[3]])
    if height<35:return None
    groups={};contradictions=set()
    for r in records[bisect_left(times,t-.15):bisect_right(times,t+.15)]:
        if abs(r['time']-t)<.01 or any(b['id']==actor['id'] for b in r['tracks']):continue
        shift=offsets[r['time']]-offsets[t];predicted=foot+shift;translated=np.array(box)+np.tile(shift,2)
        candidates=[]
        for b in r['tracks']:
            if b.get('kit')!=actor['kit'] or not b.get('box'):continue
            if any(q['id']==b['id'] for q in contact['tracks']):continue
            h=b['box'][3]-b['box'][1];distance=np.linalg.norm(np.array([(b['box'][0]+b['box'][2])/2,b['box'][3]])-predicted)/height
            score=overlap(translated,b['box'])
            if .75<=h/height<=1.3 and score>=.60 and distance<=.24:candidates.append((score,b))
        candidates.sort(key=lambda x:-x[0])
        if not candidates:continue
        if len(candidates)>1:contradictions.update(b.get('player_id') for _,b in candidates);continue
        score,b=candidates[0];pid=b.get('player_id')
        # A second close body makes a crossing ambiguous, even without a name.
        if any(q['id']!=b['id'] and q.get('kit')==b['kit'] and q.get('box') and np.linalg.norm(np.array([(q['box'][0]+q['box'][2])/2,q['box'][3]])-predicted)<height*.45 for q in r['tracks']):continue
        if not pid:continue
        groups.setdefault(pid,[]).append({'time':r['time'],'track_id':b['id'],'context_id':b.get('person_track_id'),'body_iou':round(score,3)})
    if len(groups)!=1 or contradictions:return None
    pid,evidence=next(iter(groups.items()))
    if len(evidence)<2 or evidence[-1]['time']-evidence[0]['time']<.025:return None
    scores=[q['body_iou'] for q in evidence]
    if max(scores)<.78 or np.median(scores)<.70:return None
    contexts={q['context_id'] or str(q['track_id']) for q in evidence}
    if len(contexts)!=1:return None
    return {'player_id':pid,'method':'unique_adjacent_measured_body','contact_time':t,'support':evidence,'scope':'Contact actor only; no global trajectory merge.'}
