"""Commit v3 automatic results and a review queue without altering prior manual records."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import json,hashlib,os
from automatic_core import write_json
from pitch_geometry import attach_geometry
from sequence_engine import sequence_actions
from presence_engine import presence_lineup
from analytics_v3 import profiles_for
from runtime_context import ROOT,WORK,CACHE,SOURCE

def commit():
    out=ROOT/'automatic';cache=CACHE;metadata=json.loads((out/'metadata.json').read_text());records=json.loads((cache/'dense-v3.json').read_text());views=json.loads((out/'geometry-views.json').read_text());geometry=attach_geometry(records,views);temporal=json.loads((out/'temporal-candidates.json').read_text());actions,sequence=sequence_actions(records,temporal);lineup=presence_lineup(records);roster=json.loads((ROOT/'plantilla.json').read_text(encoding='utf8'))['players'];profiles=profiles_for(records,actions,roster,metadata['duration']);segments=json.loads((out/'identity-segments.json').read_text());memory=json.loads((out/'memory-quality.json').read_text());dense=json.loads((out/'dense-ball-quality.json').read_text());queue=[]
    source=Path(metadata['source']);stat=source.stat();source_key=hashlib.sha256((str(source.resolve())+str(stat.st_size)+str(stat.st_mtime_ns)+hashlib.sha256((cache/'scan.json').read_bytes()).hexdigest()+'v3').encode()).hexdigest()[:24]
    for s in segments:
        pid=f"orange-{s['number']}" if s['number'] is not None else None;proposal=s.get('proposal');near_event=any(e.get('source_track')==s['track_id'] and s['start']<=e['time']<=s['end'] for e in actions)
        queue.append({'id':'identity-'+s['id'],'category':'identity','priority':1 if near_event else 2 if not pid else 4,'track_id':s['track_id'],'segment_id':s['id'],'time':s['start'],'start':s['start'],'end':s['end'],'evidence_start':max(0,s['start']-.5),'evidence_end':min(metadata['duration'],s['end']+.5),'player_id':pid,'candidate_player_id':f"orange-{proposal['number']}" if proposal else None,'reason':'Identidad automática para verificar' if pid else 'Identidad pendiente o conflicto de apariencia','method':s['method'],'proposal':proposal})
    for e in actions:queue.append({**e,'category':'event','priority':1 if e['state']=='candidate' else 2,'reason':e.get('reason','Acción estimada: revisar contacto, intención y receptor')})
    queue.append({'id':'lineup-initial','category':'lineup','priority':1,'time':0,'evidence_start':0,'evidence_end':45,'players':lineup['identified_candidates'],'reason':'Comprobar los ocho titulares; candidatos incompletos'})
    for i,s in enumerate(lineup['substitutions']):
        s['id']=f'substitution-{i}-{s["time"]:.3f}';queue.append({**s,'category':'substitution','priority':1,'reason':'Cambio propuesto por cruces de banda y presencia sostenida'})
    for i,a in enumerate(lineup['visibility_alerts']):queue.append({**a,'id':f'presence-alert-{i}-{a["time"]:.3f}','category':'substitution','priority':3,'in_id':a['player_id'],'out_id':None})
    for view in views:
        start=max(0,view['time']-2);end=min(metadata['duration'],view['time']+2)
        queue.append({'id':f'geometry-{view["frame"]}','category':'geometry','priority':2 if view['state'] in ('rejected','unavailable') else 4,'time':view['time'],'start':start,'end':end,'evidence_start':start,'evidence_end':end,'reason':view['reason'],'geometry':view})
    queue.sort(key=lambda q:(q['priority'],q['time'],q['id']));completed=datetime.now(timezone.utc).isoformat()
    q={'version':3,'sampled_frames':len(records),'base_frames':dense['base_samples'],'adaptive_frames':dense['adaptive_samples'],'ball_visible_frames':sum(r['ball'] is not None for r in records),'possession_frames':sum(r.get('possession') is not None for r in records),'identified_players':sum(p['samples']>0 for p in profiles),'identified_player_observations':sum(p['samples'] for p in profiles),'duplicate_claims_rejected':memory['duplicate_claims_rejected'],'automatic_action_estimates':len(actions),'estimated_actions':sum(e['state']=='estimated' for e in actions),'candidate_actions':sum(e['state']=='candidate' for e in actions),'manual_annotation_inputs':memory.get('reviewed_reference_inputs',0),'review_queue_items':len(queue),'probable_substitutions':len(lineup['substitutions']),'geometry':'F8 marking evidence and camera update; relative plane remains approximate','completed_at_utc':completed,'memory':{k:v for k,v in memory.items() if k!='cuts'},'sequence':sequence,'geometry_quality':geometry,'scope':'Automatic partial reconstruction with reviewable uncertainty. No certified full-match totals.'}
    for minute in sorted({int(r['time']//60) for r in records}):write_json(out/'chunks'/f'{minute:03}.json',[r for r in records if int(r['time']//60)==minute])
    for name,value in [('profiles',profiles),('actions',actions),('lineup',lineup),('quality',q),('uncertainties',queue),('geometry-quality',geometry),('sequence-quality',sequence),('review-manifest',{'version':3,'source_key':source_key,'source':str(source),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'completed_at_utc':completed,'automatic_base_immutable':True})]:write_json(out/(name+'.json'),value)
    metadata.update(engine_version=3,adaptive_analysis_fps=15,automatic_passes=2,source_key=source_key);write_json(out/'metadata.json',metadata);write_json(out/'status.json',{'state':'complete','stage':'done','done':len(records),'total':len(records),'quality':q});print(json.dumps(q,ensure_ascii=False),flush=True)
if __name__=='__main__':commit()
