"""Visible hair, kit, socks and boot color features from original crops; no metric body claims."""
from pathlib import Path
from collections import defaultdict
import json,time,cv2,numpy as np
from automatic_core import crop,write_json
from runtime_context import ROOT,WORK,CACHE,SOURCE

def physical_signature(img,box):
    feats=[]
    for a,b in [(0,.18),(.18,.5),(.5,.68),(.68,.9),(.9,1)]:
        part=crop(img,box,a,b,.1,.9)
        if not part.size:feats.extend(np.zeros(72));continue
        hsv=cv2.cvtColor(part,cv2.COLOR_BGR2HSV);h,s,v=cv2.split(hsv);mask=(~((h>30)&(h<95)&(s>25))).astype(np.uint8)*255
        hist=cv2.calcHist([hsv],[0,1],mask,[8,8],[0,180,0,256]).ravel();hist/=max(1,hist.sum());v_hist=cv2.calcHist([hsv],[2],mask,[8],[0,256]).ravel();v_hist/=max(1,v_hist.sum());feats.extend(np.sqrt(hist));feats.extend(np.sqrt(v_hist))
    w=box[2]-box[0];h=box[3]-box[1];feats.extend([np.clip(w/max(h,1),0,1),0 if h<60 else 1])
    return np.array(feats,np.float32)

def main():
    cache=CACHE;rows=json.loads((cache/'feature-rows.json').read_text());records={r['frame']:r for r in json.loads((cache/'scan.json').read_text())};groups=defaultdict(list)
    for row in rows:groups[row['frame']].append(row)
    result=np.zeros((len(rows),362),np.float32);cap=cv2.VideoCapture(SOURCE);frame=-1;beg=time.monotonic()
    for i,(target,observations) in enumerate(sorted(groups.items())):
        while frame<target:
            if not cap.grab():raise RuntimeError('Source decode ended')
            frame+=1
        ok,img=cap.retrieve()
        if not ok:raise RuntimeError(target)
        boxes={b['id']:b['box'] for b in records[target]['tracks']}
        for row in observations:result[row['index']]=physical_signature(img,boxes[row['track_id']])
        if i%150==0:print(json.dumps({'appearance_frame':i,'total':len(groups),'elapsed':round(time.monotonic()-beg,1)}),flush=True)
    cap.release();np.save(cache/'physical-features.npy',result);write_json(ROOT/'automatic/physical-feature-metadata.json',{'frames':len(groups),'observations':len(rows),'components':'five body regions: HSV and brightness histograms excluding green background, plus apparent box aspect and crop-size flag','scope':'Appearance cues for identity only. No height, weight, ethnicity or other personal traits are inferred.','run_seconds':round(time.monotonic()-beg,2)});print('physical feature extraction complete',result.shape)
if __name__=='__main__':main()
