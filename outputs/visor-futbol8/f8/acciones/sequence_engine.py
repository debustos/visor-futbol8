"""Contact -> release -> travel -> reception with duration-based ownership and evidence."""
from collections import defaultdict
import hashlib, numpy as np
from f8.core.metricas import METRIC_MAP

def event_id(e):return hashlib.sha256(f"{e['kind']}:{e.get('source_track')}:{e.get('target_track')}:{e['time']:.3f}".encode()).hexdigest()[:20]

def temporal_shot_proposals(temporal):
    """One proposal per shot window; retain the strongest class and all evidence."""
    other=[dict(e) for e in temporal if e['class'] not in ('Shots on target','Shots off target')]
    groups=[]
    for e in sorted((e for e in temporal if e['class'] in ('Shots on target','Shots off target')),key=lambda e:e['time']):
        if groups and e['time']-groups[-1][0]['time']<.7:groups[-1].append(e)
        else:groups.append([e])
    for group in groups:
        winner=dict(max(group,key=lambda e:e['score']))
        winner['temporal_evidence']=[{'class':e['class'],'score':e['score'],'time':e['time']} for e in group]
        other.append(winner)
    return sorted(other,key=lambda e:e['time'])

def released_actor(contacts,records,time,offsets):
    """Attribute a proposal only to a measured contact followed by ball release.

    This establishes a causal actor proposal; it does not establish shot intent.
    A reception/save near the event timestamp is not a shot by that goalkeeper.
    """
    from f8.acciones.contactos import foot_contacts
    candidates=[]
    for ep in contacts:
        t0=ep['last']['time'];ball=ep['last'].get('ball')
        if not ep['trusted'] or not -.25<=time-t0<=1.8 or not ball or not ball.get('center'):continue
        points=[];blocked=False
        for r in records:
            if not t0<r['time']<=min(t0+.8,time+.6):continue
            b=r.get('ball')
            if not b or not b.get('center') or b['confidence']<.4:continue
            touching=foot_contacts(r)
            if touching:
                if any(x[1]['id']!=ep['actor']['id'] and not(ep['actor'].get('person_track_id') and x[1].get('person_track_id')==ep['actor']['person_track_id']) for x in touching):blocked=True
                break
            points.append((r['time'],np.array(b['center'])-offsets[r['time']]))
        if blocked or len(points)<2:continue
        start=np.array(ball['center'])-offsets[t0];delta=points[-1][1]-start;length=float(np.linalg.norm(delta))
        height=(ep['actor'].get('box') or [0,0,0,60])[3]-(ep['actor'].get('box') or [0,0,0,60])[1]
        if length<max(12,.2*height):continue
        xy=np.array([p[1] for p in points]);progress=(xy-start)@delta/max(length**2,1e-8)
        residual=np.linalg.norm(xy-(start+progress[:,None]*delta),axis=1)
        if np.mean(residual<max(10,length*.3))<.8 or np.any(np.diff(progress)<-.15):continue
        candidates.append((ep,{'contact_time':t0,'release_samples':len(points),'screen_travel_pixels':round(length,2),'source_context_id':ep['actor'].get('person_track_id')}))
    if len(candidates)!=1:return {},{'state':'ambiguous' if candidates else 'unobserved','candidate_actors':len(candidates)}
    ep,evidence=candidates[0]
    return ep['actor'],{'state':'measured_release',**evidence}

