"""Continuous measured ball sampling, with native player detection and optional adaptive mode."""
from pathlib import Path
from bisect import bisect_left
import argparse,json,time,cv2,numpy as np
from automatic_core import Detector,write_json,select_ball,infer_possession,camera_step,kit,iou
from refine_ball import FootballBall
from pitch_geometry import recover_matrix,marking_evidence
from runtime_context import ROOT,WORK,CACHE,SOURCE

def windows_for(records,temporal,duration):
    spans=[]
    for r in records:
        if r.get('possession'):spans.append((max(0,r['time']-.65),min(duration,r['time']+.65)))
    for e in temporal:
        if e['class'] in ('Goal','Foul','Shots on target','Shots off target','Substitution','Clearance'):spans.append((max(0,e['time']-2.5),min(duration,e['time']+2.5)))
    merged=[]
    for a,b in sorted(spans):
        if merged and a<=merged[-1][1]+.2:merged[-1][1]=max(b,merged[-1][1])
        else:merged.append([a,b])
    return merged

def associate_people(detections,nearby,time):
    tracks=[];used=set()
    for j,d in enumerate(detections):
        options=[]
        for b in nearby['tracks']:
            score=iou(d['box'],b['box'])
            if score>.35:options.append((score,b))
        options.sort(key=lambda v:-v[0]);best=options[0] if options else None
        stable=best and (len(options)==1 or best[0]-options[1][0]>.15) and best[1]['id'] not in used
        b=best[1] if stable else {};tid=b.get('id',f"D{round(time*1000)}-{j}")
        if stable:used.add(tid)
        tracks.append({**d,'id':tid,'kit':d['kit'],'position':d.get('position'),'player_id':b.get('player_id') if d['kit']==b.get('kit') else None,'segment_id':b.get('segment_id'),'identity':b.get('identity',{'state':'unknown'}),'association':'measured_box_unique_iou' if stable else 'unassigned'})
    return tracks

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default=SOURCE);p.add_argument('--fps',type=float,default=10);p.add_argument('--records');p.add_argument('--output');p.add_argument('--adaptive-only',action='store_true');a=p.parse_args();out=ROOT/'automatic';cache=CACHE
    records=json.loads(Path(a.records or cache/'identified-v3.json').read_text(encoding='utf-8-sig'));metadata=json.loads((out/'metadata.json').read_text());temporal=json.loads((out/'temporal-candidates.json').read_text());fps=metadata['source_fps'];duration=metadata['duration'];spans=windows_for(records,temporal,duration) if a.adaptive_only else [[0,duration]]
    targets={r['frame'] for r in records}
    denseframes={round(t*fps) for start,end in spans for t in np.arange(start,end,1/a.fps)}
    targets=sorted(targets|denseframes);base={r['frame']:r for r in records};times=[r['time'] for r in records];ball=FootballBall();people=Detector(WORK/'yolo11s.onnx');cap=cv2.VideoCapture(a.source);frame=-1;last_img=None;last_time=-100;C=None;previous=None;last_search=-100;result=[];views=[];begin=time.monotonic();extra=0;inferred=0
    for i,target in enumerate(targets):
        if target>=round(duration*fps):continue
        while frame<target:
            if not cap.grab():raise RuntimeError(f'Unexpected end at {target}')
            frame+=1
        ok,img=cap.retrieve()
        if not ok:raise RuntimeError(f'Failed frame {target}')
        t=target/fps;original=base.get(target)
        if original:
            r=json.loads(json.dumps(original));C=recover_matrix(r);selected=r.get('ball')
        else:
            idx=min(len(records)-1,bisect_left(times,t));near=min(records[max(0,idx-1):idx+1],key=lambda r:abs(r['time']-t))
            if C is not None and last_img is not None and t-last_time<.25:
                step=camera_step(last_img,img);C=C@step if step is not None else None
            else:C=recover_matrix(near)
            dets=people(img)[0];found=[]
            for d in dets:
                k,score=kit(img,d['box']);d.update(kit=k,kit_score=score)
                x1,y1,x2,y2=d['box'];point=None
                if C is not None:
                    from automatic_core import project
                    pp=project(C,[[(x1+x2)/2,y2]]);point=pp[0].round(4).tolist() if pp is not None and -8<=pp[0,0]<=108 and -8<=pp[0,1]<=108 and y2<1076 else None
                d['position']=point
                if k in ('orange','keeper','opponent') and y2-y1>=30:found.append(d)
            tracks=associate_people(found,near,t)
            r={'frame':target,'time':round(t,4),'tracks':tracks,'calibration':near['calibration'],'dense':True};extra+=1;selected=None
        if target in denseframes:
            region=None
            if previous and t-previous['time']<=.3:
                x,y=previous['center'];x=int(np.clip(x-320,0,img.shape[1]-640));y=int(np.clip(y-320,0,img.shape[0]-640));region=[(x,y,x+640,y+640)]
            candidates=ball(img,region) if region or t-last_search>=.3 else []
            if not region and candidates:last_search=t
            measured=select_ball(candidates,t,previous,C,img) if candidates else None;inferred+=1
            r['ball_candidates']=[*candidates,*([original['ball']] if original and original.get('ball') else [])]
            if measured:selected=measured
        if selected:previous=selected
        r['ball']=selected;r['possession']=infer_possession(r);result.append(r)
        if original and (not views or t-views[-1]['time']>=3.95):views.append({'time':round(t,4),'frame':target,**marking_evidence(img,C)})
        last_img=img;last_time=t
        if i%250==0 or i==len(targets)-1:
            status={'state':'processing','stage':'dense_ball','done':i+1,'total':len(targets),'dense_frames':extra,'ball_samples':sum(r['ball'] is not None for r in result),'seconds':round(time.monotonic()-begin,1)};write_json(out/'ball-status.json',status);print(json.dumps(status),flush=True)
    cap.release();write_json(Path(a.output or cache/'dense-v3.json'),result);write_json(out/'geometry-views.json',views)
    q={'version':6,'base_samples':len(records),'adaptive_samples':extra,'total_samples':len(result),'target_fps':a.fps,'windows':spans,'window_seconds':round(sum(b-a for a,b in spans),2),'ball_observed_samples':sum(r['ball'] is not None for r in result),'contact_samples':sum(r['possession'] is not None for r in result),'ball_detector_calls':inferred,'run_seconds':round(time.monotonic()-begin,1),'policy':'Continuous measured ball sampling across the complete video; measured person boxes, optional pitch projection and unique association to nearby identities; no invented ball points.'};write_json(out/'dense-ball-quality.json',q);write_json(out/'ball-status.json',{'state':'complete',**q});print(json.dumps(q),flush=True)
if __name__=='__main__':main()
