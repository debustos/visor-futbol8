"""Validate the full-half output and create an audit summary without accuracy claims."""
import json,math
from collections import Counter,defaultdict
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from server import App,ROOT

data=ROOT/'data';meta=json.loads((data/'metadata.json').read_text(encoding='utf8'));status=json.loads((data/'status.json').read_text(encoding='utf8'))
assert status['state']=='complete' and meta['full_source']
records=[r for path in sorted((data/'chunks').glob('*.json')) for r in json.loads(path.read_text(encoding='utf8'))]
assert len(records)==meta['planned_samples']==meta['processed_samples']
assert records[0]['frame']==0 and records[-1]['frame']==meta['source_frames']-1
observations=defaultdict(list);total=0
for i,r in enumerate(records):
    assert r['sample']==i and math.isfinite(r['time'])
    assert abs(r['time']-r['frame']/meta['source_fps'])<.0001
    if i:assert r['time']>records[i-1]['time'] and r['frame']>records[i-1]['frame']
    tids=[b['id'] for b in r['tracks']];assert len(tids)==len(set(tids))
    for b in r['tracks']:
        x1,y1,x2,y2=b['box'];assert all(math.isfinite(v) for v in b['box']) and x2>x1 and y2>y1
        assert 0<=b['confidence']<=1 and b['kit'] in ('orange','yellow','opponent','unknown')
        observations[b['id']].append((r['time'],b));total+=1
fragments=json.loads((data/'fragments.json').read_text(encoding='utf8'));assert len(fragments)==len(observations)==meta['unique_fragments']
risks=[]
for f in fragments:
    obs=observations[f['id']];assert f['samples']==len(obs)
    strong=[(t,b['kit']) for t,b in obs if b['kit_score']>.4 and b['kit'] in ('orange','opponent')]
    changes=[{'time':b[0],'from':a[1],'to':b[1]} for a,b in zip(strong,strong[1:]) if a[1]!=b[1] and b[0]-a[0]<1]
    f['appearance_change_warnings']=changes
    if changes:risks.append({'id':f['id'],'changes':changes})
temporary=data/'fragments.json.tmp';temporary.write_text(json.dumps(fragments,ensure_ascii=False,separators=(',',':')),encoding='utf8');temporary.replace(data/'fragments.json')
lengths=sorted(f['samples']/meta['analysis_fps'] for f in fragments);median=lengths[len(lengths)//2] if len(lengths)%2 else sum(lengths[len(lengths)//2-1:len(lengths)//2+1])/2
checks=['complete processing status','first and final native source frame','all chunks readable','planned sample count','monotonic frame and time indices','timestamps agree with original fps','unique IDs within each sample','finite boxes with positive dimensions','confidence within 0..1','known appearance groups','fragment count and observation count agreement']
app=App();review=app.export();(ROOT/'revision-inicial.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf8')
metrics={'duration_seconds':meta['duration'],'source_frames':meta['source_frames'],'analyzed_samples':len(records),'chunks':len(list((data/'chunks').glob('*.json'))),'runtime_seconds':meta['runtime_seconds'],'unique_fragments':len(fragments),'tracked_observations':total,'median_fragment_sample_seconds':round(median,2),'fragments_with_appearance_change_warning':len(risks),'appearance_warning_note':'Heuristic warning only: color errors also cause changes; not a measured ID-switch rate','identity_assignments':len(review['assignments']),'recorded_confirmed_events':sum(e['status']=='confirmed' for e in review['events']),'automated_identity_or_event_accuracy':'not measured; independent ground truth unavailable','checks_passed':checks}
(ROOT/'validacion-primera.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf8')
(ROOT/'alertas-apariencia.json').write_text(json.dumps(risks,ensure_ascii=False,indent=2),encoding='utf8')
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
images=sorted((data/'audit').glob('*.jpg'))
for offset in range(0,len(images),9):
    group=images[offset:offset+9];sheet=Image.new('RGB',(1920,360*math.ceil(len(group)/3)),(17,20,23))
    for j,path in enumerate(group):
        with Image.open(path) as im:sheet.paste(im.resize((640,360)),((j%3)*640,(j//3)*360))
    sheet.save(ROOT/f'revision-muestras-{offset//9+1}.jpg',quality=91)
print(json.dumps(metrics,ensure_ascii=False),flush=True)
