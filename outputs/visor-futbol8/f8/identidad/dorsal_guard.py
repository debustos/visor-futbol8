"""Recheck clear local dorsals before trusting inherited track-level identities."""
from collections import defaultdict,Counter
import json

SOURCES={'full_jersey','local_dorsal_recheck','verified_training_reference'}

def attach_readings(records,evidence):
    index={(r.get('frame'),str(b['id'])):b for r in records for b in r['tracks']}
    for entry in evidence:
        for reading in entry.get('readings',[]):
            text=reading.get('text','')
            if not reading.get('localized') or reading.get('source') not in SOURCES or not text.isdigit() or str(int(text))!=text or reading.get('score',0)<.8:continue
            b=index.get((reading.get('frame'),str(entry['track_id'])))
            if b is None or b.get('kit')!='orange':continue
            item={'number':int(text),'score':reading['score'],'frame':reading['frame'],'time':reading['time'],'source':reading['source']}
            observations=b.setdefault('dorsal_observations',[])
            if item not in observations:observations.append(item)

def apply_guard(records):
    contexts=defaultdict(list)
    for r in records:
        for b in r['tracks']:
            if b.get('person_track_id') and b.get('kit')=='orange':contexts[b['person_track_id']].append((r,b))
    changes=[]
    for cid,rows in contexts.items():
        if any(b.get('identity',{}).get('method') in ('manual_review','review_conflict') or b.get('identity',{}).get('anchor_method')=='manual_review' for r,b in rows):continue
        ids={b.get('player_id') for r,b in rows if b.get('player_id')}
        if len(ids)!=1:continue
        current=next(iter(ids));perframe=defaultdict(dict)
        for r,b in rows:
            for v in b.get('dorsal_observations',[]):
                if v['number'] not in {78,5,22,14,7,8,99,11,17,12,30,41,6,16,9}:continue
                key=(v['number'],v['frame']);perframe[v['number']][v['frame']]=max(perframe[v['number']].get(v['frame'],0),v['score'])
        contrary={n:fs for n,fs in perframe.items() if 'orange-'+str(n)!=current and max(fs.values(),default=0)>=.97}
        if not contrary:continue
        ordered=sorted(contrary.items(),key=lambda v:(len(v[1]),sum(v[1].values())),reverse=True);number,frames=ordered[0]
        old_number=int(current.split('-')[-1]);old_frames=perframe.get(old_number,{})
        supported=len(frames)>=2 and sum(frames.values())>=1.6 and len(old_frames)<2 and len(contrary)==1
        pid='orange-'+str(number) if supported else None
        report={'context_id':cid,'before':current,'after':pid,'independent_frames':len(frames),'reason':'local_dorsal_overrides_inherited_identity' if supported else 'contradictory_local_dorsal_identity_suspended','start':rows[0][0]['time'],'end':rows[-1][0]['time'],'samples':len(rows)};changes.append(report)
        for r,b in rows:
            b['player_id']=pid;b['dorsal_guard']=report
            b['identity']={**b.get('identity',{}),'state':'estimated' if pid else 'conflict','locked':bool(pid),'anchor_method':'local_dorsal_guard' if pid else None,'reason':report['reason']}
            raw=b.get('identity_evidence',{});b['identity_evidence']={**raw,'player_id':pid,'identity':{'method':'local_dorsal_guard' if pid else 'dorsal_conflict','state':'accepted' if pid else 'rejected'}}
    # A locally read number must not create two players with the same identity.
    guarded={q['context_id']:q for q in changes if q['after']}
    for cid,report in guarded.items():
        occupied={r.get('frame',r['time']) for r,b in contexts[cid]}
        for other,rows in contexts.items():
            if other==cid or not any(b.get('player_id')==report['after'] and r.get('frame',r['time']) in occupied for r,b in rows):continue
            manual=any(b.get('identity',{}).get('method') in ('manual_review','review_conflict') or b.get('identity',{}).get('anchor_method')=='manual_review' for r,b in rows)
            if manual:
                for r,b in contexts[cid]:
                    b['player_id']=None;b['identity']={**b.get('identity',{}),'state':'conflict','locked':False,'reason':'competing_with_manual_identity'}
                    b['identity_evidence']={'player_id':None,'identity':{'method':'dorsal_conflict','state':'rejected'}}
                report['after']=None;report['reason']='competing_with_manual_identity'
                break
            for r,b in rows:
                b['player_id']=None;b['identity']={**b.get('identity',{}),'state':'conflict','locked':False,'reason':'competing_with_local_dorsal'}
                raw=b.get('identity_evidence',{});b['identity_evidence']={**raw,'player_id':None,'identity':{'method':'dorsal_conflict','state':'rejected'}}
    return {'version':10,'checked_contexts':len(contexts),'changes':changes,'policy':'Local independent dorsal frames override inherited identity; a single clear contradiction suspends identity; manual corrections are preserved.'}

