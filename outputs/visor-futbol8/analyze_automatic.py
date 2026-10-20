"""One command, no player labels: detect, track, OCR, identify, project, estimate actions."""
from __future__ import annotations
import argparse,json,math,os,time,hashlib
from collections import Counter,defaultdict
from pathlib import Path
import cv2,numpy as np
from automatic_core import *
from reference_sampling import retain_ocr_candidates
from automatic_fusion import enrich,substitutions
from identity_stitch import stitch
from ball_actions import trajectory_actions

from runtime_context import ROOT,WORK,CACHE,SOURCE;os.environ['YOLO_CONFIG_DIR']=str(WORK/'yolo-config')

def read_image_at(cap,second):
    cap.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,img=cap.read()
    if not ok:raise RuntimeError(f'No frame at {second}')
    return img

class UnavailableProjection:
    def __call__(self,img):return None,{'state':'unavailable','reason':'No supported field projection for this video'}

def make_registrar(cap,calibration):
    if calibration.get('matrix') is None:return UnavailableProjection()
    ref=read_image_at(cap,0);C=np.asarray(calibration['matrix']);initial=Registrar([ref],[np.eye(3)],C);images=[ref];transforms=[np.eye(3)]
    duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/cap.get(cv2.CAP_PROP_FPS)
    for t in (60,300,994,1200):
        if t>=duration:continue
        img=read_image_at(cap,t);_,info=initial(img)
        if info['state']!='unavailable':images.append(img);transforms.append(info['global_matrix'])
    return Registrar(images,transforms,C)

def candidate_quality(img,box):
    x1,y1,x2,y2=box;h=y2-y1;part=crop(img,box,.15,.52,.22,.82)
    if h<60 or not part.size:return 0
    hsv=cv2.cvtColor(part,cv2.COLOR_BGR2HSV);hu,sa,va=cv2.split(hsv);dark=(hu>=0)&(hu<25)&(sa>65)&(va<140);fraction=float(np.mean(dark))
    if not .01<fraction<.48:return 0
    sharp=float(cv2.Laplacian(cv2.cvtColor(part,cv2.COLOR_BGR2GRAY),cv2.CV_32F).var())
    return h*min(math.sqrt(sharp+1),30)*min(fraction,.15)

