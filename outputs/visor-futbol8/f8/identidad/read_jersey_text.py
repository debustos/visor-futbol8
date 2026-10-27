"""Read full jersey text with digit localization and roster-name corroboration."""
from pathlib import Path
from collections import defaultdict
import json,time,re,sys,hashlib,torch,easyocr,cv2
from f8.core.runtime_context import ROOT as viewer,WORK as work,CACHE as cache
target=cache;target.mkdir(parents=True,exist_ok=True)
from f8.core.io import write_json
roster=json.loads((viewer/'plantilla.json').read_text())['players'];summaries=json.loads((cache/'summaries.json').read_text());candidates={c['file']:{**c,'track_id':s['id']} for s in summaries for c in s['ocr_candidates']};torch.set_num_threads(5)
reader=easyocr.Reader(['en'],gpu=False,detector=True,model_storage_directory=str(work/'automatic-probe/ocr-models'),user_network_directory=str(work/'automatic-probe/ocr-networks'),verbose=False)
results=defaultdict(list);started=time.monotonic()
existing=target/'jersey-text-cache.json'
source=Path(json.loads((viewer/'automatic/metadata.json').read_text())['source']);source_stat=source.stat();fingerprint={'source':str(source.resolve()),'size':source_stat.st_size,'mtime_ns':source_stat.st_mtime_ns,'scan_sha256':hashlib.sha256((cache/'scan.json').read_bytes()).hexdigest()}
context=cache/'jersey-text-source.json'
if existing.exists() and context.exists() and json.loads(context.read_text())==fingerprint:
    for entry in json.loads(existing.read_text()):results[entry['file']]=entry['results']
names={re.sub('[^a-z]','',p['nickname'].lower()):p['jersey_number'] for p in roster if len(re.sub('[^a-z]','',p['nickname'].lower()))>=4}
for i,(file,c) in enumerate(sorted(candidates.items(),key=lambda v:v[1]['frame'])):
    if file in results:continue
    image=cv2.imread(str(cache/'crops'/file));height,width=image.shape[:2];top=int(height*.08);bottom=int(height*.62);torso=image[top:bottom];scale=max(3,min(5,240/max(torso.shape[0],1)));torso=cv2.resize(torso,None,fx=scale,fy=scale)
    found=reader.readtext(torso,detail=1,allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',text_threshold=.40,low_text=.25,link_threshold=.25,canvas_size=640,mag_ratio=1)
    rows=[]
    for box,text,score in found:
        cleaned=re.sub('[^a-zA-Z0-9]','',text);center_y=sum(p[1] for p in box)/4/scale+top;xs=[p[0]/scale for p in box];ys=[p[1]/scale+top for p in box];kind='number' if cleaned.isdigit() else 'name'
        rows.append({'text':cleaned,'score':round(float(score),4),'kind':kind,'box':[min(xs),min(ys),max(xs),max(ys)],'relative_y':round(center_y/height,3),'relative_height':round((max(ys)-min(ys))/height,3),'name_number':names.get(cleaned.lower())})
    results[file]=rows
    if i%25==0 or i==len(candidates)-1:
        saved=[{'file':f,**candidates[f],'results':rows} for f,rows in results.items()];write_json(existing,saved);print(json.dumps({'stage':'full_jersey_text','done':i+1,'total':len(candidates),'seconds':round(time.monotonic()-started,1),'numbers':sum(r['kind']=='number' for rs in results.values() for r in rs),'names':sum(bool(r['name_number']) for rs in results.values() for r in rs)}),flush=True)
write_json(existing,[{'file':f,**candidates[f],'results':rows} for f,rows in results.items()]);write_json(context,fingerprint);print('complete',flush=True)
