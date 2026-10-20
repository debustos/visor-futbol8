"""Sustained on-field presence and paired border evidence for F8 lineups."""
from collections import defaultdict
import numpy as np

def presence_lineup(records,opening=45):
    presence=defaultdict(list);crossings=[];last={};occupancy=[]
    for r in records:
        visible=[]
        for b in r['tracks']:
            pid=b.get('player_id');p=b.get('position')
            if not pid or p is None or r.get('geometry',{}).get('state') in ('rejected','unavailable'):continue
            t=r['time'];inside=1<=p[0]<=99 and 0<=p[1]<=100
            if inside:presence[pid].append((t,p,b['id']));visible.append(pid)
            if pid in last:
                before,q=last[pid]
                if t-before<=.5 and 5<p[1]<95:
                    if 2<q[0]<98 and (p[0]<0 or p[0]>100):crossings.append({'player_id':pid,'time':t,'direction':'out','side':'left' if p[0]<0 else 'right'})
                    if (q[0]<0 or q[0]>100) and 2<p[0]<98:crossings.append({'player_id':pid,'time':t,'direction':'in','side':'left' if p[0]<50 else 'right'})
            last[pid]=(t,p)
        occupancy.append({'time':r['time'],'identified_on_pitch':len(set(visible)),'ids':sorted(set(visible))})
    initial=[];episodes={};alerts=[]
    for pid,rows in presence.items():
        early=[v for v in rows if v[0]<=opening]
        spans=[]
        for t,p,tid in rows:
            if not spans or t-spans[-1]['end']>.6:spans.append({'start':t,'end':t,'samples':1})
            else:spans[-1]['end']=t;spans[-1]['samples']+=1
        episodes[pid]=spans
        stable=[e for e in spans if e['end']-e['start']>=1]
        early_spans=[e for e in spans if e['start']<=opening and min(e['end'],opening)-e['start']>=2]
        if early_spans and len(early)>=10:initial.append({'player_id':pid,'first_seen':early[0][0],'last_seen_initial':early[-1][0],'observed_seconds':round(sum(min(e['end'],opening)-e['start'] for e in early_spans),1),'state':'probable','reason':'Presencia sostenida dentro del campo durante el inicio; momento de saque no verificado'})
        if stable and stable[0]['start']>opening:alerts.append({'player_id':pid,'time':stable[0]['start'],'evidence_start':max(0,stable[0]['start']-5),'evidence_end':stable[0]['start']+8,'state':'uncertain','reason':'Primera presencia sostenida tardía: entrada o identificación tardía, no prueba de cambio'})
    subs=[]
    for out in [e for e in crossings if e['direction']=='out']:
        entries=[e for e in crossings if e['direction']=='in' and e['side']==out['side'] and e['player_id']!=out['player_id'] and abs(e['time']-out['time'])<=15]
        if len(entries)!=1:continue
        entry=entries[0];incoming=[e for e in episodes[entry['player_id']] if entry['time']<=e['start']<=entry['time']+5 and e['end']-e['start']>=2]
        outgoing=[t for t,p,tid in presence[out['player_id']] if out['time']+2<t<out['time']+12]
        if not incoming or outgoing:continue
        if any(s['out_id']==out['player_id'] and abs(s['time']-out['time'])<15 for s in subs):continue
        subs.append({'time':round((out['time']+entry['time'])/2,4),'out_id':out['player_id'],'in_id':entry['player_id'],'state':'probable','evidence_start':max(0,min(out['time'],entry['time'])-4),'evidence_end':max(out['time'],entry['time'])+8,'method':'Cruces de banda emparejados, permanencia del entrante y ausencia posterior del saliente; geometría aproximada'})
    initial.sort(key=lambda p:p['first_seen']);overfull=[o for o in occupancy if o['identified_on_pitch']>8]
    return {'expected':8,'opening_seconds':opening,'identified_candidates':initial,'state':'probable' if len(initial)==8 and not any(o['time']<opening for o in overfull) else 'incomplete','unidentified_slots':max(0,8-len(initial)),'substitutions':subs,'visibility_alerts':alerts,'presence_episodes':episodes,'overfull_samples':len(overfull),'reason':'Sustained visibility is evidence of presence, not minutes played or substitution certainty.'}
