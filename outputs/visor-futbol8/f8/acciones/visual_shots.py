"""Generate reviewable shot proposals from ball flight and visible goal posts."""
import argparse,json,time,hashlib
from bisect import bisect_left
from pathlib import Path
import cv2,numpy as np
from f8.balon.native_ball import iter_records
from f8.campo.pitch_geometry import recover_matrix
from f8.campo.goal_geometry import GoalImageTracker,mouth_point,approach_proposals
from f8.campo.proyeccion import project;from f8.core.io import write_json
from f8.core.runtime_context import ROOT,CACHE,SOURCE
from f8.core.paths import PACKAGE_DIR


def search_windows(records,duration):
    intervals=[]
    for r in records:
        b=r.get('ball')
        if not b or not b.get('center') or b.get('confidence',0)<.4:continue
        C=recover_matrix(r)
        if C is None:continue
        try:I=np.linalg.inv(C)
        except np.linalg.LinAlgError:continue
        near=False
        for end in (0,100):
            seed=project(I,[[42.5,end],[57.5,end]])
            if seed is None:continue
            width=np.linalg.norm(seed[1]-seed[0])
            if 80<=width<=1200 and np.linalg.norm(np.array(b['center'])-seed.mean(axis=0))<width*2.2:near=True
        if near:intervals.append([max(0,r['time']-.6),min(duration,r['time']+.6)])
    merged=[]
    for a,b in intervals:
        if merged and a<=merged[-1][1]+.2:merged[-1][1]=max(b,merged[-1][1])
        else:merged.append([a,b])
    return merged


def analyze(records,cap,fps,windows):
    times=[r['time'] for r in records];samples={0:[],100:[]};examined=0;cached_frames=0
    stat=Path(SOURCE).stat();signature={'source':str(Path(SOURCE).resolve()),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'code':hashlib.sha256((PACKAGE_DIR/'campo'/'goal_geometry.py').read_bytes()).hexdigest(),'views':hashlib.sha256((ROOT/'automatic/geometry-views.json').read_bytes()).hexdigest() if (ROOT/'automatic/geometry-views.json').exists() else None}
    cache=CACHE/'goal-mouth-views-v11.json';stored=json.loads(cache.read_text(encoding='utf8')) if cache.exists() else {};views=stored.get('views',{}) if stored.get('signature')==signature else {}
    for a,b in windows:
        trackers={e:GoalImageTracker(e) for e in samples};cap.set(cv2.CAP_PROP_POS_FRAMES,round(a*fps))
        for frame in range(round(a*fps),min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT))-1,round(b*fps))+1):
            key=str(frame);known=key in views
            if known or frame%3:
                if not cap.grab():raise RuntimeError(f'No se puede decodificar el fotograma {frame}')
                if frame%3:continue
                img=None;cached_frames+=1
            else:
                ok,img=cap.read()
                if not ok:raise RuntimeError(f'No se puede decodificar el fotograma {frame}')
            t=frame/fps;k=bisect_left(times,t);near=min(records[max(0,k-1):min(len(records),k+1)],key=lambda r:abs(r['time']-t));C=recover_matrix(near);examined+=1
            measured={}
            for end,tracker in trackers.items():
                goal=views[key].get(str(end)) if known else tracker.update(img,t,C)
                measured[str(end)]=goal
                if not goal:continue
                # Use actual measured balls within half a sampled frame; no interpolated ball.
                for r in records[bisect_left(times,t-.049):bisect_left(times,t+.05)]:
                    ball=r.get('ball')
                    if not ball or not ball.get('center') or ball.get('confidence',0)<.4 or r.get('ball_tracking_conflict'):continue
                    q=mouth_point(goal,ball['center'])
                    if q is not None:samples[end].append({'time':r['time'],'mouth':q.tolist(),'measurement':ball.get('measurement','neural_detection'),'goal_state':goal['state']})
            if not known:views[key]=measured
        write_json(cache,{'signature':signature,'views':views})
        print(json.dumps({'stage':'visual_shots','done_seconds':b,'total_seconds':windows[-1][1]}),flush=True)
    proposals=[]
    for end,ss in samples.items():
        unique={round(x['time'],4):x for x in ss};proposals+=approach_proposals(sorted(unique.values(),key=lambda x:x['time']),end)
    return sorted(proposals,key=lambda e:e['time']),{'sampled_goal_images':examined,'cached_goal_images':cached_frames,'goal_ball_samples':{str(e):len(s) for e,s in samples.items()},'windows':windows,'automatic_shots_certified':False,'automatic_goals_certified':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--records',default=str(CACHE/'recovery-v5/records-v5.json'));p.add_argument('--windows');p.add_argument('--output',default=str(ROOT/'automatic/visual-shot-candidates.json'));p.add_argument('--quality',default=str(ROOT/'automatic/visual-shot-quality.json'));args=p.parse_args()
    metadata=json.loads((ROOT/'automatic/metadata.json').read_text(encoding='utf8'));windows=json.loads(Path(args.windows).read_text(encoding='utf8')) if args.windows else search_windows(iter_records(args.records),metadata['duration']);rows=[r for r in iter_records(args.records) if any(a-.2<=r['time']<=b+.2 for a,b in windows)];cap=cv2.VideoCapture(SOURCE);started=time.monotonic();events,q=analyze(rows,cap,metadata['source_fps'],windows);cap.release();q.update(version=11,proposals=len(events),source=SOURCE,source_key=metadata.get('source_key'),run_seconds=round(time.monotonic()-started,2));write_json(Path(args.output),events);write_json(Path(args.quality),q);print(json.dumps(q),flush=True)
if __name__=='__main__':main()
