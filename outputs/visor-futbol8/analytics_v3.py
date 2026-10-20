"""Derived player profiles shared by automatic runs and reviewed projections."""
from collections import defaultdict,Counter
import numpy as np
from sequence_engine import METRIC_MAP
from action_quality import metric_counts
METRICS=('goals','assists','big_chances','balls_into_box','fouls_won','fouls_committed','recoveries','successful_dribbles','shots','passes','turnovers')

def profiles_for(records,actions,roster,duration,base_fps=5):
    observations=defaultdict(list)
    for i,r in enumerate(records):
        dt=min(1/base_fps,max(0,(records[i+1]['time'] if i+1<len(records) else duration)-r['time']))
        for b in r['tracks']:
            if b.get('player_id'):observations[b['player_id']].append((r,b,dt))
    profiles=[]
    for p in roster:
        pid=p.get('id',f"orange-{p['jersey_number']}");obs=observations[pid];points=[];intervals=[]
        for r,b,dt in obs:
            pos=b.get('position');geometry=r.get('geometry',{}).get('state','approximate')
            if pos is not None and 0<=pos[0]<=100 and 0<=pos[1]<=100 and geometry not in ('rejected','unavailable'):
                points.append({'time':r['time'],'x':round(pos[0],3),'y':round(pos[1],3),'track_id':b['id'],'segment_id':b.get('segment_id'),'weight_seconds':round(dt,5),'identity_method':b.get('identity',{}).get('method','unknown'),'calibration_state':geometry})
            if not intervals or r['time']-intervals[-1]['end']>.26:intervals.append({'start':r['time'],'end':r['time']})
            else:intervals[-1]['end']=r['time']
        own=[e for e in actions if e.get('player_id')==pid and e['state']!='rejected'];estimated=Counter(k for e in own if e['state']=='estimated' for k in METRIC_MAP.get(e['kind'],[]));confirmed=Counter(k for e in own if e['state']=='confirmed' for k in METRIC_MAP.get(e['kind'],[]));candidate=Counter(k for e in own if e['state']=='candidate' for k in METRIC_MAP.get(e['kind'],[]))
        metrics={k:metric_counts(k,estimated.get(k,0),confirmed.get(k,0),candidate.get(k,0),bool(obs)) for k in METRICS}
        seconds=sum(dt for r,b,dt in obs);mapped=sum(pt['weight_seconds'] for pt in points)
        profiles.append({**p,'id':pid,'samples':len(obs),'mapped_samples':len(points),'visible_seconds':round(seconds,1),'mapped_seconds':round(mapped,1),'coverage_percent':round(seconds/duration*100,1),'mapped_coverage_percent':round(mapped/duration*100,1),'identity_state':'observed' if obs else 'unidentified','intervals':intervals,'metrics':metrics,'actions':own,'heatmap_points':points,'mean_position':np.mean([[v['x'],v['y']] for v in points],axis=0).round(2).tolist() if points else None})
    return profiles
