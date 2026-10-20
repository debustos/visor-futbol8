"""Link automatic ball/motion and temporal candidates to players, with explicit uncertainty."""
from collections import defaultdict
import numpy as np

def enrich(records,events,temporal):
    events=list(events);ambiguous=[]
    def stable_actor(t):
        votes=defaultdict(list)
        for r in records:
            if t-2<=r['time']<=t+.4 and r.get('possession'):
                owner=r['possession']['track_id'];b=next((b for b in r['tracks'] if b['id']==owner),None)
                if b:votes[owner].append((r,b))
        ranked=sorted(votes.values(),key=len,reverse=True)
        if not ranked or len(ranked[0])<2:return None
        if len(ranked)>1 and len(ranked[0])-len(ranked[1])<2:return None
        return ranked[0][-1]
    for event in temporal:
        label=event['class'];t=event['time'];actor=stable_actor(t);kind=None;player=None
        if label in ('Goal','Shots on target','Shots off target'):
            kind='goal' if label=='Goal' else 'shot'
            if actor and actor[1].get('player_id'):player=actor[1]['player_id']
        elif label=='Foul' and actor:
            r,owner=actor
            if owner.get('position') is not None:
                opponents=[b for b in r['tracks'] if b['position'] is not None and b['kit'] in ('orange','opponent') and b['kit']!=owner['kit']]
                opponents.sort(key=lambda b:np.linalg.norm(np.array(b['position'])-owner['position']))
                if opponents and np.linalg.norm(np.array(opponents[0]['position'])-owner['position'])<5:
                    if owner.get('player_id'):kind='foul_won';player=owner['player_id']
                    elif opponents[0].get('player_id'):kind='foul_committed';player=opponents[0]['player_id']
        if kind and player:
            events.append({'time':t,'player_id':player,'kind':kind,'outcome':'goal' if kind=='goal' else 'unknown','state':'candidate','score':event['score'],'evidence_start':max(0,t-3),'evidence_end':t+3,'method':'Temporal event model plus ball-owner proximity. Actor and event require independent validation.'})
        elif label in ('Goal','Shots on target','Shots off target','Foul','Substitution'):ambiguous.append({**event,'reason':'No stable, unique player attribution'})
    # Evidence-supported dribble candidates: same owner around a close encounter, separated after one second.
    used={}
    for index,r in enumerate(records):
        if not r.get('possession'):continue
        tid=r['possession']['track_id'];owner=next((b for b in r['tracks'] if b['id']==tid and b.get('player_id')),None)
        if not owner or owner['position'] is None or owner['kit']!='orange':continue
        if r['time']-used.get(owner['player_id'],-100)<4:continue
        rivals=[b for b in r['tracks'] if b['kit']=='opponent' and b['position'] is not None]
        rivals.sort(key=lambda b:np.linalg.norm(np.array(b['position'])-owner['position']))
        if not rivals or np.linalg.norm(np.array(rivals[0]['position'])-owner['position'])>3:continue
        opponent=rivals[0];future=[q for q in records[index+1:index+11] if .8<=q['time']-r['time']<=1.8 and q.get('possession') and q['possession']['track_id']==tid]
        if len(future)<2:continue
        later=future[-1];same=next((b for b in later['tracks'] if b['id']==tid),None);defender=next((b for b in later['tracks'] if b['id']==opponent['id']),None)
        if not same or not defender or same['position'] is None or defender['position'] is None:continue
        if np.linalg.norm(np.array(same['position'])-defender['position'])<5:continue
        used[owner['player_id']]=r['time'];events.append({'time':r['time'],'player_id':owner['player_id'],'kind':'dribble','outcome':'success','state':'candidate','score':min(r['ball']['confidence'],later['ball']['confidence']),'evidence_start':max(0,r['time']-1),'evidence_end':later['time']+1,'method':'Same ball owner before and after a close opponent encounter. A separation alone does not certify a successful dribble.'})
    goals=[e for e in events if e['kind']=='goal']
    shots=[e for e in events if e['kind'] in ('shot','goal')]
    for shot in shots:
        passes=[e for e in events if e['kind']=='pass' and e.get('receiver_id')==shot['player_id'] and 0<=shot['time']-e['time']<=6]
        if not passes:continue
        p=max(passes,key=lambda e:e['time'])
        if shot['kind']=='goal':events.append({**p,'kind':'assist','state':'candidate','goal_time':shot['time'],'method':'Candidate final pass to the scorer; goal and intervening touches are not certified.'})
        actor=stable_actor(shot['time'])
        if actor and actor[1]['position'] is not None:
            x,y=actor[1]['position']
            if 30<x<70 and y<22:events.append({**p,'kind':'big_chance','state':'candidate','method':'Pass followed by a shot candidate in an approximate central box; chance quality is not validated.'})
    # Limit repeated temporal proposals of the same metric and actor to one per four-second neighborhood.
    result=[]
    for e in sorted(events,key=lambda e:e['time']):
        if any(v['player_id']==e['player_id'] and v['kind']==e['kind'] and abs(v['time']-e['time'])<2 for v in result):continue
        result.append(e)
    return result,ambiguous

def substitutions(records):
    crossing=[];last={};presence=defaultdict(list)
    for r in records:
        for b in r['tracks']:
            pid=b.get('player_id');p=b.get('position')
            if not pid or p is None:continue
            x,y=p;presence[pid].append((r['time'],p))
            if pid in last:
                t,q=last[pid]
                if r['time']-t<=.6 and 5<y<95:
                    if 1<q[0]<99 and (x<-1 or x>101):crossing.append({'player_id':pid,'time':r['time'],'direction':'out','side':'left' if x<0 else 'right'})
                    if (q[0]<-1 or q[0]>101) and 1<x<99:crossing.append({'player_id':pid,'time':r['time'],'direction':'in','side':'left' if x<50 else 'right'})
            last[pid]=(r['time'],p)
    candidates=[]
    for out in [e for e in crossing if e['direction']=='out']:
        follows=[t for t,p in presence[out['player_id']] if out['time']+2<t<out['time']+15 and 0<=p[0]<=100]
        if follows:continue
        entries=[e for e in crossing if e['direction']=='in' and e['side']==out['side'] and e['player_id']!=out['player_id'] and abs(e['time']-out['time'])<=10]
        if len(entries)!=1:continue
        entry=entries[0];inside=[t for t,p in presence[entry['player_id']] if entry['time']+2<t<entry['time']+15 and 0<=p[0]<=100]
        if len(inside)<10:continue
        candidates.append({'time':round((out['time']+entry['time'])/2,2),'out_id':out['player_id'],'in_id':entry['player_id'],'state':'probable','evidence_start':max(0,min(out['time'],entry['time'])-3),'evidence_end':max(out['time'],entry['time'])+5,'method':'Paired observed border crossings plus sustained new-player presence. Approximate calibration.'})
    return candidates
