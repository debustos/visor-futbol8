"""Candidate-run identity repair, reusing native 5fps and adaptive 15fps detections."""
from pathlib import Path
from collections import defaultdict,Counter
import sys,json,time,copy,re,hashlib,numpy as np
from f8.core.runtime_context import ROOT as viewer,WORK as work,CACHE as cache,MASTER
target=cache/'recovery-v5';target.mkdir(parents=True,exist_ok=True)
from f8.core.io import write_json;from f8.acciones.contactos import infer_possession
from f8.identidad.visual_memory_v5 import reconstruct
from f8.acciones.sequence_engine import sequence_actions
from f8.publicacion.analytics_v3 import profiles_for
from f8.publicacion.presence_engine import presence_lineup
from f8.campo.pitch_geometry import attach_geometry
roster=json.loads((viewer/'plantilla.json').read_text())['players'];names={re.sub('[^a-z]','',p['nickname'].lower()):p['jersey_number'] for p in roster if len(p['nickname'])>=4}
evidence=json.loads((viewer/'automatic/jersey-evidence.json').read_text());text= json.loads((cache/'jersey-text-cache.json').read_text()) if (cache/'jersey-text-cache.json').exists() else []
bytrack={e['track_id']:copy.deepcopy(e) for e in evidence};new=defaultdict(list)
from difflib import SequenceMatcher
for entry in text:
    for reading in entry['results']:
        token=reading['text'];name=names.get(token.lower())
        if name is None and len(token)>=4 and not any(ch.isdigit() for ch in token):
            order=sorted([(SequenceMatcher(None,token.lower(),n).ratio(),number) for n,number in names.items()],reverse=True)
            if order and order[0][0]>=.84 and (len(order)<2 or order[0][0]-order[1][0]>=.15):name=order[0][1]
        if name and reading['score']>=.40:
            # Names corroborate identity but cannot manufacture a pixel number reading.
            new[entry['track_id']].append({'frame':entry['frame'],'time':entry['time'],'text':str(name),'score':reading['score'],'crop':entry['file'],'localized':True,'source':'jersey_name','raw_text':token})
        if token.isdigit() and token in {str(p['jersey_number']) for p in roster} and .08<=reading['relative_height']<=.3 and .17<reading['relative_y']<.58 and reading['score']>=.75:
            new[entry['track_id']].append({'frame':entry['frame'],'time':entry['time'],'text':token,'score':reading['score'],'crop':entry['file'],'localized':True,'source':'full_jersey','text_box':reading['box']})
summaries=json.loads((cache/'summaries.json').read_text());crop_context={c['file']:{**c,'track_id':s['id']} for s in summaries for c in s['ocr_candidates']}
from f8.identidad.jersey_font import proposals
font=proposals(cache/'crops',MASTER/'training/jersey-font-model.npz');write_json(target/'font-proposals.json',font)
for proposal in font:
    c=crop_context.get(proposal['file'])
    if c is None:continue
    reads=bytrack.get(c['track_id'],{}).get('readings',[])
    corroborated=any(r['frame']==c['frame'] and r['text']==str(proposal['number']) and r['score']>=.40 for r in reads)
    if not corroborated and not(proposal['similarity']>=.85 and proposal['margin']>=.18):continue
    new[c['track_id']].append({'frame':c['frame'],'time':c['time'],'text':str(proposal['number']),'score':proposal['similarity'],'crop':c['file'],'localized':True,'source':'font_silhouette','font_margin':proposal['margin']})
# Training references are restricted to the exact source video.
verified=[]
metadata=json.loads((viewer/'automatic/metadata.json').read_text());source=Path(metadata['source']);source_stat=source.stat();fingerprint={'source':str(source.resolve()),'size':source_stat.st_size,'mtime_ns':source_stat.st_mtime_ns,'scan_sha256':hashlib.sha256((cache/'scan.json').read_bytes()).hexdigest()}
for reference_file in (MASTER/'training').glob('jersey-references-*.json'):
    reference=json.loads(reference_file.read_text())
    if reference.get('source_fingerprint')==fingerprint:verified.extend(reference['references'])
for ref in verified:
    new[ref['track_id']].append({'frame':ref['frame'],'time':ref['time'],'text':str(ref['verified_number']),'score':.999,'crop':ref['crop'],'localized':True,'source':'verified_training_reference'})
for tid,readings in new.items():
    item=bytrack.setdefault(tid,{'track_id':tid,'readings':[]});item['readings']+=readings
    # Full two-digit readings supersede a clipped digit across the same cached track.
    longer=Counter(r['text'] for r in readings if len(r['text'])==2 and r['score']>=.75);longframes={n:{r['frame'] for r in readings if r['text']==n} for n in longer};confirmed_long=[n for n,fs in longframes.items() if len(fs)>=2 or any(r['text']==n and r['source']=='verified_training_reference' for r in readings)]
    name_numbers={r['text'] for r in readings if r['source']=='jersey_name'}
    item['readings']=[r for r in item['readings'] if not (len(r['text'])==1 and any(r['text'] in n for n in confirmed_long) and r['text'] not in name_numbers)]