def scan(args,output,intermediate):
    cap=cv2.VideoCapture(args.source)
    if not cap.isOpened():raise RuntimeError(args.source)
    fps=cap.get(cv2.CAP_PROP_FPS);total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));duration=total/fps;end=duration if args.end is None else min(args.end,duration);start=args.start
    calibration=json.loads((ROOT/'pitch-calibration.json').read_text());registrar=make_registrar(cap,calibration)
    detector=Detector(WORK/'yolo11s.onnx');encoder=Encoder(WORK/'yolo26n-reid.onnx');tracker=MemoryTracker();records=[];features=[];feature_rows=[];OCR=defaultdict(list)
    targets=sorted({round(t*fps) for t in np.arange(start,end,1/args.fps)}|{min(total-1,round(end*fps)-1)});current=targets[0];cap.set(cv2.CAP_PROP_POS_FRAMES,current);C=None;registration={};last_registration=-10;last_embedding=-10;last_ball=None;previous_image=None;started=time.monotonic()
    for sample,target in enumerate(targets):
        while current<target:
            if not cap.grab():raise RuntimeError(f'Decode ended at {current}')
            current+=1
        ok,img=cap.read();current+=1
        if not ok:raise RuntimeError(f'Cannot decode {target}')
        t=target/fps
        if previous_image is not None and C is not None:
            step=camera_step(previous_image,img)
            if step is not None:C=C@step
            else:C=None
        if t-last_registration>=1.95 or C is None:
            absolute,info=registrar(img)
            if absolute is not None:C=absolute;registration=info
            elif C is None:registration=info
            last_registration=t
        previous_image=img
        found=detector(img);dets=[]
        for p in found[0]:
            box=p['box'];x1,y1,x2,y2=box
            if x2-x1<9 or y2-y1<30:continue
            k,score=kit(img,box);foot=[(x1+x2)/2,y2];point=project(C,[foot]);pos=point[0].tolist() if point is not None and -5<=point[0,0]<=105 and -5<=point[0,1]<=105 and y2<1076 else None
            if point is not None and not(-8<=point[0,0]<=108 and -8<=point[0,1]<=108):continue
            if pos is None:
                surrounding=crop(img,[foot[0]-10,foot[1]-2,foot[0]+10,foot[1]+10]);hsv=cv2.cvtColor(surrounding,cv2.COLOR_BGR2HSV) if surrounding.size else None
                if hsv is not None and np.mean((hsv[:,:,0]>30)&(hsv[:,:,0]<95))<.15:continue
            dets.append({**p,'kit':k,'kit_score':score,'position':pos,'appearance':appearance(img,box),'embedding':None})
        embedding_frame=t-last_embedding>=.45
        if embedding_frame:
            embedded=encoder(img,[d['box'] for d in dets]);last_embedding=t
            for d,f in zip(dets,embedded):d['embedding']=f
        tracked=tracker.update(dets,t,C);public=[]
        for d in tracked:
            tid=d['id'];summary=tracker.summary[tid]
            public.append({k:(np.asarray(d[k]).round(4).tolist() if k=='position' and d[k] is not None else d[k]) for k in ('id','box','confidence','kit','kit_score','position')})
            if embedding_frame and d['embedding'] is not None:
                index=len(features);features.append(d['embedding']);feature_rows.append({'index':index,'track_id':tid,'time':round(t,4),'frame':target});summary['embedding_rows'].append(index)
            if d['kit']=='orange' and sample%2==0:
                quality=candidate_quality(img,d['box'])
                if quality and all(abs(c['time']-t)>.32 for c in OCR[tid]):
                    candidates=OCR[tid]
                    name=f'{target:05}-{tid}.jpg';candidate={'file':name,'frame':target,'time':round(t,4),'quality':round(quality,3),'height':round(d['box'][3]-d['box'][1],1)}
                    kept=retain_ocr_candidates(candidates+[candidate])
                    if any(c['file']==name for c in kept):
                        part=crop(img,d['box']);cv2.imwrite(str(intermediate/'crops'/name),part,[cv2.IMWRITE_JPEG_QUALITY,96])
                        retained={c['file'] for c in kept}
                        for old in candidates:
                            if old['file'] not in retained:(intermediate/'crops'/old['file']).unlink(missing_ok=True)
                        OCR[tid]=kept
        ball=select_ball(found[32],t,last_ball,C,img)
        if ball:last_ball=ball
        record={'frame':target,'time':round(t,4),'tracks':public,'ball':ball,'calibration':{k:v for k,v in registration.items() if k!='global_matrix'}};record['possession']=infer_possession(record);records.append(record)
        if sample%100==0 or sample==len(targets)-1:
            status={'state':'processing','stage':'detection','done':sample+1,'total':len(targets),'source_seconds':round(t,2),'elapsed':round(time.monotonic()-started,1)};write_json(output/'status.json',status);print(json.dumps(status),flush=True)
        if sample%round(args.fps*60)==0 or sample==len(targets)-1:
            audit=img.copy()
            for d in public:
                x1,y1,x2,y2=map(round,d['box']);color={'orange':(0,150,255),'keeper':(0,255,255),'opponent':(230,170,0),'referee':(0,230,140)}.get(d['kit'],(200,200,200));cv2.rectangle(audit,(x1,y1),(x2,y2),color,2);cv2.putText(audit,f"A{d['id']} {d['kit']}",(x1,max(24,y1-4)),cv2.FONT_HERSHEY_SIMPLEX,.6,color,2)
            if ball:cv2.circle(audit,tuple(map(round,ball['center'])),12,(0,0,255),3)
            cv2.imwrite(str(output/'audit'/f'{target:05}.jpg'),cv2.resize(audit,(1280,720)))
    cap.release()
    metadata={'source':args.source,'source_fps':fps,'duration':duration,'first_analyzed_frame':targets[0],'last_analyzed_frame':targets[-1],'analysis_fps':args.fps,'samples':len(records),'full_source':targets[0]==0 and targets[-1]==total-1,'model':'YOLO11s ONNX','execution_provider':detector.session.get_providers()[0],'appearance_embedding_interval_seconds':.45,'max_dorsal_crops_per_track':24,'tracklets':len(tracker.summary),'identity_input':'automatic jersey OCR and appearance; no manual review database read','calibration':calibration,'run_seconds_detection':round(time.monotonic()-started,2)}
    summaries=[{**s,'kit_counts':dict(s['kit_counts']),'ocr_candidates':OCR[s['id']]} for s in tracker.summary.values()]
    write_json(intermediate/'scan.json',records);write_json(intermediate/'summaries.json',summaries);write_json(intermediate/'feature-rows.json',feature_rows);np.save(intermediate/'embeddings.npy',np.array(features,np.float32));write_json(output/'metadata.json',metadata)
    return records,summaries,feature_rows,np.array(features,np.float32),metadata

