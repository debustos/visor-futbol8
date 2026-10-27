"""Person detector, appearance embeddings, kit colours and the memory tracker. Moved from automatic_core.py without changes."""
from __future__ import annotations
from collections import Counter
import cv2,numpy as np
from scipy.optimize import linear_sum_assignment
from f8.core.io import ort_session,crop,iou

class Detector:
    def __init__(self,path):self.session=ort_session(path);self.input=self.session.get_inputs()[0].name
    def __call__(self,img):
        small=cv2.resize(img,(1280,720));padded=cv2.copyMakeBorder(small,8,8,0,0,cv2.BORDER_CONSTANT,value=(114,114,114))
        tensor=np.ascontiguousarray(padded[:,:,::-1].transpose(2,0,1)[None],dtype=np.float32)/255
        raw=self.session.run(None,{self.input:tensor})[0][0];output={}
        for cls,threshold in [(0,.20),(32,.12)]:
            indexes=np.where(raw[4+cls]>=threshold)[0];arr=raw[:4,indexes].T;scores=raw[4+cls,indexes]
            boxes=np.column_stack((arr[:,0]-arr[:,2]/2,arr[:,1]-arr[:,3]/2,arr[:,2],arr[:,3]))
            keep=cv2.dnn.NMSBoxes(boxes.tolist(),scores.tolist(),threshold,.45)
            output[cls]=[{'box':[(float(boxes[i,0]))*1.5,(float(boxes[i,1])-8)*1.5,(float(boxes[i,0]+boxes[i,2]))*1.5,(float(boxes[i,1]+boxes[i,3])-8)*1.5],'confidence':round(float(scores[i]),4)} for i in np.asarray(keep).reshape(-1)]
        return output

def appearance(img,box):
    feats=[]
    for a,b in [(0,.17),(.18,.48),(.49,.68),(.69,.9),(.9,1)]:
        part=crop(img,box,a,b,.12,.88)
        if not part.size:feats.extend(np.zeros(64));continue
        hsv=cv2.cvtColor(part,cv2.COLOR_BGR2HSV);hist=cv2.calcHist([hsv],[0,1],None,[8,8],[0,180,0,256]).reshape(-1);hist/=max(hist.sum(),1);feats.extend(np.sqrt(hist))
    f=np.asarray(feats,np.float32);return f/max(np.linalg.norm(f),1e-8)

def kit(img,box):
    torso=crop(img,box,.2,.5,.2,.8);legs=crop(img,box,.52,.83,.18,.82)
    if not torso.size:return 'unknown',0
    hsv=cv2.cvtColor(torso,cv2.COLOR_BGR2HSV);h,s,v=cv2.split(hsv)
    orange=float(np.mean((h>=3)&(h<=23)&(s>75)&(v>65)));yellow=float(np.mean((h>23)&(h<40)&(s>90)&(v>95)));black=float(np.mean((v<160)&(s<110)))
    if yellow>.18:
        if legs.size:
            h,s,v=cv2.split(cv2.cvtColor(legs,cv2.COLOR_BGR2HSV));full=float(np.mean((h>23)&(h<40)&(s>75)&(v>90)))
            if full>.22:return 'keeper',round(min(yellow,full),3)
        return 'referee',round(yellow,3)
    if orange>.15:return 'orange',round(orange,3)
    if black>.3:return 'opponent',round(black,3)
    return 'unknown',0

class Encoder:
    def __init__(self,path):self.session=ort_session(path);self.name=self.session.get_inputs()[0].name
    def __call__(self,img,boxes):
        if not boxes:return []
        images=[]
        for b in boxes:
            part=crop(img,b)
            if not part.size:part=np.zeros((16,16,3),np.uint8)
            images.append(cv2.resize(part,(224,224))[:,:,::-1].transpose(2,0,1))
        data=np.ascontiguousarray(images,dtype=np.float32)/255;raw=self.session.run(None,{self.name:data})[0];raw=raw.reshape(len(boxes),-1)
        return raw/np.maximum(np.linalg.norm(raw,axis=1,keepdims=True),1e-8)

class MemoryTracker:
    """Motion in camera-corrected coordinates, appearance, and exclusive assignments."""
    def __init__(self):self.live={};self.next_id=1;self.summary={}
    def update(self,detections,time,C):
        live=[v for v in self.live.values() if time-v['time']<=2];cost=np.full((len(live),len(detections)),100.,np.float32)
        for i,t in enumerate(live):
            for j,d in enumerate(detections):
                if t['kit']!='unknown' and d['kit']!='unknown' and t['kit']!=d['kit']:continue
                visual=float(t['appearance']@d['appearance']);embed=float(t['embedding']@d['embedding']) if t.get('embedding') is not None and d.get('embedding') is not None else visual
                overlap=iou(t['box'],d['box']);gap=time-t['time']
                if t['position'] is not None and d['position'] is not None:
                    predicted=np.asarray(t['position'])+np.asarray(t.get('velocity',[0,0]))*min(gap,.6);distance=float(np.linalg.norm(predicted-d['position']))
                    gate=3+gap*8
                else:
                    a=np.array([(t['box'][0]+t['box'][2])/2,t['box'][3]]);b=np.array([(d['box'][0]+d['box'][2])/2,d['box'][3]]);distance=float(np.linalg.norm(a-b))/max(d['box'][3]-d['box'][1],35);gate=.8+gap*2
                if distance>gate or (overlap<.05 and visual<.55):continue
                cost[i,j]=.50*min(distance/gate,1)+.25*(1-visual)+.15*(1-embed)+.10*(1-overlap)
        assigned={}
        if cost.size:
            for i,j in zip(*linear_sum_assignment(cost)):
                if cost[i,j]<.59:assigned[j]=live[i]['id']
        result=[]
        for j,d in enumerate(detections):
            tid=assigned.get(j)
            if tid is None:tid=self.next_id;self.next_id+=1;self.summary[tid]={'id':tid,'start':time,'end':time,'samples':0,'kit_counts':Counter(),'embedding_rows':[],'ocr_candidates':[]}
            old=self.live.get(tid);velocity=np.zeros(2)
            if old and old['position'] is not None and d['position'] is not None and time>old['time']:
                velocity=(np.array(d['position'])-old['position'])/(time-old['time']);velocity=np.clip(velocity,-25,25)*.4+np.array(old.get('velocity',[0,0]))*.6
            d.update(id=tid,time=time,velocity=velocity.tolist())
            if old:
                if d.get('embedding') is None:d['embedding']=old.get('embedding')
                if d['kit']=='unknown':d['kit']=old['kit']
            self.live[tid]=d;summary=self.summary[tid];summary['end']=time;summary['samples']+=1;summary['kit_counts'][d['kit']]+=1;result.append(d)
        self.live={k:v for k,v in self.live.items() if time-v['time']<=2}
        return result
