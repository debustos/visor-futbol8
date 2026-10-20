"""Verify image goal posts near calibrated F8 goal seeds; no goal count from geometry alone."""
import cv2,numpy as np
from automatic_core import project


def detect_goal(img,C,end=0):
    if C is None:return None
    try:inverse=np.linalg.inv(C)
    except np.linalg.LinAlgError:return None
    seed=project(inverse,[[42.5,end],[57.5,end]])
    if seed is None:return None
    seed=seed[np.argsort(seed[:,0])];width=float(np.linalg.norm(seed[1]-seed[0]));h,w=img.shape[:2]
    if not 80<=width<=1200 or min(seed[:,0])<0 or max(seed[:,0])>=w:return None
    x0=max(0,int(seed[0,0]-width*.22));x2=min(w,int(seed[1,0]+width*.22));y0=max(0,int(min(seed[:,1])-width*.55));y2=min(h,int(max(seed[:,1])+width*.18));patch=img[y0:y2,x0:x2]
    hsv=cv2.cvtColor(patch,cv2.COLOR_BGR2HSV);mask=((hsv[:,:,1]<70)&(hsv[:,:,2]>190)).astype(np.uint8)*255
    lines=cv2.HoughLinesP(mask,1,np.pi/180,25,minLineLength=max(35,int(width*.27)),maxLineGap=9);uprights=[]
    for a,b,c,d in [] if lines is None else lines.reshape(-1,4):
        if abs(c-a)>max(8,abs(d-b)*.12) or abs(d-b)<width*.27:continue
        p=np.array([a+x0,b+y0],float);q=np.array([c+x0,d+y0],float);top,bottom=(p,q) if p[1]<q[1] else (q,p)
        if not .27*width<=bottom[1]-top[1]<=.55*width:continue
        uprights.append((top,bottom))
    candidates=[]
    for left in uprights:
        for right in uprights:
            separation=right[1][0]-left[1][0]
            if not .75*width<=separation<=1.25*width:continue
            error=np.linalg.norm(left[1]-seed[0])+np.linalg.norm(right[1]-seed[1])
            if error>width*.40 or abs(left[0][1]-right[0][1])>width*.05 or abs(left[1][1]-right[1][1])>width*.06:continue
            white=[]
            for x,y in np.linspace(left[0],right[0],40):
                xx=int(x-x0);yy=int(y-y0);p=mask[max(0,yy-4):min(mask.shape[0],yy+5),max(0,xx-2):min(mask.shape[1],xx+3)];white.append(bool(p.size and p.max()))
            support=float(np.mean(white))
            if support<.8:continue
            interior=mask[max(0,int(max(left[0][1],right[0][1])-y0)+10):max(0,int(min(left[1][1],right[1][1])-y0)-10),max(0,int(left[0][0]-x0)+10):max(0,int(right[0][0]-x0)-10)]
            if not interior.size or np.mean(interior>0)>.35:continue
            height=(left[1][1]-left[0][1]+right[1][1]-right[0][1])/2
            candidates.append((support-.5*error/width+.3*height/width,{'polygon':[left[0].tolist(),right[0].tolist(),right[1].tolist(),left[1].tolist()],'end':end,'crossbar_support':round(support,3),'seed_error_pixels':round(error,2),'method':'two_white_posts_and_crossbar_near_F8_calibration','state':'image_verified','crossing_certified':False}))
    candidates.sort(key=lambda q:-q[0]);return candidates[0][1] if candidates else None


class GoalImageTracker:
    """Carry a verified goal outline through short camera movement, never count goals."""
    def __init__(self,end=0):
        self.end=end;self.previous_image=None;self.previous_time=None;self.goal=None;self.last_verified=-100
    def update(self,img,time,C=None):
        from automatic_core import camera_step
        carried=None;dt=time-self.previous_time if self.previous_time is not None else 0
        if self.goal and 0<dt<=.2 and time-self.last_verified<=.4:
            backward=camera_step(self.previous_image,img)
            if backward is not None:
                try:H=np.linalg.inv(backward)
                except np.linalg.LinAlgError:H=None
                points=project(H,self.goal['polygon']) if H is not None else None
                if points is not None:
                    width=np.linalg.norm(points[1]-points[0]);oldwidth=np.linalg.norm(np.array(self.goal['polygon'][1])-self.goal['polygon'][0])
                    if .90<=width/max(oldwidth,1)<=1.10:
                        carried={**self.goal,'polygon':points.tolist(),'state':'camera_carried','last_verified_time':self.last_verified,'crossing_certified':False}
        detected=detect_goal(img,C,self.end)
        if detected and carried:
            error=float(np.max(np.linalg.norm(np.array(detected['polygon'])-carried['polygon'],axis=1)))
            width=np.linalg.norm(np.array(carried['polygon'][1])-carried['polygon'][0])
            if error>max(8,width*.07):detected=None
        if detected:
            self.last_verified=time;detected['last_verified_time']=time;self.goal=detected
        else:self.goal=carried
        self.previous_image=img;self.previous_time=time
        return self.goal


def mouth_point(goal,center):
    if not goal:return None
    H=cv2.getPerspectiveTransform(np.float32(goal['polygon']),np.float32([[0,0],[1,0],[1,1],[0,1]]))
    q=project(H,[center]);return q[0] if q is not None else None


def approach_proposals(samples,end):
    """Measured trajectories approaching the visible mouth are shot proposals only.

    A 2-D image cannot certify that the ball crossed the goal line in depth.
    """
    groups=[]
    for sample in samples:
        if sample.get('mouth') is None:continue
        if not groups or sample['time']-groups[-1][-1]['time']>.35:groups.append([])
        groups[-1].append(sample)
    proposals=[]
    for group in groups:
        last_emission=-100
        for i,last in enumerate(group):
            q=np.array(last['mouth']);distance=float(np.linalg.norm(q-np.clip(q,0,1)))
            if distance>.08 or last['time']-last_emission<2:continue
            previous=[x for x in group[max(0,i-60):i+1] if .18<=last['time']-x['time']<=1.6 and np.linalg.norm(np.array(x['mouth'])-np.clip(x['mouth'],0,1))>=.75]
            if not previous:continue
            first=previous[-1];path=[x for x in group if first['time']<=x['time']<=last['time']]
            if len(path)<5 or sum(x.get('measurement')=='neural_detection' for x in path)<2:continue
            points=np.array([x['mouth'] for x in path]);d=points[-1]-points[0];length=float(np.linalg.norm(d))
            if length<.75:continue
            progression=(points-points[0])@d/(length*length);residual=np.linalg.norm(points-(points[0]+progression[:,None]*d),axis=1)
            distances=np.linalg.norm(points-np.clip(points,0,1),axis=1)
            if np.mean(np.diff(distances)<=.10)<.8 or np.mean(np.diff(progression)>=-.10)<.8 or np.median(residual)>.15:continue
            proposals.append({'time':first['time'],'class':'Visual goal approach','score':.5,'goal_end':end,'mouth_entry_time':last['time'],'path_samples':len(path),'neural_samples':sum(x.get('measurement')=='neural_detection' for x in path),'start_distance_goal_widths':round(float(distances[0]),3),'trajectory_residual':round(float(np.median(residual)),3),'crossing_certified':False,'evidence_start':max(0,first['time']-1),'evidence_end':last['time']+1,'measurement_times':[x['time'] for x in path],'method':'Measured image trajectory approaching verified posts; shot intention and actor require review.'})
            last_emission=last['time']
    return proposals