def read_dorsals(summaries,output,intermediate,roster):
    import torch,easyocr
    torch.set_num_threads(6)
    reader=easyocr.Reader(['en'],gpu=False,detector=True,model_storage_directory=str(WORK/'automatic-probe'/'ocr-models'),user_network_directory=str(WORK/'automatic-probe'/'ocr-networks'),verbose=False)
    log=[];labels={};total=sum(bool(s['ocr_candidates']) for s in summaries);done=0
    for s in summaries:
        readings=[]
        if not s['ocr_candidates']:continue
        for candidate in sorted(s['ocr_candidates'],key=lambda c:c['quality'],reverse=True):
            img=cv2.imread(str(intermediate/'crops'/candidate['file']))
            if img is None:continue
            torso=crop(img,[0,0,img.shape[1],img.shape[0]],.10,.60,0,1)
            if torso.size:
                torso=cv2.resize(torso,None,fx=3,fy=3)
                detected=reader.readtext(torso,allowlist='0123456789',detail=1,text_threshold=.45,low_text=.25,link_threshold=.25,canvas_size=512,mag_ratio=1)
                for result in detected:readings.append({'frame':candidate['frame'],'time':candidate['time'],'text':result[1],'score':round(float(result[2]),4),'crop':candidate['file'],'localized':True})
            region=number_region(img)
            regions=[region] if region is not None else []
            regions.append(crop(img,[0,0,img.shape[1],img.shape[0]],.15,.57,.12,.88))
            regions.append(crop(img,[0,0,img.shape[1],img.shape[0]],.15,.50,.40,.80))
            for torso in regions:
                if torso is None or not torso.size:continue
                torso=cv2.resize(torso,None,fx=4,fy=4)
                for angle in (0,-20,20):
                    rot=torso if angle==0 else cv2.warpAffine(torso,cv2.getRotationMatrix2D((torso.shape[1]/2,torso.shape[0]/2),angle,1),(torso.shape[1],torso.shape[0]),borderMode=cv2.BORDER_REPLICATE)
                    for result in reader.recognize(cv2.cvtColor(rot,cv2.COLOR_BGR2GRAY),allowlist='0123456789',detail=1):readings.append({'frame':candidate['frame'],'time':candidate['time'],'text':result[1],'score':round(float(result[2]),4),'crop':candidate['file']})
            # Process all independent crops: an early misread must not stop later contradictory evidence.
            label,ev=jersey_vote(readings,roster)
            localized=[r for r in readings if r.get('localized')]
            local_label,local_ev=jersey_vote(localized,roster)
            # Keep reading the independent distance-diverse crops; a later dorsal can contradict an early read.
        label,evidence=jersey_vote(readings,roster);labels[s['id']]={'number':label,'evidence':evidence};log.append({'track_id':s['id'],'label':label,'decision':evidence,'readings':readings});done+=1
        if done%5==0 or done==total:
            status={'state':'processing','stage':'jersey','done':done,'total':total,'identified_tracklets':sum(v['number'] is not None for v in labels.values())};write_json(output/'status.json',status);write_json(intermediate/'labels-checkpoint.json',labels);write_json(output/'jersey-evidence-checkpoint.json',log);print(json.dumps(status),flush=True)
    write_json(output/'jersey-evidence.json',log);write_json(intermediate/'labels.json',labels);return labels