def sequence_actions(records, temporal, short_contacts=False):
    from f8.acciones.pass_engine import transfer_events,pass_summary
    events,contacts,transitions=transfer_events(records,temporal,short_contacts)
    from f8.identidad.identity_recovery import camera_offsets
    offsets=camera_offsets(records)
    # Temporal classifications propose actions; causal release is required for an actor.
    for e in temporal_shot_proposals(temporal):
        klass=e['class']
        if klass not in ('Goal','Shots on target','Shots off target','Foul','Visual goal approach'):continue
        before=[ep for ep in contacts if -0.15<=e['time']-ep['last']['time']<=1.8]
        ep=min(before,key=lambda p:abs(e['time']-p['last']['time'])) if before else None
        if klass=='Foul':actor=ep['actor'] if ep else {};release={'state':'not_applicable'}
        else:actor,release=released_actor(contacts,records,e['time'],offsets)
        pid=actor.get('player_id')
        kind='goal' if klass=='Goal' else 'shot' if 'Shots' in klass or klass=='Visual goal approach' else 'foul_won' if actor.get('kit') in ('orange','keeper') else 'foul_committed'
        if klass in ('Goal','Shots on target','Shots off target','Visual goal approach') and actor.get('kit')=='opponent':continue
        events.append({'time':e['time'],'kind':kind,'player_id':pid,'state':'candidate','outcome':'goal' if kind=='goal' else 'off_target' if klass=='Shots off target' else 'unknown','score':e['score'],'source_track':actor.get('id'),'team':'orange' if actor.get('kit') in ('orange','keeper') else 'unresolved','actor_evidence':release,'visual_evidence':e if klass=='Visual goal approach' else None,'temporal_evidence':e.get('temporal_evidence',[{'class':klass,'score':e['score'],'time':e['time']}]),'evidence_start':max(0,e['time']-3),'evidence_end':e['time']+3,'method':'Vuelo medido hacia postes visibles; requiere verificar intención y jugador' if klass=='Visual goal approach' else 'Propuesta temporal y contacto previo; requiere verificar intención o decisión arbitral','reason':'Jugador o acción sin resolver' if not pid else 'Propuesta temporal sin validar'})
    for shot in [e for e in events if e['kind'] in ('shot','goal') and e.get('player_id')]:
        passes=[e for e in events if e['kind']=='pass' and e.get('receiver_id')==shot['player_id'] and 0<=shot['time']-e['time']<=6]
        if not passes:continue
        p=max(passes,key=lambda e:e['time'])
        if shot['kind']=='goal':events.append({**p,'kind':'assist','state':'candidate','goal_time':shot['time'],'outcome':'unknown'})
        events.append({**p,'kind':'big_chance','state':'candidate','shot_time':shot['time'],'outcome':'unknown','reason':'La calidad de la ocasión exige comprobar distancia, oposición e intención'})
    # Successful dribble proposals require continuity of control and relative progress past a defender.
    for ep in contacts:
        if ep['last']['time']-ep['first']['time']<.6 or not ep['actor'].get('player_id') or ep['actor']['kit']!='orange':continue
        first,last=ep['first'],ep['last'];a=next((b for b in first['tracks'] if b['id']==ep['actor']['id']),None);z=ep['actor']
        if not a or a.get('position') is None or z.get('position') is None:continue
        move=np.array(z['position'])-a['position'];distance=float(np.linalg.norm(move))
        if distance<2:continue
        direction=move/distance
        for defender in first['tracks']:
            if defender['kit']!='opponent' or defender.get('position') is None:continue
            q=next((b for b in last['tracks'] if b['id']==defender['id'] and b.get('position') is not None),None)
            if q and np.linalg.norm(np.array(defender['position'])-a['position'])<3 and (np.array(defender['position'])-a['position'])@direction>0 and (np.array(q['position'])-z['position'])@direction<-.5:
                events.append({'time':first['time'],'kind':'dribble','player_id':z['player_id'],'source_track':z['id'],'state':'candidate','outcome':'success','score':min(first['ball']['confidence'],last['ball']['confidence']),'evidence_start':max(0,first['time']-1),'evidence_end':last['time']+1,'method':'Control sostenido y avance relativo más allá de un rival; revisión necesaria'});break
    dedup=[]
    for e in sorted(events,key=lambda e:e['time']):
        if any(q['kind']==e['kind'] and q.get('player_id')==e.get('player_id') and q.get('source_track')==e.get('source_track') and abs(q['time']-e['time'])<.7 for q in dedup):continue
        e['id']=event_id(e);dedup.append(e)
    return dedup,{'version':11,'passes':pass_summary(dedup),'controlled_episodes':len(contacts),'transitions':len(transitions),'travel_supported_transitions':sum(t['travel_verified'] for t in transitions),'state_machine':['contact','release','travel','reception'],'short_contacts_enabled':short_contacts,'single_touch_contacts':sum(len(ep['rows'])==1 for ep in contacts),'scope':'Measured contact, travel and reception rules. Partial automatically detected actions; not certified match totals.'}
