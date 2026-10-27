"""Ball measurements at native frame rate with camera compensation and local reacquisition.

Motion predicts search windows only. A returned ball always has a measured detector
box or a compact, high-contrast image component connected to a recent detector seed.
"""
import cv2,math,numpy as np
from f8.campo.proyeccion import camera_step,project


def compact_components(img,center,radius,diameter):
    h,w=img.shape[:2];x,y=center
    x0=max(0,int(x-radius));y0=max(0,int(y-radius));x2=min(w,int(x+radius+1));y2=min(h,int(y+radius+1))
    if x2<=x0 or y2<=y0:return []
    patch=img[y0:y2,x0:x2];H,S,V=cv2.split(cv2.cvtColor(patch,cv2.COLOR_BGR2HSV))
    # Local contrast removes uniform grass, while compactness removes pitch lines.
    blur=cv2.GaussianBlur(V,(0,0),max(3,diameter*.75))
    mask=((S<125)&(V>=165)&(V.astype(float)-blur.astype(float)>18)).astype(np.uint8)
    count,labels,stats,centroids=cv2.connectedComponentsWithStats(mask)
    found=[]
    for i,(a,b,ww,hh,area) in enumerate(stats[1:],1):
        if min(ww,hh)<3 or max(ww,hh)>max(40,diameter*2) or max(ww,hh)/min(ww,hh)>2.2:continue
        if not max(7,diameter*diameter*.08)<=area<=diameter*diameter*2.2 or area/(ww*hh)<.43:continue
        if not .65<=math.sqrt(ww*hh)/max(diameter,1)<=1.8:continue
        white=float(np.mean(V[labels==i]));contrast=float(np.mean(V.astype(float)[labels==i]-blur.astype(float)[labels==i]));cx,cy=centroids[i]
        found.append({'box':[float(a+x0),float(b+y0),float(a+ww+x0),float(b+hh+y0)],'center':[float(cx+x0),float(cy+y0)],'confidence':.5,'detector':'compact_image_component','local_contrast':round(contrast,2),'fill':round(area/(ww*hh),3)})
    return found


def map_point(H,p):
    if H is None:return np.asarray(p,float)
    q=project(H,[p]);return q[0] if q is not None else np.asarray(p,float)


class MeasuredBallTracker:
    def __init__(self):
        self.previous_image=None;self.time=None;self.ball=None;self.velocity=np.zeros(2);self.last_seed=-100;self.missing=0;self.recent=0;self.last_camera=None;self.seed_streak=0;self.search_center=None;self.diameter=12;self.prediction_time=None;self.prediction_value=None
    def predict(self,img,time):
        self.prediction_time=time;self.prediction_value=None
        dt=time-self.time if self.time is not None else 0
        self.last_camera=None
        # Camera registration only moves an existing search center. Without a
        # measured seed (or across a time gap) update() must reacquire instead.
        if self.ball is None or not 0<dt<=.12:return None
        backward=camera_step(self.previous_image,img) if self.previous_image is not None else None
        H=None
        if backward is not None:
            try:H=np.linalg.inv(backward)
            except np.linalg.LinAlgError:pass
        self.last_camera=H
        self.prediction_value=map_point(H,self.search_center)+self.velocity*dt
        return self.prediction_value
    def update(self,img,time,candidates,C=None,prediction=None):
        dt=time-self.time if self.time is not None else 0
        previous=self.ball;recent=previous is not None and .001<dt<=.12 and time-previous['time']<=.6
        predicted=prediction if prediction is not None else self.prediction_value if self.prediction_time==time else self.predict(img,time)
        diameter=self.diameter if previous else 12
        radius=max(22,diameter*2.2,float(np.linalg.norm(self.velocity))*max(dt,0)*.9)
        radius=min(180,radius+max(0,time-previous['time']-dt)*400) if recent else radius
        choices=[]
        for b in candidates:
            a,y,c,d=b['box'];ww=c-a;hh=d-y
            if min(ww,hh)<3 or max(ww,hh)>48 or max(ww,hh)/min(ww,hh)>2.2:continue
            center=np.array([(a+c)/2,(y+d)/2]);error=float(np.linalg.norm(center-predicted)) if predicted is not None else None
            if recent and error>radius:continue
            if b.get('confidence',0)<(.23 if recent else .65):continue
            if recent and not .35<=math.sqrt(ww*hh)/diameter<=2.3:continue
            # New seeds require a field background, airborne continuation does not.
            patch=img[max(0,int(y)-7):min(img.shape[0],int(d)+7),max(0,int(a)-7):min(img.shape[1],int(c)+7)]
            if not patch.size:continue
            hsv=cv2.cvtColor(patch,cv2.COLOR_BGR2HSV);grass=float(np.mean((hsv[:,:,0]>30)&(hsv[:,:,0]<95)&(hsv[:,:,1]>20)))
            if not recent and grass<.15:continue
            plane=project(C,[center]) if C is not None else None
            if not recent and plane is not None and not(-8<=plane[0,0]<=108 and -8<=plane[0,1]<=108):continue
            score=b['confidence']-(.25*error/radius if recent else 0)
            choices.append((score,{**b,'center':center.tolist(),'prediction_error_pixels':error,'measurement':'neural_detection','grass_fraction':grass}))
        if recent and time-self.last_seed<=.6 and self.seed_streak>=2 and predicted is not None:
            for b in compact_components(img,predicted,radius+max(0,time-previous['time']-.06)*120,diameter):
                error=float(np.linalg.norm(np.array(b['center'])-predicted))
                if b['fill']<.60 or b['local_contrast']<35:continue
                limit=max(12,diameter*.9)+max(0,time-previous['time']-.06)*120
                if error>min(radius+max(0,time-previous['time']-.06)*120,limit):continue
                score=.58-.25*error/max(radius,limit)
                choices.append((score,{**b,'prediction_error_pixels':error,'measurement':'compact_image_component'}))
        choices.sort(key=lambda item:-item[0]);selected=None
        if choices:
            best,value=choices[0]
            # Duplicate boxes are the same candidate, different locations are ambiguous.
            rivals=[q for q in choices[1:] if np.linalg.norm(np.array(q[1]['center'])-value['center'])>max(5,diameter*.6)]
            if not rivals or best-rivals[0][0]>=.10:
                selected=value
        if selected:
            center=selected['center'];pos=project(C,[center]) if C is not None and selected.get('grass_fraction',0)>=.15 else None
            selected.update(time=time,position=pos[0].round(3).tolist() if pos is not None and -3<=pos[0,0]<=103 and -4<=pos[0,1]<=104 else None)
            if recent:
                correction=(np.array(center)-predicted)/max(dt,time-previous['time'])
                self.velocity=self.velocity+.65*correction
            else:self.velocity=np.zeros(2)
            if selected['measurement']=='neural_detection':
                self.seed_streak=self.seed_streak+1 if recent else 1;self.last_seed=time;self.diameter=math.sqrt((selected['box'][2]-selected['box'][0])*(selected['box'][3]-selected['box'][1]))
            self.ball=selected;self.search_center=np.asarray(center,float);self.missing=0
        else:
            self.missing+=1
            # No synthetic center is ever returned or stored as a measurement.
            if predicted is not None:self.search_center=predicted
            if previous is None or time-previous['time']>.6:self.ball=None;self.search_center=None;self.velocity=np.zeros(2);self.seed_streak=0
        self.previous_image=img;self.time=time
        return selected
