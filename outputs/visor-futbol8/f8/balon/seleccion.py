"""Ball candidate selection; abstains when candidates compete. Moved from automatic_core.py without changes."""
from __future__ import annotations
import math
import cv2,numpy as np
from f8.core.io import crop
from f8.campo.proyeccion import project

def select_ball(candidates,time,previous,C,img):
    plausible=[]
    for b in candidates:
        x1,y1,x2,y2=b['box'];w=x2-x1;h=y2-y1;x=(x1+x2)/2;y=(y1+y2)/2
        if min(w,h)<3 or max(w,h)>48 or max(w,h)/min(w,h)>2:continue
        pos=project(C,[[x,y]]) if C is not None else None
        if pos is not None and not(-3<=pos[0,0]<=103 and -4<=pos[0,1]<=104):continue
        # A ball on the barrier or the adjacent pitch must not become possession in this match.
        c=crop(img,[x1-7,y1-7,x2+7,y2+7]);hsv=cv2.cvtColor(c,cv2.COLOR_BGR2HSV) if c.size else None
        if hsv is not None and np.mean((hsv[:,:,0]>30)&(hsv[:,:,0]<95)&(hsv[:,:,1]>20))<.12:continue
        score=b['confidence']
        if previous and time-previous['time']<.65:
            if pos is not None and previous.get('position') is not None:
                distance=float(np.linalg.norm(pos[0]-previous['position']))
                if distance>35:continue
                score+=.15*math.exp(-distance/10)
            elif previous.get('center'):
                distance=math.hypot(x-previous['center'][0],y-previous['center'][1])
                score+=.15*math.exp(-distance/100)
        plausible.append((score,{**b,'center':[round(x,2),round(y,2)],'position':pos[0].round(3).tolist() if pos is not None else None,'time':time}))
    if not plausible:return None
    plausible.sort(key=lambda v:v[0],reverse=True)
    # Keep multiple candidates in diagnostics, but abstain from possession when similarly plausible balls compete.
    if len(plausible)>1 and plausible[0][0]-plausible[1][0]<.06:return None
    return plausible[0][1]
