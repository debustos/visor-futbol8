"""Pass contacts and measured travel, independent of intermittent player names."""
from collections import Counter
from bisect import bisect_right,bisect_left
import numpy as np
from identity_recovery import camera_offsets,foot
from automatic_core import foot_contacts
OWN={'orange','keeper'}


def contact_episodes(records,short_contacts,offsets=None):
    offsets=offsets if offsets is not None else camera_offsets(records)
    episodes=[];active=None
    def alias_continuity(ep,r,actor):
        previous=ep['actor'];dt=r['time']-ep['last']['time']
        if not .01<=dt<=.12 or actor.get('kit')!=previous.get('kit'):return False
        if not(str(actor['id']).startswith(('D','N')) or str(previous['id']).startswith(('D','N'))):return False
        if actor.get('player_id') and previous.get('player_id') and actor['player_id']!=previous['player_id']:return False
        if any(b['id']==previous['id'] for b in r['tracks']) or any(b['id']==actor['id'] for b in ep['last']['tracks']):return False
        if not actor.get('box') or not previous.get('box'):return False
        h=actor['box'][3]-actor['box'][1];ph=previous['box'][3]-previous['box'][1]
        if not .7<h/max(ph,1)<1.3:return False
        predicted=foot(previous['box'])+offsets[r['time']]-offsets[ep['last']['time']];distance=float(np.linalg.norm(foot(actor['box'])-predicted));height=max(h,ph,30)
        if distance>.25*height:return False
        # Two simultaneously visible people, or a competing nearby body, cannot be joined.
        return not any(b['id']!=actor['id'] and b.get('kit')==actor['kit'] and b.get('box') and np.linalg.norm(foot(b['box'])-predicted)<distance+.2*height for b in r['tracks'])
    for r in records:
        owner=r.get('possession');ball=r.get('ball')
        actor=next((x for x in r['tracks'] if owner and x['id']==owner['track_id']),None)
        if not(actor and ball and ball['confidence']>=.3 and owner.get('distance',1)<.25):continue
        key=('context',actor['person_track_id']) if actor.get('person_track_id') else ('track',actor['id'],actor.get('segment_id'))
        alias=bool(active and active['key']!=key and alias_continuity(active,r,actor))
        if active and ((active['key']==key and r['time']-active['last']['time']<=.45) or alias):
            active['last']=r;active['rows'].append(r);active['actor']=dict(actor);active['aliases']+=int(alias)
        else:
            active={'key':key,'first':r,'last':r,'rows':[r],'actor':dict(actor),'aliases':0};episodes.append(active)
    contacts=[]
    for ep in episodes:
        rows=ep['rows'];conf=[r['ball']['confidence'] for r in rows]
        stable=(len(rows)>=2 and rows[-1]['time']-rows[0]['time']>=.06) or (short_contacts and len(rows)==1 and conf[0]>=.65 and rows[0]['possession'].get('distance',1)<=.18)
        if not stable:continue
        ids=Counter()
        for r in rows:
            b=next(x for x in r['tracks'] if x['id']==r['possession']['track_id'])
            if b.get('player_id'):ids[b['player_id']]+=1
        ep['actor']['player_id']=next(iter(ids)) if len(ids)==1 else None
        ep['identity_times']=[r['time'] for r in rows if any(b['id']==r['possession']['track_id'] and b.get('player_id')==ep['actor'].get('player_id') for b in r['tracks'])] if ep['actor'].get('player_id') else []
        ep['trusted']=bool(max(conf)>=.65 and np.median(conf)>=.50)
        ep['confidence']=float(np.median(conf));contacts.append(ep)
    if short_contacts:
        from contact_identity import resolve_contact
        times=[r['time'] for r in records]
        for ep in contacts:
            evidence=resolve_contact(ep,records,times,offsets)
            if evidence:
                ep['actor']['player_id']=evidence['player_id'];ep['identity_times']=[q['time'] for q in evidence['support']];ep['contact_identity_evidence']=evidence
    return contacts


