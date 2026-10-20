"""Reject implausible ball jumps during measured free flight; never interpolate."""
from pathlib import Path
import argparse,json,math,numpy as np
from automatic_core import infer_possession,foot_contacts,project,write_json
from pitch_geometry import recover_matrix
from identity_recovery import camera_offsets
from runtime_context import ROOT,CACHE


def refine(records):
    offsets=camera_offsets(records);history=[];examined=changed=rejected=0;before=sum(bool(r.get('ball')) for r in records)
    for r in records:
        t=r['time'];original=r.get('ball');prediction=None;previous=None
        if len(history)>=2:
            a,b=history[-2:];dt=b['time']-a['time'];gap=t-b['time']
            if .015<dt<=.25 and .01<gap<=.4 and a['free'] and b['free']:
                velocity=(b['point']-a['point'])/dt
                if np.linalg.norm(velocity)>35:prediction=b['point']+velocity*gap+offsets[t];previous=b
        if prediction is not None:
            examined+=1;C=recover_matrix(r);candidates=list(r.get('ball_candidates',[]))
            if original:candidates.append(original)
            options=[]
            for c in candidates:
                x1,y1,x2,y2=c['box'];width=x2-x1;height=y2-y1
                if min(width,height)<3 or max(width,height)>48 or max(width,height)/min(width,height)>2:continue
                center=np.array([(x1+x2)/2,(y1+y2)/2]);error=float(np.linalg.norm(center-prediction))
                limit=max(40,previous['height']*3,(t-previous['time'])*500)
                if error>limit:continue
                pos=project(C,[center]) if C is not None else None
                if pos is not None and not(-3<=pos[0,0]<=103 and -4<=pos[0,1]<=104):continue
                shape=abs(math.log(height/max(previous['height'],1)))
                score=c['confidence']-.004*error-.2*shape
                value={**c,'center':center.round(2).tolist(),'position':pos[0].round(3).tolist() if pos is not None else None,'time':t,'continuity':'measured_free_flight','prediction_error_pixels':round(error,3)}
                if not any(np.linalg.norm(center-np.array(v[1]['center']))<4 for v in options):options.append((score,value))
            options.sort(key=lambda v:-v[0]);chosen=options[0][1] if options and (len(options)==1 or options[0][0]-options[1][0]>=.04) else None
            if original and not chosen:rejected+=1
            if chosen and (not original or np.linalg.norm(np.array(chosen['center'])-np.array(original['center']))>4):changed+=1
            r['ball']=chosen
        r['possession']=infer_possession(r)
        ball=r.get('ball')
        if ball and ball.get('center') and ball.get('confidence',0)>=.3:
            history.append({'time':t,'point':np.array(ball['center'])-offsets[t],'height':ball['box'][3]-ball['box'][1],'free':not foot_contacts(r)})
            history=history[-2:]
        elif history and t-history[-1]['time']>.4:history=[]
    return {'version':6,'examined_free_flight_frames':examined,'reselected_measured_candidates':changed,'implausible_jumps_rejected':rejected,'ball_samples_before':before,'ball_samples_after':sum(bool(r.get('ball')) for r in records),'policy':'Prediction only scores existing measured detections; missing detections remain missing. Foot controls and stationary balls are not extrapolated.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--records',default=str(CACHE/'dense-v3.json'));p.add_argument('--output');p.add_argument('--fallback-records');a=p.parse_args();source=Path(a.records);records=json.loads(source.read_text(encoding='utf-8-sig'))
    if a.fallback_records:
        fallback={r['frame']:r for r in json.loads(Path(a.fallback_records).read_text(encoding='utf-8-sig'))}
        for r in records:
            old=fallback.get(r['frame'])
            if old and abs(old['time']-r['time'])<.00011 and old.get('ball'):r.setdefault('ball_candidates',[]).append(old['ball'])
    quality=refine(records);write_json(Path(a.output) if a.output else source,records);write_json(ROOT/'automatic/ball-continuity-quality.json',quality);print(json.dumps(quality),flush=True)
if __name__=='__main__':main()
