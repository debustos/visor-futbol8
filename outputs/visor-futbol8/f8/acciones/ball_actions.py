"""Short-touch transitions supported by a measured moving-ball path, not proximity alone."""
import numpy as np

def trajectory_actions(records):
    events=[];last=None
    for index,r in enumerate(records):
        o=r.get('possession');ball=r.get('ball')
        if not o or not ball or ball['confidence']<.6 or o['distance']>.22:continue
        b=next((b for b in r['tracks'] if b['id']==o['track_id']),None)
        if b is None or b['position'] is None:continue
        current={'record':r,'box':b,'index':index,'time':r['time'],'position':np.asarray(ball['position'])}
        if last and last['box']['id']!=b['id'] and .2<=r['time']-last['time']<=3:
            start=last['position'];end=current['position'];delta=end-start;length=float(np.linalg.norm(delta))
            flight=[q for q in records[last['index']+1:index] if q.get('ball') and q['ball']['confidence']>=.25]
            if length>=3 and len(flight)>=2:
                coords=np.asarray([q['ball']['position'] for q in flight]);progress=(coords-start)@delta/(length*length);residual=np.linalg.norm(coords-(start+progress[:,None]*delta),axis=1)
                # Two measured intermediate positions, compatible with the handoff direction.
                reliable=(progress>-.15)&(progress<1.15)&(residual<min(5,length*.4))
                monotone=np.mean(np.diff(progress)>=-.12) if len(progress)>1 else 0
                if np.sum(reliable)>=2 and np.mean(reliable)>=.7 and monotone>=.65:
                    a=last['box'];same=a['kit'] in ('orange','keeper') and b['kit'] in ('orange','keeper');switch=(a['kit']=='opponent')!=(b['kit']=='opponent')
                    common={'time':round(last['time']+.1,4),'evidence_start':max(0,last['time']-.8),'evidence_end':r['time']+.8,'state':'estimated','score':round(min(last['record']['ball']['confidence'],ball['confidence']),3),'source_track':a['id'],'target_track':b['id'],'method':'Unambiguous close-ball contacts, high-confidence endpoints and at least two intermediate moving-ball observations. Intent and full coverage are not certified.','ball_path_samples':len(flight),'path_length_relative':round(length,2)}
                    if same and a.get('player_id') and b.get('player_id') and a['player_id']!=b['player_id']:
                        events.append({**common,'kind':'pass','player_id':a['player_id'],'receiver_id':b['player_id'],'outcome':'complete'})
                        if b['position'][1]<18 and 25<b['position'][0]<75 and a['position'][1]>=18:events.append({**common,'kind':'ball_into_box','player_id':a['player_id'],'state':'candidate','outcome':'unknown','method':'Moving-ball pass enters the approximate opposition box. Pitch dimensions are unverified.'})
                    elif switch:
                        if a.get('player_id'):events.append({**common,'kind':'turnover','player_id':a['player_id'],'outcome':'unknown'});events.append({**common,'kind':'pass','player_id':a['player_id'],'receiver_id':None,'outcome':'incomplete','state':'candidate'})
                        if b.get('player_id'):events.append({**common,'kind':'recovery','player_id':b['player_id'],'outcome':'unknown'})
        last=current
    return events
