"""Projection to the relative pitch plane and camera registration. Moved from automatic_core.py without changes."""
from __future__ import annotations
import cv2,numpy as np

def project(H,points):
    if H is None:return None
    a=np.asarray(points,np.float32).reshape(1,-1,2);out=cv2.perspectiveTransform(a,H)[0]
    return out if np.isfinite(out).all() else None

class Registrar:
    """Direct registration to configured reference views; no cumulative camera drift."""
    def __init__(self,reference_images,transforms,C):
        self.sift=cv2.SIFT_create(nfeatures=2000);self.matcher=cv2.FlannBasedMatcher(dict(algorithm=1,trees=4),dict(checks=45));self.refs=[];self.C=np.asarray(C,np.float64)
        for image,T in zip(reference_images,transforms):
            kp,des=self.features(image);self.refs.append((kp,des,np.asarray(T,np.float64)))
    def features(self,img):
        im=cv2.resize(img,(960,540));return self.sift.detectAndCompute(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),None)
    def __call__(self,img):
        kp,des=self.features(img);best=None
        if des is None:return None,{'state':'unavailable','reason':'no features'}
        for rk,rd,T in self.refs:
            if rd is None:continue
            pairs=self.matcher.knnMatch(des,rd,k=2);good=[p for pair in pairs if len(pair)==2 for p,q in [pair] if p.distance<.70*q.distance]
            if len(good)<18:continue
            p=np.float32([kp[m.queryIdx].pt for m in good]);q=np.float32([rk[m.trainIdx].pt for m in good]);H,mask=cv2.findHomography(p,q,cv2.RANSAC,2.5)
            if H is None or mask is None:continue
            mask=mask.ravel().astype(bool);n=int(mask.sum());ratio=n/len(good)
            if n<18 or ratio<.22:continue
            predictions=project(H,p[mask]);error=float(np.median(np.linalg.norm(predictions-q[mask],axis=1)))
            if error>1.5:continue
            # The optical-center approximation is checked separately on pitch markings in the audit.
            scale=np.diag([.5,.5,1]);full=np.linalg.inv(scale)@H@scale;globalH=T@full;C=self.C@globalH
            score=n/(1+error)
            if best is None or score>best[0]:best=(score,C,{'state':'approximate','inliers':n,'matches':len(good),'median_reprojection_pixels':round(2*error,2),'global_matrix':globalH.tolist()})
        return (best[1],best[2]) if best else (None,{'state':'unavailable','reason':'insufficient registration'})

def camera_step(previous,current):
    """Current-to-previous camera mapping at every sampled frame, not just OCR frames."""
    a=cv2.cvtColor(cv2.resize(previous,(960,540)),cv2.COLOR_BGR2GRAY);b=cv2.cvtColor(cv2.resize(current,(960,540)),cv2.COLOR_BGR2GRAY)
    p=cv2.goodFeaturesToTrack(a,maxCorners=700,qualityLevel=.015,minDistance=10)
    if p is None or len(p)<20:return None
    q,ok,_=cv2.calcOpticalFlowPyrLK(a,b,p,None,winSize=(25,25),maxLevel=3)
    if q is None:return None
    valid=ok.ravel().astype(bool);p=p[valid,0];q=q[valid,0]
    if len(p)<20:return None
    H,mask=cv2.findHomography(q,p,cv2.RANSAC,1.8)
    if H is None or mask is None or mask.sum()<20 or mask.mean()<.5:return None
    scale=np.diag([.5,.5,1]);return np.linalg.inv(scale)@H@scale
