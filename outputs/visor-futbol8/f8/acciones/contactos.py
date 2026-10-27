"""Foot contacts, possession and conservative ownership transitions. Moved from automatic_core.py without changes."""
from __future__ import annotations
import math
import numpy as np

def foot_contacts(record):
    """Measured contact with a reachable foot region; projection is optional.

    This is a contact proposal, not proof of control. The pass engine must also
    observe release and a travelling ball before crediting a transfer.
    """
    ball=record.get('ball')
    if not ball or not ball.get('center'):return []
    candidates=[]
    for p in record['tracks']:
        if p.get('kit') not in ('orange','opponent','keeper') or not p.get('box'):continue
        x1,y1,x2,y2=p['box'];x,y=ball['center'];height=max(y2-y1,1)
        # An extended foot can lie beyond the midpoint of the person box.
        dx=max(x1-.15*height-x,0,x-x2-.15*height)
        dy=abs(y-y2)
        distance=math.hypot(dx,dy)/height
        center_distance=math.hypot(x-(x1+x2)/2,y-y2)/height
        if distance<.25 and y>y1+.68*height and center_distance<.65:
            candidates.append((distance+.12*center_distance,p,distance))
    if any(p.get('keypoints') for p in record['tracks']):
        from f8.balon.pose_contacts import ankle_contacts
        byid={str(p['id']):(score,p,distance) for score,p,distance in candidates}
        for score,p,distance in ankle_contacts(record):
            old=byid.get(str(p['id']))
            if old is None or score<old[0]:byid[str(p['id'])]=(score,p,distance)
        candidates=list(byid.values())
    candidates.sort(key=lambda v:v[0])
    return candidates

def infer_possession(record):
    candidates=foot_contacts(record)
    if not candidates or (len(candidates)>1 and candidates[1][0]-candidates[0][0]<.06):return None
    _,p,distance=candidates[0]
    method='reachable_foot_region'
    if p.get('keypoints'):
        from f8.balon.pose_contacts import ankle_contacts
        if any(q['id']==p['id'] and abs(d-distance)<1e-5 for _,q,d in ankle_contacts(record)):method='measured_ankle_contact'
    return {'track_id':p['id'],'kit':p['kit'],'distance':round(distance,3),'method':method}

def action_candidates(records):
    """Conservative ownership transitions. The result remains an estimate with video evidence."""
    events=[];last=None;last_seen=None;active=None;run=[];used=set()
    for r in records:
        o=r.get('possession')
        if not o:
            if last_seen is not None and r['time']-last_seen>2.2:last=None;active=None;run=[]
            continue
        last_seen=r['time'];key=o['track_id']
        if active!=key:active=key;run=[]
        run.append(r)
        run=[v for v in run if r['time']-v['time']<=.9]
        if len(run)<3 and (last is None or last['track_id']!=key):continue
        b=next((b for b in r['tracks'] if b['id']==key),None)
        if b is None:continue
        current={'time':r['time'],'track_id':key,'kit':o['kit'],'player_id':b.get('player_id'),'position':b['position'],'ball':r['ball']}
        if last and last['track_id']!=key and r['time']-last['time']<=2.2:
            marker=(last['track_id'],key,round(r['time'],1))
            if marker not in used:
                used.add(marker);distance=np.linalg.norm(np.array(current['position'])-last['position']);same=last['kit'] in ('orange','keeper') and current['kit'] in ('orange','keeper');switch=(last['kit']=='opponent')!=(current['kit']=='opponent')
                common={'time':run[0]['time'],'evidence_start':max(0,last['time']-.8),'evidence_end':r['time']+.8,'state':'estimated','score':round(min(last['ball']['confidence'],r['ball']['confidence']),3),'method':'Three sampled observations per owner, unambiguous ball proximity, ownership transition within 2.2 seconds.','source_track':last['track_id'],'target_track':key}
                if same and distance>3 and last['player_id'] and current['player_id'] and last['player_id']!=current['player_id']:
                    events.append({**common,'kind':'pass','player_id':last['player_id'],'receiver_id':current['player_id'],'outcome':'complete'})
                    if current['position'][1]<18 and 25<current['position'][0]<75 and 18<last['position'][1]<82:events.append({**common,'kind':'ball_into_box','player_id':last['player_id'],'outcome':'unknown','state':'candidate','method':'Entry into an approximate box region; field dimensions not verified.'})
                elif switch:
                    if last['kit'] in ('orange','keeper') and last['player_id']:
                        events.append({**common,'kind':'turnover','player_id':last['player_id'],'outcome':'unknown'})
                        # A moving ball transferred over distance is a pass attempt candidate, not automatically every loss.
                        if distance>3 and current['time']-last['time']>.4:events.append({**common,'kind':'pass','player_id':last['player_id'],'receiver_id':None,'outcome':'incomplete','state':'candidate','method':'Ownership changed teams after a moving ball; distinguishes an attempt only as a candidate.'})
                    if current['kit'] in ('orange','keeper') and current['player_id']:events.append({**common,'kind':'recovery','player_id':current['player_id'],'outcome':'unknown'})
        last=current
    return events
