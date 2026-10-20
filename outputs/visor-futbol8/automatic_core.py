"""Automatic football analysis primitives. Abstention is a result, never a fabricated zero."""
from __future__ import annotations
import json,math
from collections import Counter,defaultdict
from pathlib import Path
import cv2,numpy as np
from scipy.optimize import linear_sum_assignment

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8');temp.replace(path)

def ort_session(path,gpu=True):
    import onnxruntime as ort
    options=ort.SessionOptions();options.intra_op_num_threads=4;options.enable_mem_pattern=False;options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    providers=['DmlExecutionProvider','CPUExecutionProvider'] if gpu and 'DmlExecutionProvider' in ort.get_available_providers() else ['CPUExecutionProvider']
    return ort.InferenceSession(str(path),options,providers=providers)

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

def crop(img,box,a=0,b=1,c=0,d=1):
    x1,y1,x2,y2=box;h=y2-y1;w=x2-x1
    return img[max(0,round(y1+a*h)):min(img.shape[0],round(y1+b*h)),max(0,round(x1+c*w)):min(img.shape[1],round(x1+d*w))]

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

def iou(a,b):
    left=max(a[0],b[0]);top=max(a[1],b[1]);right=min(a[2],b[2]);bottom=min(a[3],b[3]);intersection=max(0,right-left)*max(0,bottom-top)
    return intersection/max((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection,1)

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

def foot_contacts(record):
    """Measured contact with a reachable foot region; projection is optional.

    This is a contact proposal, not proof of control. The pass engine must also
    observe release and a travelling ball before crediting a transfer.
    """
    ball=record.get('ball')
    if not ball or not ball.get('center'):return []
    candidates=[]
    for p in record['tracks']:
        if p.get('kit') not in ('orange','opponent','keeper') or not p.get('box'):continue
        x1,y1,x2,y2=p['box'];x,y=ball['center'];height=max(y2-y1,1)
        # An extended foot can lie beyond the midpoint of the person box.
        dx=max(x1-.15*height-x,0,x-x2-.15*height)
        dy=abs(y-y2)
        distance=math.hypot(dx,dy)/height
        center_distance=math.hypot(x-(x1+x2)/2,y-y2)/height
        if distance<.25 and y>y1+.68*height and center_distance<.65:
            candidates.append((distance+.12*center_distance,p,distance))
    if any(p.get('keypoints') for p in record['tracks']):
        from pose_contacts import ankle_contacts
        byid={str(p['id']):(score,p,distance) for score,p,distance in candidates}
        for score,p,distance in ankle_contacts(record):
            old=byid.get(str(p['id']))
            if old is None or score<old[0]:byid[str(p['id'])]=(score,p,distance)
        candidates=list(byid.values())
    candidates.sort(key=lambda v:v[0])
    return candidates

def infer_possession(record):
    candidates=foot_contacts(record)
    if not candidates or (len(candidates)>1 and candidates[1][0]-candidates[0][0]<.06):return None
    _,p,distance=candidates[0]
    method='reachable_foot_region'
    if p.get('keypoints'):
        from pose_contacts import ankle_contacts
        if any(q['id']==p['id'] and abs(d-distance)<1e-5 for _,q,d in ankle_contacts(record)):method='measured_ankle_contact'
    return {'track_id':p['id'],'kit':p['kit'],'distance':round(distance,3),'method':method}

def infer_changes(players,records,start_seconds=30):
    """Visibility cannot prove a substitution. Report candidates, require observed border crossing."""
    presence=defaultdict(list)
    for r in records:
        for b in r['tracks']:
            if b.get('player_id') and b.get('position') is not None and 0<=b['position'][0]<=100 and 0<=b['position'][1]<=100:presence[b['player_id']].append((r['time'],b['position'],b['id']))
    starters=[];changes=[]
    for pid,rows in presence.items():
        early=[r for r in rows if r[0]<=start_seconds]
        if len(early)>=5:starters.append({'player_id':pid,'first_seen':early[0][0],'last_seen_initial':early[-1][0],'state':'probable','reason':'Repeated automatic identity within the opening recording interval; kickoff time is not certified.'})
        previous=rows[0]
        for row in rows[1:]:
            gap=row[0]-previous[0]
            if gap>25:
                before_edge=min(previous[1][0],100-previous[1][0])<4;after_edge=min(row[1][0],100-row[1][0])<4
                if before_edge or after_edge:changes.append({'player_id':pid,'time_start':previous[0],'time_end':row[0],'type':'possible_return','state':'uncertain','reason':'Border visibility gap; not sufficient to certify a substitution.'})
            previous=row
    starters.sort(key=lambda v:v['first_seen'])
    return {'expected':8,'identified_candidates':starters,'state':'probable' if len(starters)==8 else 'incomplete','unidentified_slots':max(0,8-len(starters)),'substitutions':[],'visibility_alerts':changes,'reason':'No substitution is asserted from disappearance alone.'}

def action_candidates(records):
    """Conservative ownership transitions. The result remains an estimate with video evidence."""
    events=[];last=None;last_seen=None;active=None;run=[];used=set()
    for r in records:
        o=r.get('possession')
        if not o:
            if last_seen is not None and r['time']-last_seen>2.2:last=None;active=None;run=[]
            continue
        last_seen=r['time'];key=o['track_id']
        if active!=key:active=key;run=[]
        run.append(r)
        run=[v for v in run if r['time']-v['time']<=.9]
        if len(run)<3 and (last is None or last['track_id']!=key):continue
        b=next((b for b in r['tracks'] if b['id']==key),None)
        if b is None:continue
        current={'time':r['time'],'track_id':key,'kit':o['kit'],'player_id':b.get('player_id'),'position':b['position'],'ball':r['ball']}
        if last and last['track_id']!=key and r['time']-last['time']<=2.2:
            marker=(last['track_id'],key,round(r['time'],1))
            if marker not in used:
                used.add(marker);distance=np.linalg.norm(np.array(current['position'])-last['position']);same=last['kit'] in ('orange','keeper') and current['kit'] in ('orange','keeper');switch=(last['kit']=='opponent')!=(current['kit']=='opponent')
                common={'time':run[0]['time'],'evidence_start':max(0,last['time']-.8),'evidence_end':r['time']+.8,'state':'estimated','score':round(min(last['ball']['confidence'],r['ball']['confidence']),3),'method':'Three sampled observations per owner, unambiguous ball proximity, ownership transition within 2.2 seconds.','source_track':last['track_id'],'target_track':key}
                if same and distance>3 and last['player_id'] and current['player_id'] and last['player_id']!=current['player_id']:
                    events.append({**common,'kind':'pass','player_id':last['player_id'],'receiver_id':current['player_id'],'outcome':'complete'})
                    if current['position'][1]<18 and 25<current['position'][0]<75 and 18<last['position'][1]<82:events.append({**common,'kind':'ball_into_box','player_id':last['player_id'],'outcome':'unknown','state':'candidate','method':'Entry into an approximate box region; field dimensions not verified.'})
                elif switch:
                    if last['kit'] in ('orange','keeper') and last['player_id']:
                        events.append({**common,'kind':'turnover','player_id':last['player_id'],'outcome':'unknown'})
                        # A moving ball transferred over distance is a pass attempt candidate, not automatically every loss.
                        if distance>3 and current['time']-last['time']>.4:events.append({**common,'kind':'pass','player_id':last['player_id'],'receiver_id':None,'outcome':'incomplete','state':'candidate','method':'Ownership changed teams after a moving ball; distinguishes an attempt only as a candidate.'})
                    if current['kit'] in ('orange','keeper') and current['player_id']:events.append({**common,'kind':'recovery','player_id':current['player_id'],'outcome':'unknown'})
        last=current
    return events
