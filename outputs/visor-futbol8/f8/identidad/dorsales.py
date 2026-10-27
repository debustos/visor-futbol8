"""Jersey number regions and per-frame dorsal voting. Moved from automatic_core.py without changes."""
from __future__ import annotations
from collections import Counter,defaultdict
import cv2,numpy as np
from f8.core.io import crop

def number_region(person):
    """Locate dark jersey printing inside an orange shirt, without clipping a digit on purpose."""
    torso=crop(person,[0,0,person.shape[1],person.shape[0]],.17,.53,.15,.9)
    if not torso.size:return None
    h,s,v=cv2.split(cv2.cvtColor(torso,cv2.COLOR_BGR2HSV));mask=((h<25)&(s>65)&(v<145)).astype(np.uint8)*255
    n,labels,stats,centroids=cv2.connectedComponentsWithStats(mask)
    candidates=[]
    for st,center in zip(stats[1:],centroids[1:]):
        x,y,w,hh,area=st
        if area>=5 and hh>=max(5,torso.shape[0]*.20) and hh<=torso.shape[0]*.85 and w<torso.shape[1]*.7 and y<torso.shape[0]*.65:candidates.append((area,st,center))
    if not candidates:return None
    candidates.sort(key=lambda v:v[0],reverse=True);area,st,center=candidates[0];chosen=[st]
    for _,other,oc in candidates[1:]:
        if abs(oc[1]-center[1])<st[3]*.45 and abs(oc[0]-center[0])<st[3]*1.2 and .45<other[3]/st[3]<1.6:chosen.append(other)
    xa=max(0,min(v[0] for v in chosen)-3);ya=max(0,min(v[1] for v in chosen)-3);xb=min(torso.shape[1],max(v[0]+v[2] for v in chosen)+3);yb=min(torso.shape[0],max(v[1]+v[3] for v in chosen)+3)
    return torso[ya:yb,xa:xb]

def jersey_vote(readings,roster):
    """Readings from the same image are correlated and count as a single vote."""
    per_frame=defaultdict(dict)
    for r in readings:
        text=r['text']
        threshold=.75 if r.get('localized') else .90
        if text.isdigit() and str(int(text))==text and int(text) in roster and int(text)!=1 and r['score']>=threshold:
            per_frame[r['frame']][int(text)]=max(per_frame[r['frame']].get(int(text),0),r['score'])
    totals=Counter();supports=Counter()
    for frame,values in per_frame.items():
        if not values:continue
        # A clipped last digit must not beat a full number read from the same frame.
        values={n:v for n,v in values.items() if not any(len(str(m))>len(str(n)) and str(n) in str(m) for m in values)}
        number,score=max(values.items(),key=lambda v:v[1]);totals[number]+=score;supports[number]+=1
    if not totals:return None,{'state':'unknown','votes':{}}
    ordered=totals.most_common();winner,score=ordered[0];runner=ordered[1][1] if len(ordered)>1 else 0
    accepted=supports[winner]>=2 and score>=1.55 and score>runner*1.8
    longer_conflict=any(r.get('localized') and r['score']>=.30 and r['text'].isdigit() and str(int(r['text']))==r['text'] and int(r['text']) in roster and len(r['text'])>len(str(winner)) and str(winner) in r['text'] for r in readings)
    if longer_conflict:accepted=False
    return (winner if accepted else None),{'state':'accepted' if accepted else 'uncertain','candidate':winner,'distinct_frames':supports[winner],'vote_score':round(score,3),'votes':dict(totals),'possible_clipped_number':longer_conflict}
