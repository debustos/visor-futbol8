"""Process every part of a half, with streamed chunks and explicit unknown identities."""
from __future__ import annotations
import argparse, hashlib, json, math, os, time
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]/'work'
os.environ['YOLO_CONFIG_DIR']=str(WORK/'yolo-config')
os.environ['YOLO_OFFLINE']='true'
import cv2
import numpy as np
from PIL import Image, ImageDraw

def write_json(path,value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    temp.replace(path)

def classify(frame,box):
    x1,y1,x2,y2=box; h,w=frame.shape[:2]; bh=y2-y1;bw=x2-x1
    a,b=(.55,1) if y2>=h-3 else (.22,.55)
    crop=frame[max(0,int(y1+a*bh)):min(h,int(y1+b*bh)),max(0,int(x1+.18*bw)):min(w,int(x2-.18*bw))]
    if crop.size==0:return 'unknown',0.
    hu,sa,va=cv2.split(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV))
    scores={'orange':float(np.mean((hu>=3)&(hu<=23)&(sa>75)&(va>70))),
            'yellow':float(np.mean((hu>23)&(hu<40)&(sa>90)&(va>95))),
            'opponent':float(np.mean((va<175)&(sa<110)))}
    for key,threshold in [('orange',.15),('yellow',.18),('opponent',.30)]:
        if scores[key]>threshold:return key,round(scores[key],3)
    return 'unknown',round(max(scores.values()),3)