# Single-digit reads in cropped recognizer fallbacks are not full-number anchors.
for item in bytrack.values():
    item['readings']=[r for r in item['readings'] if not(len(r['text'])==1 and not r.get('localized'))]
evidence=list(bytrack.values());write_json(target/'jersey-evidence-v5.json',evidence)
records=json.loads((cache/'scan.json').read_text());rows=json.loads((cache/'feature-rows.json').read_text());features=np.load(cache/'embeddings.npy');physical=np.load(cache/'physical-features.npy');balls=json.loads((cache/'ball-refinement.json').read_text());started=time.monotonic()
for r,b in zip(records,balls):r['ball']=b['ball'];r['possession']=infer_possession(r)
reviews=[]
if (viewer/'revisiones.sqlite3').exists() and (viewer/'automatic/review-manifest.json').exists():
    import sqlite3,hashlib
    key=json.loads((viewer/'automatic/review-manifest.json').read_text())['source_key'];expected=hashlib.sha256((str(source.resolve())+str(source_stat.st_size)+str(source_stat.st_mtime_ns)+hashlib.sha256((cache/'scan.json').read_bytes()).hexdigest()+'v3').encode()).hexdigest()[:24]
    if key==expected:
        with sqlite3.connect(viewer/'revisiones.sqlite3') as db:
            if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='automatic_reviews'").fetchone():reviews=[json.loads(r[0]) for r in db.execute('SELECT payload FROM automatic_reviews WHERE source_key=?',(key,)) if json.loads(r[0]).get('category')=='identity']
records,segments,memory,q=reconstruct(records,rows,features,evidence,{p['jersey_number']:p for p in roster},physical,reviews)
q['visually_verified_training_references']=len(verified);write_json(target/'base-v5.json',records);write_json(cache/'identified-v5.json',records);write_json(target/'identity-segments.json',segments);write_json(target/'visual-memory.json',memory);write_json(target/'memory-quality.json',q);print(json.dumps({k:v for k,v in q.items() if k!='cuts'}),flush=True)
# Transfer the repaired identity to measured dense boxes at their original times.
dense=json.loads((cache/'dense-v3.json').read_text());times=np.array([r['time'] for r in records]);matched=0
for r in dense:
    j=int(np.argmin(np.abs(times-r['time'])));base=records[j];lookup={str(b['id']):b for b in base['tracks']}
    for b in r['tracks']:
        original=lookup.get(str(b['id']))
        if original is None:
            from f8.core.io import iou
            candidates=sorted([(iou(b['box'],a['box']),a) for a in base['tracks'] if a['kit']==b['kit']],key=lambda v:-v[0])
            if candidates and candidates[0][0]>.55 and (len(candidates)==1 or candidates[0][0]-candidates[1][0]>.15):original=candidates[0][1]
        b['player_id']=original.get('player_id') if original and b['kit'] in ('orange','keeper') else None;b['segment_id']=original.get('segment_id') if original else None;b['identity']=copy.deepcopy(original.get('identity',{})) if original else {'method':'unknown','state':'unknown'}
        matched+=int(bool(b['player_id']))
    claims=defaultdict(list)
    for b in r['tracks']:
        if b.get('player_id'):claims[b['player_id']].append(b)
    for pid,bs in claims.items():
        if len(bs)>1:
            keep=max(bs,key=lambda b:b['confidence'])
            for b in bs:
                if b is not keep:b['player_id']=None;b['identity']['state']='conflict'
    r['possession']=infer_possession(r)
views=json.loads((viewer/'automatic/geometry-views.json').read_text());attach_geometry(dense,views);temporal=json.loads((viewer/'automatic/temporal-candidates.json').read_text());actions,sequence=sequence_actions(dense,temporal,short_contacts=True);metadata=json.loads((viewer/'automatic/metadata.json').read_text());profiles=profiles_for(dense,actions,roster,metadata['duration']);lineup=presence_lineup(dense)
for name,value in [('records-v5',dense),('profiles',profiles),('actions',actions),('lineup',lineup),('sequence-quality',sequence)]:write_json(target/(name+'.json'),value)
report={'version':5,'new_text_images':len(text),'new_text_anchors':sum(len(v) for v in new.values()),'visually_verified_training_references':len(verified),'name_anchors':sum(r['source']=='jersey_name' for vs in new.values() for r in vs),'identified_observations':sum(bool(b.get('player_id')) for r in dense for b in r['tracks']),'identities':sum(p['samples']>0 for p in profiles),'observed_seconds':{str(p['jersey_number']):p['visible_seconds'] for p in profiles},'actions':dict(Counter((e['kind'],e['state']) for e in actions)) if False else {k:dict(Counter(e['state'] for e in actions if e['kind']==k)) for k in {e['kind'] for e in actions}},'sequence':sequence,'run_seconds':round(time.monotonic()-started,2)};write_json(target/'candidate-quality.json',report);print(json.dumps(report),flush=True)
