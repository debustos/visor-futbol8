"""Measured ankle proposals for raised-leg kicks; unique association to person boxes."""
import cv2,numpy as np
from f8.core.io import ort_session,iou
from f8.core.runtime_context import WORK

class PoseDetector:
    def __init__(self):
        self.session=ort_session(WORK/'yolo11s-pose.onnx');self.name=self.session.get_inputs()[0].name
    def __call__(self,img,region=None):
        h,w=img.shape[:2];x,y,x2,y2=region or (0,0,w,h);patch=img[y:y2,x:x2]
        if not patch.size:return []
        tensor=np.ascontiguousarray(cv2.resize(patch,(640,640))[:,:,::-1].transpose(2,0,1)[None],dtype=np.float32)/255
        raw=self.session.run(None,{self.name:tensor})[0][0];ids=np.flatnonzero(raw[4]>.25)
        if not len(ids):return []
        xywh=raw[:4,ids].T;scores=raw[4,ids];boxes=np.column_stack((xywh[:,0]-xywh[:,2]/2,xywh[:,1]-xywh[:,3]/2,xywh[:,2],xywh[:,3]));keep=np.asarray(cv2.dnn.NMSBoxes(boxes.tolist(),scores.tolist(),.25,.45)).reshape(-1);found=[]
        for i in keep:
            a,b,c,d=boxes[i];sx=(x2-x)/640;sy=(y2-y)/640;points=raw[5:,ids[i]].reshape(17,3).copy();points[:,0]=points[:,0]*sx+x;points[:,1]=points[:,1]*sy+y
            found.append({'box':[float(a*sx+x),float(b*sy+y),float((a+c)*sx+x),float((b+d)*sy+y)],'confidence':float(scores[i]),'keypoints':points.round(3).tolist(),'pose_model':'yolo11s-pose'})
        return found


def attach_poses(tracks,poses):
    assigned=0;used=set()
    for b in tracks:
        candidates=sorted([(iou(b['box'],p['box']),j,p) for j,p in enumerate(poses) if j not in used],reverse=True,key=lambda q:q[0])
        if not candidates or candidates[0][0]<.5 or len(candidates)>1 and candidates[0][0]-candidates[1][0]<.15:continue
        score,j,p=candidates[0];used.add(j);b['keypoints']=p['keypoints'];b['pose_evidence']={'model':p['pose_model'],'box_iou':round(score,4),'confidence':p['confidence']};assigned+=1
    return assigned


def ankle_contacts(record):
    ball=record.get('ball')
    if not ball or not ball.get('center'):return []
    found=[];center=np.array(ball['center'])
    for b in record.get('tracks',[]):
        if b.get('kit') not in ('orange','keeper','opponent') or not b.get('box'):continue
        kp=b.get('keypoints')
        if not kp or len(kp)<17:continue
        height=max(1,b['box'][3]-b['box'][1]);options=[]
        for j in (15,16):
            x,y,c=kp[j]
            if c<.55 or min(x,y)<=0:continue
            distance=float(np.linalg.norm(center-[x,y]))/height
            # A boot extends beyond its ankle. Aerial chest/head balls remain distinct.
            if distance<.12 and y>b['box'][1]+height*.5:options.append((distance,j,c))
        if options:
            distance,j,c=min(options);found.append((distance+.04,b,distance))
    return sorted(found,key=lambda q:q[0])