def near_pitch(frame,box):
    x1,y1,x2,y2=box;h,w=frame.shape[:2]
    if y2>=h-3:return True
    cx=int((x1+x2)/2);y=int(y2);half=max(6,int((x2-x1)*.3))
    crop=frame[max(0,y-2):min(h,y+12),max(0,cx-half):min(w,cx+half)]
    if crop.size==0:return False
    hu,sa,va=cv2.split(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV))
    return float(np.mean((hu>30)&(hu<95)&(sa>25)&(va>35)))>.18

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default='S:/PRIMERA PARTE.MP4');p.add_argument('--fps',type=float,default=5);p.add_argument('--limit',type=float);p.add_argument('--output',default=str(ROOT/'data'));args=p.parse_args()
    if not 0<args.fps<=30:raise ValueError('Frecuencia fuera de rango')
    import torch,ultralytics
    from ultralytics import YOLO,settings
    from ultralytics.engine.results import Boxes
    from ultralytics.trackers.bot_sort import BOTSORT
    from ultralytics.utils import IterableSimpleNamespace
    settings.update({'sync':False});torch.set_num_threads(6);cv2.setNumThreads(2)
    output=Path(args.output);(output/'chunks').mkdir(parents=True,exist_ok=True);(output/'audit').mkdir(exist_ok=True)
    model_path=WORK/'yolo11n.pt';model=YOLO(str(model_path))
    tracker_cfg={'tracker_type':'botsort','track_high_thresh':.25,'track_low_thresh':.1,'new_track_thresh':.30,'track_buffer':8,'match_thresh':.75,'fuse_score':True,'gmc_method':'sparseOptFlow','proximity_thresh':.5,'appearance_thresh':.8,'with_reid':False,'model':'auto'}
    tracker=BOTSORT(IterableSimpleNamespace(**tracker_cfg))
    cap=cv2.VideoCapture(args.source)
    if not cap.isOpened():raise RuntimeError('No se puede abrir la primera parte')
    source_fps=cap.get(cv2.CAP_PROP_FPS);total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));w=int(cap.get(3));h=int(cap.get(4));duration=total/source_fps
    last=total-1 if args.limit is None else min(total-1,round(args.limit*source_fps)-1)
    targets=sorted({min(last,round(i*source_fps/args.fps)) for i in range(math.ceil((last+1)/source_fps*args.fps))}|{last})
    model_hash=hashlib.sha256(model_path.read_bytes()).hexdigest()
    metadata={'part':'primera','source':args.source,'source_fps':source_fps,'source_frames':total,'width':w,'height':h,'duration':duration,'analysis_fps':args.fps,'planned_samples':len(targets),'model':'YOLO11n','model_sha256':model_hash,'device':'cpu','image_size':1280,'tracker':tracker_cfg,'versions':{'torch':torch.__version__,'ultralytics':ultralytics.__version__,'opencv':cv2.__version__},'identity_mode':'manual intervals; no automatic jersey recognition','chunk_seconds':60}
    write_json(output/'metadata.json',metadata)
    write_json(output/'status.json',{'state':'processing','done':0,'total':len(targets),'source_seconds':0})
    current=0;chunk_number=0;records=[];fragments=defaultdict(list);counts=Counter();started=time.perf_counter();det_count=0
    try:
        for sample,target in enumerate(targets):
            while current<target:
                if not cap.grab():raise RuntimeError(f'Fin inesperado en {current}')
                current+=1
            ok,frame=cap.read();current+=1
            if not ok:raise RuntimeError(f'Error decodificando {target}')
            t=round(target/source_fps,4);minute=int(t//60)
            if minute!=chunk_number and records:
                write_json(output/'chunks'/f'{chunk_number:03}.json',records);records=[];chunk_number=minute
            small=cv2.resize(frame,(1280,round(h*1280/w)));scale=w/1280
            result=model.predict(small,classes=[0],conf=.20,iou=.40,imgsz=1280,device='cpu',verbose=False)[0]
            detections=[]
            for xy,conf in zip(result.boxes.xyxy.tolist(),result.boxes.conf.tolist()):
                if near_pitch(small,xy):detections.append(xy+[conf,0])
            array=np.asarray(detections,dtype=np.float32).reshape(-1,6)
            tracked=tracker.update(Boxes(array,small.shape[:2]),small)
            tracks=[]
            for b in tracked:
                box=[round(float(v)*scale,2) for v in b[:4]];kit,score=classify(frame,box);tid=int(b[4]);confidence=round(float(b[5]),4)
                candidate=near_pitch(frame,box)
                tracks.append({'id':tid,'box':box,'confidence':confidence,'kit':kit,'kit_score':score,'field_candidate':candidate})
                fragments[tid].append((t,kit,candidate));counts[kit]+=1
            records.append({'sample':sample,'frame':target,'time':t,'tracks':tracks,'detection_count':len(detections)});det_count+=len(detections)
            if sample%round(args.fps*60)==0 or sample==len(targets)-1:
                im=Image.fromarray(cv2.cvtColor(small,cv2.COLOR_BGR2RGB));draw=ImageDraw.Draw(im)
                colors={'orange':'orange','yellow':'yellow','opponent':'cyan','unknown':'white'}
                for b in tracks:
                    xy=[v/scale for v in b['box']];draw.rectangle(xy,outline=colors[b['kit']],width=2);draw.text((xy[0],max(20,xy[1]-12)),f"{b['kit']} T{b['id']}",fill=colors[b['kit']])
                draw.rectangle((0,0,1280,20),fill='black');draw.text((8,4),f'PRIMERA PARTE {t:.2f}s - identidad pendiente',fill='white')
                im.save(output/'audit'/f'{sample:05}.jpg',quality=88)
            if sample%100==0 or sample==len(targets)-1:
                status={'state':'processing','done':sample+1,'total':len(targets),'source_seconds':t,'elapsed':round(time.perf_counter()-started,1)};write_json(output/'status.json',status);print(json.dumps(status),flush=True)
        write_json(output/'chunks'/f'{chunk_number:03}.json',records)
        summaries=[]
        for tid,obs in fragments.items():
            runs=[];run=None
            for t,kit,candidate in obs:
                if run is None or t-run['end']>1.5/args.fps:
                    run={'start':t,'end':t,'samples':0};runs.append(run)
                run['end']=t;run['samples']+=1
            kits=Counter(k for t,k,c in obs)
            summaries.append({'id':tid,'start':obs[0][0],'end':obs[-1][0],'samples':len(obs),'kit':kits.most_common(1)[0][0],'kit_counts':dict(kits),'runs':runs,'candidate_samples':sum(c for t,k,c in obs)})
        write_json(output/'fragments.json',summaries)
        metadata.update({'processed_samples':len(targets),'processed_last_frame':last,'runtime_seconds':round(time.perf_counter()-started,2),'unique_fragments':len(summaries),'tracked_observations':sum(counts.values()),'detections':det_count,'kit_observations':dict(counts),'full_source':last==total-1})
        write_json(output/'metadata.json',metadata);write_json(output/'status.json',{'state':'complete','done':len(targets),'total':len(targets),'source_seconds':last/source_fps,'elapsed':metadata['runtime_seconds']})
        print(json.dumps(metadata),flush=True)
    except Exception as e:
        write_json(output/'status.json',{'state':'failed','error':str(e),'done':sum(len(v) for v in fragments.values())});raise
    finally:cap.release()

if __name__=='__main__':main()