def main():
    import argparse,cv2,re,torch,easyocr
    from pathlib import Path
    from f8.core.runtime_context import ROOT,WORK,CACHE,SOURCE
    from f8.core.io import write_json,iou
    parser=argparse.ArgumentParser();parser.add_argument('--records');parser.add_argument('--output');args=parser.parse_args()
    path=Path(args.records) if args.records else CACHE/'recovery-v5/records-v5.json'
    records=json.loads(path.read_text(encoding='utf8'));ep=ROOT/'automatic/jersey-evidence-v5.json';evidence=json.loads(ep.read_text(encoding='utf8')) if ep.exists() else []
    attach_readings(records,evidence);contexts=defaultdict(list);triggers={}
    for r in records:
        for b in r['tracks']:
            cid=b.get('person_track_id')
            if not cid:continue
            contexts[cid].append((r,b))
            for v in b.get('dorsal_observations',[]):
                if b.get('player_id') and b['player_id']!='orange-'+str(v['number']) and v['score']>=.97:triggers[cid]=v['time']
    print(json.dumps({'stage':'dorsal_guard','conflicting_contexts':len(triggers)}),flush=True)
    if triggers:
        torch.set_num_threads(5);reader=easyocr.Reader(['en'],gpu=False,model_storage_directory=str(WORK/'automatic-probe/ocr-models'),user_network_directory=str(WORK/'automatic-probe/ocr-networks'),verbose=False);cap=cv2.VideoCapture(SOURCE);rechecks=[]
        for i,(cid,t) in enumerate(triggers.items()):
            selected={}
            for offset in (-1,-.5,.5,1,2,3):
                row=min(contexts[cid],key=lambda row:abs(row[0]['time']-(t+offset)));r,b=row
                if abs(r['time']-(t+offset))>.2 or b['box'][3]-b['box'][1]<100:continue
                if any(q is not b and q.get('kit')=='orange' and q.get('box') and iou(q['box'],b['box'])>.2 for q in r['tracks']):continue
                selected[r['frame']]=row
            for r,b in selected.values():
                cap.set(cv2.CAP_PROP_POS_FRAMES,r['frame']);ok,img=cap.read()
                if not ok:continue
                x1,y1,x2,y2=map(round,b['box']);im=img[max(0,y1):y2,max(0,x1):x2];h,w=im.shape[:2]
                if not h or not w:continue
                top=int(h*.08);torso=im[top:int(h*.62)];scale=max(3,min(5,240/max(torso.shape[0],1)));torso=cv2.resize(torso,None,fx=scale,fy=scale)
                for box,text,score in reader.readtext(torso,detail=1,allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',text_threshold=.4,low_text=.25,link_threshold=.25,canvas_size=640,mag_ratio=1):
                    token=re.sub('[^a-zA-Z0-9]','',text);ys=[p[1]/scale+top for p in box];rh=(max(ys)-min(ys))/h;ry=sum(ys)/4/h
                    if token.isdigit() and score>=.8 and .08<=rh<=.3 and .17<ry<.58:
                        v={'text':token,'score':float(score),'time':r['time'],'frame':r['frame'],'localized':True,'source':'local_dorsal_recheck'};rechecks.append({'track_id':b['id'],'readings':[v]})
            print(json.dumps({'stage':'dorsal_guard','done':i+1,'total':len(triggers)}),flush=True)
        cap.release();attach_readings(records,rechecks);write_json(CACHE/'dorsal-guard-rechecks.json',rechecks)
    quality=apply_guard(records);write_json(Path(args.output) if args.output else path,records)
    context_path=CACHE/'recovery-v5/identity-contexts.json'
    if context_path.exists():
        public=json.loads(context_path.read_text(encoding='utf8'));bycid={b.get('person_track_id'):b for r in records for b in r['tracks']}
        for c in public:
            b=bycid.get(c['id'])
            if b:c.update(player_id=b.get('player_id'),anchor_method=b.get('identity',{}).get('anchor_method'),reason=b.get('identity',{}).get('reason'))
        write_json(context_path,public)
    write_json(ROOT/'automatic/dorsal-guard-quality.json',quality);print(json.dumps(quality),flush=True)

if __name__=='__main__':main()
