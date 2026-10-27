"""Contact -> release -> travel -> reception with duration-based ownership and evidence."""
from collections import defaultdict
import hashlib, numpy as np
from f8.core.metricas import METRIC_MAP
from f8.acciones.proposal_review import checked_proposals,review_proposals,complementary_evidence

def event_id(e):
    key=f"{e['kind']}:{e.get('source_track')}:{e.get('target_track')}:{e['time']:.3f}"
    if e.get('goal_end') is not None:key+=f":goal_end={e['goal_end']}"
    return hashlib.sha256(key.encode()).hexdigest()[:20]

def temporal_shot_proposals(temporal):
    """Group compatible shot/goal evidence, preserving distinct nearby actions."""
    valid,_=checked_proposals(temporal)
    return review_proposals(valid)

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
    actor=dict(ep['actor'])
    if ep.get('contact_identity_evidence'):actor['player_id']=None
    return actor,{'state':'measured_release',**evidence}

def sequence_actions(records, temporal, short_contacts=False):
    from f8.acciones.pass_engine import transfer_events,pass_summary
    valid,rejected=checked_proposals(temporal)
    events,contacts,transitions=transfer_events(records,valid,short_contacts)
    from f8.identidad.identity_recovery import camera_offsets
    offsets=camera_offsets(records)
    # Temporal classifications propose actions; causal release is required for an actor.
    for e in review_proposals(valid):
        klass=e['class']
        if klass not in ('Goal','Shots on target','Shots off target','Foul','Visual goal approach'):continue
        if klass=='Foul':actor={};release={'state':'unobserved','reason':'Contact or possession cannot establish who committed or received a foul'}
        else:actor,release=released_actor(contacts,records,e['time'],offsets)
        team='orange' if actor.get('kit') in ('orange','keeper') else 'opponent' if actor.get('kit')=='opponent' else 'unresolved'
        pid=actor.get('player_id') if team=='orange' else None
        kind='goal' if klass=='Goal' else 'shot' if 'Shots' in klass or klass=='Visual goal approach' else 'foul_committed'
        members=e.get('proposal_evidence',[e]);visual=[q for q in members if q['class']=='Visual goal approach']
        event={'time':e['time'],'kind':kind,'player_id':pid,'state':'candidate','outcome':'goal' if kind=='goal' else 'off_target' if klass=='Shots off target' else 'unknown','score':e['score'],'source_track':actor.get('id'),'team':team,'actor_evidence':release,'visual_evidence':visual[0] if visual else None,'temporal_evidence':e.get('temporal_evidence',[{'class':klass,'score':e['score'],'time':e['time']}]),'proposal_evidence':members,'complementary_evidence':complementary_evidence(e,valid),'evidence_start':e['evidence_start'],'evidence_end':e['evidence_end'],'method':'Propuesta de acción; resultado, equipo, autor y decisión arbitral requieren revisión independiente','reason':'Jugador o acción sin resolver' if not pid else 'Propuesta temporal sin validar','event_validation':'pending','outcome_validation':'pending'}
        if visual:event['goal_end']=visual[0].get('goal_end')
        if klass=='Foul':event.update(foul_role=None,committed_by=None,received_by=None,decision_state='pending')
        events.append(event)
    for shot in [e for e in events if e['kind'] in ('shot','goal') and e.get('player_id') and e.get('team')=='orange']:
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
        if 'proposal_evidence' not in e and any(q['kind']==e['kind'] and q.get('player_id')==e.get('player_id') and q.get('source_track')==e.get('source_track') and abs(q['time']-e['time'])<.7 for q in dedup):continue
        e['id']=event_id(e);dedup.append(e)
    return dedup,{'version':12,'rejected_proposals':rejected,'passes':pass_summary(dedup),'controlled_episodes':len(contacts),'transitions':len(transitions),'travel_supported_transitions':sum(t['travel_verified'] for t in transitions),'state_machine':['contact','release','travel','reception'],'short_contacts_enabled':short_contacts,'single_touch_contacts':sum(len(ep['rows'])==1 for ep in contacts),'scope':'Measured contact, travel and reception rules. Partial automatically detected actions; not certified match totals.'}
