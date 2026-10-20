"""Commit v5 automatic results and a review queue without altering prior manual records."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import json,hashlib,os
from automatic_core import write_json,infer_possession
from pitch_geometry import attach_geometry
from sequence_engine import sequence_actions
from presence_engine import presence_lineup
from analytics_v3 import profiles_for
from runtime_context import ROOT,WORK,CACHE,SOURCE
from trajectory_identity import stabilize

def commit():
    out=ROOT/'automatic';cache=CACHE;candidate=cache/'recovery-v5';metadata=json.loads((out/'metadata.json').read_text(encoding='utf8'));records=json.loads(Path(os.environ.get('FOOTBALL_RECORDS_FILE',str(candidate/'records-v5.json'))).read_text(encoding='utf-8-sig'));role_rejected=0
    segments=json.loads((candidate/'identity-segments.json').read_text(encoding='utf8'));memory=json.loads((candidate/'memory-quality.json').read_text(encoding='utf8'))
    if any(b.get('kit') in ('orange','keeper') and not b.get('person_track_id') for r in records for b in r['tracks']):
        contexts,context_quality=stabilize(records,segments,memory.get('cuts',[]))
        write_json(candidate/'identity-contexts.json',contexts);write_json(candidate/'identity-context-quality.json',context_quality)
    else:
        context_quality=json.loads((candidate/'identity-context-quality.json').read_text(encoding='utf8')) if (candidate/'identity-context-quality.json').exists() else {}
    for r in records:
        for b in r['tracks']:
            pid=b.get('player_id')
            if pid and ((b['kit']=='keeper' and pid!='orange-1') or (b['kit']=='orange' and pid=='orange-1') or b['kit'] not in ('orange','keeper')):
                b['player_id']=None;b['identity']={'state':'conflict','method':'uniform_role_conflict'};role_rejected+=1
        r['possession']=infer_possession(r)
    views=json.loads((out/'geometry-views.json').read_text(encoding='utf8'));geometry=attach_geometry(records,views);temporal=json.loads((out/'temporal-candidates.json').read_text(encoding='utf8'));visual_quality=json.loads((out/'visual-shot-quality.json').read_text(encoding='utf8')) if (out/'visual-shot-quality.json').exists() else {};visual_valid=visual_quality.get('source_key')==metadata.get('source_key') and visual_quality.get('source')==SOURCE;visual=json.loads((out/'visual-shot-candidates.json').read_text(encoding='utf8')) if visual_valid and (out/'visual-shot-candidates.json').exists() else [];actions,sequence=sequence_actions(records,temporal+visual,short_contacts=True);lineup=presence_lineup(records);roster=json.loads((ROOT/'plantilla.json').read_text(encoding='utf8'))['players'];profiles=profiles_for(records,actions,roster,metadata['duration']);segments=json.loads((candidate/'identity-segments.json').read_text(encoding='utf8'));memory=json.loads((candidate/'memory-quality.json').read_text(encoding='utf8'));dense=json.loads((out/'dense-ball-quality.json').read_text(encoding='utf8'));queue=[]
    source=Path(metadata['source']);stat=source.stat();source_key=hashlib.sha256((str(source.resolve())+str(stat.st_size)+str(stat.st_mtime_ns)+hashlib.sha256((cache/'scan.json').read_bytes()).hexdigest()+'v3').encode()).hexdigest()[:24]
    # Keep reviewed legacy proposals addressable after segment boundaries change.
    previous_queue=json.loads((out/'uncertainties.json').read_text(encoding='utf8')) if (out/'uncertainties.json').exists() else []
    previous_actions=json.loads((out/'actions.json').read_text(encoding='utf8')) if (out/'actions.json').exists() else []
    decisions={}
    if (ROOT/'revisiones.sqlite3').exists():
        import sqlite3
        with sqlite3.connect(ROOT/'revisiones.sqlite3') as db:
            if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='automatic_reviews'").fetchone():decisions={r[0]:json.loads(r[1]) for r in db.execute('SELECT item_id,payload FROM automatic_reviews WHERE source_key=?',(source_key,))}
    for e in previous_actions:
        if e['id'] in decisions:
            # A reviewed reception keeps its ID when denser sampling shifts release.
            rt=e.get('sequence',{}).get('reception_time')
            actions=[q for q in actions if q['id']==e['id'] or not(q['kind']==e['kind'] and q.get('source_track')==e.get('source_track') and q.get('target_track')==e.get('target_track') and rt is not None and abs(q.get('sequence',{}).get('reception_time',-100)-rt)<.45)]
            if not any(q['id']==e['id'] for q in actions):actions.append(e)
    profiles=profiles_for(records,actions,roster,metadata['duration'])
    contexts=json.loads((candidate/'identity-contexts.json').read_text(encoding='utf8'))
    for c in contexts:
        pid=c['player_id'];near_event=any(e.get('sequence',{}).get('source_context_id')==c['id'] or (str(e.get('source_track')) in c['raw_track_ids'] and c['start']<=e['time']<=c['end']) for e in actions)
        if not pid and c['end']-c['start']<.2 and not near_event:continue
        raw=c['raw_track_ids'][0];tid=int(raw) if raw.isdigit() else raw
        queue.append({'id':'identity-'+c['id'],'category':'identity','priority':1 if near_event else 2 if not pid else 4,'track_id':tid,'context_id':c['id'],'segment_id':c['id'],'time':c['start'],'start':c['start'],'end':c['end'],'evidence_start':max(0,c['start']-.5),'evidence_end':min(metadata['duration'],c['end']+.5),'player_id':pid,'candidate_player_id':c.get('candidate_player_id'),'reason':'Identidad fijada para toda la trayectoria; revisar evidencia' if pid else 'Trayectoria sin identidad aceptada; propuestas conservadas para revisión','method':c.get('anchor_method') or 'trajectory_context','proposal':None})
    for e in actions:queue.append({**e,'category':'event','priority':1 if e['state']=='candidate' else 2,'reason':e.get('reason','Acción estimada: revisar contacto, intención y receptor')})
    queue.append({'id':'lineup-initial','category':'lineup','priority':1,'time':0,'evidence_start':0,'evidence_end':45,'players':lineup['identified_candidates'],'reason':'Comprobar los ocho titulares; candidatos incompletos'})
    for i,s in enumerate(lineup['substitutions']):
        s['id']=f'substitution-{i}-{s["time"]:.3f}';queue.append({**s,'category':'substitution','priority':1,'reason':'Cambio propuesto por cruces de banda y presencia sostenida'})
    for i,a in enumerate(lineup['visibility_alerts']):queue.append({**a,'id':f'presence-alert-{i}-{a["time"]:.3f}','category':'substitution','priority':3,'in_id':a['player_id'],'out_id':None})
    for view in views:
        start=max(0,view['time']-2);end=min(metadata['duration'],view['time']+2)
        queue.append({'id':f'geometry-{view["frame"]}','category':'geometry','priority':2 if view['state'] in ('rejected','unavailable') else 4,'time':view['time'],'start':start,'end':end,'evidence_start':start,'evidence_end':end,'reason':view['reason'],'geometry':view})
    known_ids={q['id'] for q in queue}
    queue.extend(q for q in previous_queue if q['id'] in decisions and q['id'] not in known_ids)
    queue.sort(key=lambda q:(q['priority'],q['time'],q['id']));completed=datetime.now(timezone.utc).isoformat()
    bank=json.loads((out/'reference-bank-quality.json').read_text(encoding='utf8')) if (out/'reference-bank-quality.json').exists() else {}
    bank_valid=bank.get('source_fingerprint',{})=={'source':str(source.resolve()),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'scan_sha256':hashlib.sha256((cache/'scan.json').read_bytes()).hexdigest()}
    far=json.loads((out/'far-identity-quality.json').read_text(encoding='utf8')) if (out/'far-identity-quality.json').exists() else {}
    far_valid=bank_valid and far.get('source_fingerprint')==bank.get('source_fingerprint')
    version=9 if far_valid else 8 if bank_valid else 7
    native=json.loads((out/'native-ball-quality.json').read_text(encoding='utf8')) if (out/'native-ball-quality.json').exists() else {};native_valid=native.get('source_key')==source_key and native.get('source')==SOURCE
    q={'version':version,'action_engine_version':11,'native_ball':native if native_valid else {},'visual_shots':visual_quality if visual_valid else {},'dorsal_guard':json.loads((out/'dorsal-guard-quality.json').read_text(encoding='utf8')) if (out/'dorsal-guard-quality.json').exists() else {},'far_identity':far if far_valid else {},'reference_bank':bank if bank_valid else {},'identity_context':context_quality,'role_claims_rejected':role_rejected,'sampled_frames':len(records),'base_frames':dense['base_samples'],'adaptive_frames':dense['adaptive_samples'],'ball_visible_frames':sum(r['ball'] is not None for r in records),'possession_frames':sum(r.get('possession') is not None for r in records),'identified_players':sum(p['samples']>0 for p in profiles),'identified_player_observations':sum(p['samples'] for p in profiles),'duplicate_claims_rejected':memory['duplicate_claims_rejected'],'automatic_action_estimates':len(actions),'estimated_actions':sum(e['state']=='estimated' for e in actions),'candidate_actions':sum(e['state']=='candidate' for e in actions),'manual_annotation_inputs':memory.get('reviewed_reference_inputs',0),'visually_verified_training_references':memory.get('visually_verified_training_references',0),'review_queue_items':len(queue),'probable_substitutions':len(lineup['substitutions']),'geometry':'F8 marking evidence and camera update; relative plane remains approximate','completed_at_utc':completed,'memory':{k:v for k,v in memory.items() if k!='cuts'},'sequence':sequence,'geometry_quality':geometry,'scope':'Automatic partial reconstruction with reviewable uncertainty. No certified full-match totals.'}
    for name in ('identity-segments','visual-memory','memory-quality','jersey-evidence-v5','candidate-quality','identity-contexts','identity-context-quality'):
        write_json(out/(name+'.json'),json.loads((candidate/(name+'.json')).read_text(encoding='utf8')))
    for minute in sorted({int(r['time']//60) for r in records}):write_json(out/'chunks'/f'{minute:03}.json',[r for r in records if int(r['time']//60)==minute])
    for name,value in [('profiles',profiles),('actions',actions),('lineup',lineup),('quality',q),('uncertainties',queue),('geometry-quality',geometry),('sequence-quality',sequence),('review-manifest',{'version':7,'source_key':source_key,'source':str(source),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'completed_at_utc':completed,'automatic_base_immutable':True})]:write_json(out/(name+'.json'),value)
    metadata.update(engine_version=version,adaptive_analysis_fps=dense.get('target_fps',10),automatic_passes=3 if bank_valid else 2,source_key=source_key);write_json(out/'metadata.json',metadata);write_json(out/'status.json',{'state':'complete','stage':'done','done':len(records),'total':len(records),'quality':q});print(json.dumps(q,ensure_ascii=False),flush=True)
if __name__=='__main__':commit()
