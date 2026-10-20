"""Automatic ball refinement with a dedicated detector, native tiles and local reacquisition."""
from pathlib import Path
import sys,json,time,cv2,numpy as np
from automatic_core import write_json,select_ball,infer_possession,ort_session,project
from runtime_context import ROOT,WORK,CACHE,SOURCE

class FootballBall:
    def __init__(self):
        self.session=ort_session(WORK/'football-ball-detection.onnx');self.name=self.session.get_inputs()[0].name
    def __call__(self,img,regions=None):
        h,w=img.shape[:2];balls=[]
        regions=regions or [(x,y,x+640,y+640) for y in (0,h-640) for x in (0,480,960,w-640)]
        for x,y,x2,y2 in regions:
            im=cv2.resize(img[y:y2,x:x2],(640,640));tensor=np.ascontiguousarray(im[:,:,::-1].transpose(2,0,1)[None],dtype=np.float32)/255
            raw=self.session.run(None,{self.name:tensor})[0][0];ids=np.where(raw[4]>.2)[0];arr=raw[:4,ids].T;scores=raw[4,ids];boxes=np.column_stack((arr[:,0]-arr[:,2]/2,arr[:,1]-arr[:,3]/2,arr[:,2],arr[:,3]));keep=np.asarray(cv2.dnn.NMSBoxes(boxes.tolist(),scores.tolist(),.2,.45)).reshape(-1)
            for i in keep:
                b=boxes[i];sx=(x2-x)/640;sy=(y2-y)/640
                balls.append({'box':[float(b[0]*sx+x),float(b[1]*sy+y),float((b[0]+b[2])*sx+x),float((b[1]+b[3])*sy+y)],'confidence':round(float(scores[i]),4),'detector':'football_ball_native_tiles'})
        boxes=[[b['box'][0],b['box'][1],b['box'][2]-b['box'][0],b['box'][3]-b['box'][1]] for b in balls];keep=np.asarray(cv2.dnn.NMSBoxes(boxes,[b['confidence'] for b in balls],.2,.4)).reshape(-1)
        return [balls[i] for i in keep]

def search_plan(previous,time,C,shape,last_search):
    h,w=shape[:2]
    if previous and time-previous['time']<=.6:
        pixel=None
        if C is not None and previous.get('position') is not None:
            try:pixel=project(np.linalg.inv(C),[previous['position']])[0]
            except np.linalg.LinAlgError:pass
        if pixel is None:pixel=previous.get('center')
        if pixel is not None:
            x=int(np.clip(pixel[0]-320,0,max(0,w-640)));y=int(np.clip(pixel[1]-320,0,max(0,h-640)))
            return [(x,y,min(w,x+640),min(h,y+640))],'local'
    return (None,'full') if time-last_search>=.59 else (None,'reacquisition_interval')

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--end',type=float);a=p.parse_args()
    records=json.loads((CACHE/'scan.json').read_text());detector=FootballBall();cap=cv2.VideoCapture(SOURCE);frame=-1;previous=None;last_search=-100;beg=time.perf_counter();result=[];full=0;local=0
    out=ROOT/'automatic';cache=CACHE;audit=cache/'ball-audit';audit.mkdir(exist_ok=True)
    for i,r in enumerate(records):
        if a.end is not None and r['time']>a.end:break
        while frame<r['frame']:
            if not cap.grab():raise RuntimeError('Unexpected video end')
            frame+=1
        ok,img=cap.retrieve()
        if not ok:raise RuntimeError('Cannot decode source frame')
        pairs=[b for b in r['tracks'] if b.get('position') is not None]
        C=None
        if len(pairs)>=4:
            source=np.float32([[(b['box'][0]+b['box'][2])/2,b['box'][3]] for b in pairs]);target=np.float32([b['position'] for b in pairs]);C,_=cv2.findHomography(source,target,cv2.RANSAC,.15)
        balls=[];regions,mode=search_plan(previous,r['time'],C,img.shape,last_search)
        if mode=='full':last_search=r['time'];full+=1
        elif mode=='local':local+=1
        if mode in ('local','full'):balls=detector(img,regions)
        new=select_ball(balls,r['time'],previous,C,img) if balls else None
        # A lower-confidence general-model detection does not override a dedicated detection.
        if new:previous=new
        selected=new or r.get('ball')
        result.append({'frame':r['frame'],'time':r['time'],'ball':selected,'dedicated_ball':new,'old_ball':r.get('ball'),'search':mode,'candidates':balls})
        if new and (i%300==0 or (r.get('ball') is None and i%150==0)):
            copy=img.copy();x1,y1,x2,y2=map(round,new['box']);cv2.rectangle(copy,(x1-7,y1-7),(x2+7,y2+7),(0,0,255),3);cv2.imwrite(str(audit/f'{i:05}.jpg'),copy)
        if i%100==0:
            status={'state':'processing','stage':'ball_refinement','done':i+1,'total':len(records),'seconds':round(time.perf_counter()-beg,1),'dedicated_visible':sum(b['dedicated_ball'] is not None for b in result)};write_json(out/'ball-status.json',status);print(json.dumps(status),flush=True);write_json(cache/'ball-refinement.json',result)
    cap.release();write_json(cache/'ball-refinement.json',result)
    quality={'samples':len(result),'old_visible':sum(b['old_ball'] is not None for b in result),'dedicated_visible':sum(b['dedicated_ball'] is not None for b in result),'combined_visible':sum(b['ball'] is not None for b in result),'full_searches':full,'local_searches':local,'run_seconds':round(time.perf_counter()-beg,2),'model_source':'https://github.com/roboflow/sports/blob/main/examples/soccer/setup.sh','policy':'Native 640px tiles; local 5fps search while tracked, full reacquisition at most every 0.6s; no invented positions between detections.'}
    write_json(out/'ball-refinement-quality.json',quality);write_json(out/'ball-status.json',{'state':'complete',**quality});print(json.dumps(quality),flush=True)
if __name__=='__main__':main()