def identify(records,summaries,feature_rows,features,labels,roster):
    gallery=defaultdict(list);label_map={};evidence_map={};track_features={s['id']:s['embedding_rows'] for s in summaries}
    for s in summaries:
        tid=s['id'];label=labels.get(tid,labels.get(str(tid),{}));n=label.get('number')
        dominant=Counter(s['kit_counts']).most_common(1)[0][0]
        if dominant=='keeper' and s['kit_counts'].get('keeper',0)>=4:n=1;label={'evidence':{'state':'accepted','method':'Unique yellow shirt and shorts, role supplied in roster'}}
        if n is not None:
            label_map[tid]=n;evidence_map[tid]={**label.get('evidence',{}),'method':'uniform_role' if n==1 else 'jersey_vote'}
            indices=s['embedding_rows']
            # Retain a range of poses, but limit long tracklets so they cannot dominate the gallery.
            for i in indices[::max(1,len(indices)//20)]:gallery[n].append(i)
    # Label unanchored segments using multiple embeddings, a similarity floor and a margin.
    for s in summaries:
        tid=s['id']
        if tid in label_map or s['kit_counts'].get('orange',0)<3:continue
        ids=s['embedding_rows']
        if len(ids)<2:continue
        sample=features[ids];scores=[]
        for n,anchors in gallery.items():
            if n==1 or not anchors:continue
            sims=sample@features[anchors].T;nearest=np.max(sims,axis=1);score=float(np.median(nearest));scores.append((score,n,float(np.mean(nearest>=.78))))
        scores.sort(reverse=True)
        if not scores:continue
        best=scores[0];runner=scores[1][0] if len(scores)>1 else 0
        if best[0]>=.80 and best[0]-runner>=.06 and best[2]>=.6:label_map[tid]=best[1];evidence_map[tid]={'method':'appearance_gallery','similarity':round(best[0],4),'margin':round(best[0]-runner,4),'samples':len(ids),'state':'estimated'}
    stitch(records,summaries,features,label_map,evidence_map)
    # Do not propagate a label across kit switches or simultaneous duplicates. Reject both ambiguous claims.
    rejected=0
    for r in records:
        occupants=defaultdict(list)
        for b in r['tracks']:
            n=label_map.get(b['id']);expected='keeper' if n==1 else 'orange'
            if n is not None and b['kit']==expected:
                b['player_id']=f'orange-{n}';b['identity']=evidence_map[b['id']];occupants[n].append(b)
            else:b['player_id']=None;b['identity']={'state':'unknown'}
        for n,boxes in occupants.items():
            if len(boxes)>1:
                ranked=sorted(boxes,key=lambda b:0 if b['identity']['method']=='jersey_vote' else 1)
                keep_one=ranked[0]['identity']['method']=='jersey_vote' and all(b['identity']['method']!='jersey_vote' for b in ranked[1:])
                for b in ranked[1:] if keep_one else ranked:b['player_id']=None;b['identity']={'state':'conflict','reason':'Simultaneous identity claim'};rejected+=1
    return gallery,label_map,evidence_map,rejected

def finish(records,summaries,features,feature_rows,metadata,labels,output,roster):
    refinement=CACHE/'ball-refinement.json';refinement_quality=output/'ball-refinement-quality.json'
    if metadata.get('full_source') and refinement.exists() and refinement_quality.exists():
        refined=json.loads(refinement.read_text());q=json.loads(refinement_quality.read_text())
        if len(refined)==len(records) and all(v['frame']==r['frame'] for v,r in zip(refined,records)):
            for r,v in zip(records,refined):r['ball']=v['ball'];r['possession']=infer_possession(r)
            metadata['ball_refinement']=q;write_json(output/'metadata.json',metadata)
    gallery,label_map,evidence_map,rejected=identify(records,summaries,feature_rows,features,labels,roster)
    temporal=json.loads((output/'temporal-candidates.json').read_text()) if (output/'temporal-candidates.json').exists() else []
    actions,unassigned=enrich(records,action_candidates(records)+trajectory_actions(records),temporal);lineup=infer_changes(roster,records);lineup['substitutions']=substitutions(records)
    metric_map={'pass':['passes'],'turnover':['turnovers'],'recovery':['recoveries'],'ball_into_box':['balls_into_box'],'goal':['goals','shots'],'shot':['shots'],'assist':['assists'],'big_chance':['big_chances'],'foul_won':['fouls_won'],'foul_committed':['fouls_committed'],'dribble':['successful_dribbles']}
    profiles=[]
    for n,p in roster.items():
        pid=f'orange-{n}';observations=[(r,b) for r in records for b in r['tracks'] if b.get('player_id')==pid];points=[{'time':r['time'],'x':round(b['position'][0],3),'y':round(b['position'][1],3),'track_id':b['id'],'identity_method':b['identity']['method'],'calibration_state':r['calibration']['state']} for r,b in observations if b['position'] is not None and 0<=b['position'][0]<=100 and 0<=b['position'][1]<=100]
        own=[e for e in actions if e['player_id']==pid];counts=Counter(k for e in own if e['state']=='estimated' for k in metric_map.get(e['kind'],[]));candidates=Counter(k for e in own if e['state']=='candidate' for k in metric_map.get(e['kind'],[]))
        metrics={k:{'value':counts.get(k) if counts.get(k) else None,'state':'estimated' if counts.get(k) else 'unavailable','reason':'Automatically found ownership transitions; partial coverage' if counts.get(k) else 'No reliable automatic measurement; not equivalent to zero'} for k in ('goals','assists','big_chances','balls_into_box','fouls_won','fouls_committed','recoveries','successful_dribbles','shots','passes','turnovers')}
        for k,m in metrics.items():m['candidates']=candidates.get(k,0)
        intervals=[]
        for r,b in observations:
            if not intervals or r['time']-intervals[-1]['end']>.25:intervals.append({'start':r['time'],'end':r['time']})
            else:intervals[-1]['end']=r['time']
        seconds=sum(min(1/metadata['analysis_fps'],max(0,metadata['duration']-r['time'])) for r,b in observations)
        profiles.append({**p,'id':pid,'identity_state':'observed' if observations else 'unidentified','samples':len(observations),'mapped_samples':len(points),'visible_seconds':round(seconds,1),'coverage_percent':round(seconds/metadata['duration']*100,1),'intervals':intervals,'metrics':metrics,'actions':own,'heatmap_points':points,'position':p.get('position'),'preferred_foot':p.get('preferred_foot'),'mean_position':np.mean([[v['x'],v['y']] for v in points],axis=0).round(2).tolist() if points else None})
    for minute in sorted({int(r['time']//60) for r in records}):write_json(output/'chunks'/f'{minute:03}.json',[r for r in records if int(r['time']//60)==minute])
    diagnostic={'sampled_frames':len(records),'calibrated_frames':sum(r['calibration']['state']!='unavailable' for r in records),'ball_visible_frames':sum(r['ball'] is not None for r in records),'possession_frames':sum(r['possession'] is not None for r in records),'identified_player_observations':sum(p['samples'] for p in profiles),'identified_players':sum(bool(p['samples']) for p in profiles),'ocr_anchored_tracklets':sum(v.get('number') is not None for v in labels.values()),'memory_tracklets':len(summaries),'duplicate_claims_rejected':rejected,'automatic_action_estimates':len(actions),'manual_annotation_inputs':0,'unsupported_metrics':['goals','assists','big_chances','fouls_won','fouls_committed','successful_dribbles','shots'],'scope':'Automatic prototype; unmeasured metrics are null, not zeros. No certified full-match totals.'}
    diagnostic['unassigned_temporal_events']=len(unassigned);diagnostic['probable_substitutions']=len(lineup['substitutions']);diagnostic['estimated_actions']=sum(e['state']=='estimated' for e in actions);diagnostic['candidate_actions']=sum(e['state']=='candidate' for e in actions);diagnostic['geometry']='approximate; engineer-configured goal correspondences';diagnostic['ball_refined']=bool(metadata.get('ball_refinement'));diagnostic['metrics_without_validated_counts']=diagnostic.pop('unsupported_metrics');diagnostic['completed_at_utc']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat();write_json(output/'unassigned-events.json',unassigned)
    write_json(output/'profiles.json',profiles);write_json(output/'actions.json',actions);write_json(output/'lineup.json',lineup);write_json(output/'quality.json',diagnostic);write_json(output/'gallery.json',[{'jersey_number':n,'track_ids':[t for t,v in label_map.items() if v==n],'appearance_samples':len(anchors)} for n,anchors in gallery.items()]);write_json(output/'status.json',{'state':'complete','stage':'done','done':len(records),'total':len(records),'quality':diagnostic});print(json.dumps(diagnostic),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default=SOURCE);p.add_argument('--start',type=float,default=0);p.add_argument('--end',type=float);p.add_argument('--fps',type=float,default=5);p.add_argument('--output',default=str(ROOT/'automatic'));p.add_argument('--work',default=str(CACHE));p.add_argument('--resume',action='store_true');p.add_argument('--reuse-ocr',action='store_true');p.add_argument('--scan-only',action='store_true');p.add_argument('--revote',action='store_true');a=p.parse_args()
    output=Path(a.output);intermediate=Path(a.work)
    for path in (output,output/'chunks',output/'audit',intermediate,intermediate/'crops'):path.mkdir(parents=True,exist_ok=True)
    roster={p['jersey_number']:p for p in json.loads((ROOT/'plantilla.json').read_text(encoding='utf8'))['players']}
    if a.resume:
        records=json.loads((intermediate/'scan.json').read_text());summaries=json.loads((intermediate/'summaries.json').read_text());rows=json.loads((intermediate/'feature-rows.json').read_text());features=np.load(intermediate/'embeddings.npy');metadata=json.loads((output/'metadata.json').read_text())
    else:records,summaries,rows,features,metadata=scan(a,output,intermediate)
    if a.scan_only:write_json(output/'status.json',{'state':'processing','stage':'jersey_pending','done':len(records),'total':len(records)});return
    labels=json.loads((intermediate/'labels.json').read_text()) if a.reuse_ocr else read_dorsals(summaries,output,intermediate,roster)
    if a.revote:
        evidence=json.loads((output/'jersey-evidence.json').read_text())
        for row in evidence:
            n,decision=jersey_vote(row['readings'],roster);row['label']=n;row['decision']=decision;labels[str(row['track_id'])]={'number':n,'evidence':decision}
        write_json(output/'jersey-evidence.json',evidence);write_json(intermediate/'labels.json',labels)
    finish(records,summaries,features,rows,metadata,labels,output,roster)
if __name__=='__main__':main()