def separate_people(a,b):
    aa,bb=a['actor'],b['actor']
    if aa.get('person_track_id') and aa.get('person_track_id')==bb.get('person_track_id'):return False
    if aa['id']==bb['id']:return False
    if aa.get('player_id') and aa.get('player_id')==bb.get('player_id'):return False
    if aa.get('player_id') and bb.get('player_id'):return True
    for r in (a['last'],b['first']):
        one=next((x for x in r['tracks'] if x['id']==aa['id']),None);two=next((x for x in r['tracks'] if x['id']==bb['id']),None)
        if one and two and one.get('box') and two.get('box'):
            height=max(one['box'][3]-one['box'][1],two['box'][3]-two['box'][1],40)
            if np.linalg.norm(foot(one['box'])-foot(two['box']))>.5*height:return True
    return False


def transfer_events(records,temporal,short_contacts):
    offsets=camera_offsets(records) if short_contacts else {};contacts=contact_episodes(records,short_contacts,offsets);observed=[r for r in records if r.get('ball')];times=[r['time'] for r in observed]
    events=[];transitions=[]
    for a,b in zip(contacts,contacts[1:]):
        if a['key']==b['key']:continue
        aa,bb=a['actor'],b['actor'];t0=a['last']['time'];t1=b['first']['time'];gap=t1-t0
        if not .08<=gap<=(5 if short_contacts else 3):continue
        ball0,ball1=a['last']['ball'],b['first']['ball'];path=observed[bisect_right(times,t0):bisect_left(times,t1)];ptimes=[t0]+[r['time'] for r in path]+[t1]
        world0,world1=ball0.get('position'),ball1.get('position');world=False;length=0;residual=None
        if world0 is not None and world1 is not None:
            p0=np.array(world0);p1=np.array(world1);delta=p1-p0;length=float(np.linalg.norm(delta));world_path=[r for r in path if r['ball'].get('position') is not None]
            if length>=1.8 and len(world_path)>=2 and max(np.diff([t0]+[r['time'] for r in world_path]+[t1]))<=.35:
                points=np.array([r['ball']['position'] for r in world_path]);progress=(points-p0)@delta/max(length**2,1e-8);errors=np.linalg.norm(points-(p0+progress[:,None]*delta),axis=1);residual=float(np.median(errors));world=bool(np.mean((progress>-.2)&(progress<1.2)&(errors<max(2,length*.3)))>=.75 and np.mean(np.diff(progress)>=-.15)>=.6)
        image=False;image_samples=0;free_samples=0;screen_length=0;image_gap=None;image_residual=None;blocking_contact=False
        if short_contacts and ball0.get('center') and ball1.get('center'):
            p0=np.array(ball0['center'])-offsets[t0];p1=np.array(ball1['center'])-offsets[t1];delta=p1-p0;screen_length=float(np.linalg.norm(delta))
            image_path=[r for r in path if r['ball'].get('center') and r['ball']['confidence']>=.4];image_samples=len(image_path)
            if screen_length>=18 and image_path:
                points=np.array([np.array(r['ball']['center'])-offsets[r['time']] for r in image_path]);progress=(points-p0)@delta/max(screen_length**2,1e-8);errors=np.linalg.norm(points-(p0+progress[:,None]*delta),axis=1);good=(progress>-.12)&(progress<1.12)&(errors<max(12,screen_length*.3));image_residual=float(np.median(errors));image_gap=float(max(np.diff([t0]+[r['time'] for r in image_path]+[t1])))
                for r,g,progression in zip(image_path,good,progress):
                    owner=r.get('possession')
                    if g and .04<progression<.96 and not owner and not foot_contacts(r):free_samples+=1
                    if owner and owner['track_id'] not in (aa['id'],bb['id']) and not any(x['id']==owner['track_id'] and x.get('person_track_id') in (aa.get('person_track_id'),bb.get('person_track_id')) and x.get('person_track_id') for x in r['tracks']) and r['ball']['confidence']>=.65:blocking_contact=True
                image=bool(image_gap<=.65 and (image_samples>=2 or gap<=1.2) and np.mean(good)>=.7 and (len(progress)==1 or np.mean(np.diff(progress)>=-.12)>=.67))
        if length<1.8 and screen_length<18:continue
        travel=bool(world or image)
        if short_contacts:travel=bool(travel and a['trusted'] and b['trusted'] and free_samples>=1 and not blocking_contact)
        same=aa.get('kit') in OWN and bb.get('kit') in OWN;switch=(aa.get('kit')=='opponent')!=(bb.get('kit')=='opponent')
        transition={'time':t0,'reception_time':t1,'source_track':aa['id'],'target_track':bb['id'],'source_player_id':aa.get('player_id'),'target_player_id':bb.get('player_id'),'contact_confidence':round(min(a['confidence'],b['confidence']),4),'travel_verified':travel,'image_travel_verified':bool(image and travel),'image_path_samples':image_samples,'measured_path_samples':len(path),'free_flight_samples':free_samples,'largest_sample_gap':round(float(max(np.diff(ptimes))),3),'largest_image_gap':image_gap,'median_path_residual':round(residual,3) if residual is not None else None,'median_image_residual':image_residual,'blocking_contact':blocking_contact,'source_context_id':aa.get('person_track_id'),'target_context_id':bb.get('person_track_id'),'source_contact_identity':a.get('contact_identity_evidence'),'target_contact_identity':b.get('contact_identity_evidence'),'source_physical_alias_links':a.get('aliases',0),'target_physical_alias_links':b.get('aliases',0),'source_contact_start':a['first']['time'],'source_identity_times':a['identity_times'],'target_contact_end':b['last']['time'],'target_identity_times':b['identity_times'],'version':6};transitions.append(transition)
        common={'time':round(t0,4),'evidence_start':max(0,a['first']['time']-.7),'evidence_end':t1+1,'state':'estimated' if travel else 'candidate','score':round(min(a['confidence'],b['confidence']),3),'source_track':aa['id'],'target_track':bb['id'],'sequence':transition,'method':'Contacto, salida, vuelo medido sin otro contacto y recepción; identidad conservada dentro del mismo segmento.','team':'orange'}
        if same and separate_people(a,b):
            events.append({**common,'kind':'pass','player_id':aa.get('player_id'),'receiver_id':bb.get('player_id'),'outcome':'complete','attribution':'identified' if aa.get('player_id') else 'unidentified','reason':'Emisor sin identificar' if not aa.get('player_id') else 'Pase observado automáticamente'})
            if travel and world0 is not None and world1 is not None and 25<world1[0]<75 and world1[1]<18 and world0[1]>=18:events.append({**common,'kind':'ball_into_box','player_id':aa.get('player_id'),'state':'candidate','outcome':'unknown'})
        elif switch:
            shot_context=any('Shots' in e['class'] or e['class']=='Goal' for e in temporal if t0-1.5<=e['time']<=t1+1.5)
            if aa.get('kit') in OWN and aa.get('player_id'):
                events.append({**common,'kind':'turnover','player_id':aa['player_id'],'state':'candidate','outcome':'unknown','reason':'Revisar intención: tiro, despeje, rebote o pérdida','shot_context':shot_context})
                if travel and not shot_context:events.append({**common,'kind':'pass','player_id':aa['player_id'],'receiver_id':None,'state':'candidate','outcome':'incomplete'})
            if bb.get('kit') in OWN and bb.get('player_id'):events.append({**common,'time':round(t1,4),'source_track':bb['id'],'target_track':aa['id'],'kind':'recovery','player_id':bb['player_id'],'state':'estimated' if travel else 'candidate','outcome':'unknown'})
    return events,contacts,transitions


def pass_summary(actions):
    passes=[e for e in actions if e.get('kind')=='pass' and e.get('outcome')=='complete' and e.get('team','orange')=='orange']
    counted=[e for e in passes if e['state'] in ('estimated','confirmed')]
    return {'detected':len(counted),'attributed':sum(bool(e.get('player_id')) for e in counted),'unattributed':sum(not e.get('player_id') for e in counted),'candidates':sum(e['state']=='candidate' for e in passes),'scope':'Pases completados observados; los emisores sin identidad se conservan en el equipo y no se asignan a un jugador.'}
