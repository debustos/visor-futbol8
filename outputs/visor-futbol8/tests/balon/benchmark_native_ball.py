"""Isolated CPU benchmark of native tracking; requires the existing video/models.

Run from outputs/visor-futbol8 with python -m tests.balon.benchmark_native_ball.
Only --output is written. Source records, videos and review databases are read-only.
"""
import argparse,hashlib,json,platform,statistics,subprocess,time,types
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
from f8.balon import ball_tracker,native_ball
from f8.balon.refine_ball import FootballBall
from f8.core.io import ort_session
from f8.deteccion.modelos import Detector
from f8.campo.pitch_geometry import recover_matrix


def quality(rows,labels):
    byframe={r['frame']:r for r in rows};counts=dict(correct=0,missed_visible=0,false_detections=0,unknown=0,annotated=0,published=0,visible=0)
    for label in labels:
        if label.get('unknown'):
            counts['unknown']+=1;continue
        counts['annotated']+=1;ball=byframe.get(label['frame'],{}).get('ball');center=label.get('center')
        counts['published']+=bool(ball);counts['visible']+=center is not None
        correct=bool(ball and center is not None and np.linalg.norm(np.array(ball['center'])-center)<=label['tolerance_pixels'])
        counts['correct']+=correct;counts['missed_visible']+=center is not None and not correct;counts['false_detections']+=bool(ball) and not correct
    counts['precision']=counts['correct']/counts['published'] if counts['published'] else None
    counts['recall']=counts['correct']/counts['visible'] if counts['visible'] else None
    counts['coverage']=counts['published']/counts['annotated'] if counts['annotated'] else None
    return counts


def replay_compare(args,baseline,windows,records):
    """Time tracker work alone with real pixels and cached measured candidates.

    Decode and calibration are outside the timer; variants alternate to reduce
    thermal/order bias. This is not an end-to-end inference time measurement.
    """
    report={'mode':'cached-detection-replay','opencv_threads':1,'repeats':args.repeats,'windows':[]};cap=cv2.VideoCapture(str(args.video))
    try:
        for window in windows:
            inputs=[]
            for row in records:
                if not window['start']<=row['time']<=window['end']:continue
                cap.set(cv2.CAP_PROP_POS_FRAMES,row['frame']);ok,img=cap.read()
                if not ok:raise RuntimeError('Cannot decode cached frame')
                candidates=list(row.get('ball_candidates',[]))
                if row.get('ball'):candidates.append(row['ball'])
                inputs.append((img,row['time'],candidates,recover_matrix(row)))
            results={'before':[],'after':[]};hashes={'before':[],'after':[]}
            for repeat in range(args.repeats):
                variants=[('before',baseline),('after',ball_tracker)]
                for name,module in variants if repeat%2==0 else variants[::-1]:
                    tracker=module.MeasuredBallTracker();camera_calls=0;camera=module.camera_step;output=[]
                    def counted_camera(previous,current):
                        nonlocal camera_calls
                        camera_calls+=1;return camera(previous,current)
                    cv2.setRNGSeed(0)
                    with patch.object(module,'camera_step',counted_camera):
                        begin=time.perf_counter()
                        for img,t,candidates,C in inputs:output.append(tracker.update(img,t,candidates,C))
                        elapsed=time.perf_counter()-begin
                    results[name].append({'seconds':elapsed,'camera_calls':camera_calls});hashes[name].append(hashlib.sha256(json.dumps(output,sort_keys=True,allow_nan=False).encode()).hexdigest())
            entry={'id':window['id'],'split':window['split'],'frames':len(inputs),'runs':results,'median_seconds':{name:statistics.median(r['seconds'] for r in runs) for name,runs in results.items()},'output_sha256':hashes,'equal_outputs':len(set(hashes['before']+hashes['after']))==1}
            report['windows'].append(entry);print(json.dumps(entry),flush=True)
    finally:cap.release()
    (args.output/'replay-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    if not all(w['equal_outputs'] for w in report['windows']):raise RuntimeError('Tracker outputs changed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('video','models','records','manifest','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--tracker-ref',help='Git revision of ball_tracker.py; omitted = working tree')
    p.add_argument('--compare-directory',type=Path,help='Require exact native output equality with a previous run')
    p.add_argument('--replay-compare',action='store_true',help='Compare both trackers using cached detections, without model inference')
    p.add_argument('--split',choices=('development','holdout','all'),default='all');p.add_argument('--repeats',type=int,default=3)
    args=p.parse_args()
    if args.repeats<1:p.error('--repeats must be positive')
    if args.compare_directory and args.compare_directory.resolve()==args.output.resolve():p.error('Comparison baseline and output must be different directories')
    args.output.mkdir(parents=True,exist_ok=True)
    protected=[args.video.resolve(),args.records.resolve(),*(args.models/n for n in ('football-ball-detection.onnx','yolo11s.onnx'))]
    if any(v.resolve().is_relative_to(args.output.resolve()) for v in protected):p.error('Output must be isolated from inputs')
    manifest=json.loads(args.manifest.read_text(encoding='utf8'));windows=[w for w in manifest['windows'] if args.split=='all' or w['split']==args.split]
    digest=hashlib.sha256()
    with args.video.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
    if digest.hexdigest()!=manifest['video_sha256']:p.error('Video does not match the annotation manifest')
    if not windows:p.error('No windows selected')
    records=[r for r in native_ball.iter_records(args.records) if any(w['start']-.2<=r['time']<=w['end']+.2 for w in windows)]
    tracker_module=ball_tracker
    if args.tracker_ref:
        source=subprocess.check_output(['git','show',args.tracker_ref+':outputs/visor-futbol8/f8/balon/ball_tracker.py'],text=True,encoding='utf8')
        tracker_module=types.ModuleType('baseline_ball_tracker');exec(compile(source,'baseline_ball_tracker.py','exec'),tracker_module.__dict__)
    else:source=Path(ball_tracker.__file__).read_text(encoding='utf8')
    cv2.setNumThreads(1)
    if args.replay_compare:
        if not args.tracker_ref:p.error('--replay-compare requires --tracker-ref')
        return replay_compare(args,tracker_module,windows,records)
    ball=FootballBall.__new__(FootballBall);ball.session=ort_session(args.models/'football-ball-detection.onnx',gpu=False);ball.name=ball.session.get_inputs()[0].name
    people=Detector(args.models/'yolo11s.onnx');cap=cv2.VideoCapture(str(args.video));fps=cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES,round(windows[0]['start']*fps));ok,img=cap.read()
    if not ok:raise RuntimeError('Cannot decode warmup frame')
    ball(img,[(0,0,640,640)]);people(img)
    report={'tracker_ref':args.tracker_ref or 'working-tree','tracker_sha256':hashlib.sha256(source.encode()).hexdigest(),'python':platform.python_version(),'opencv':cv2.__version__,'onnxruntime':__import__('onnxruntime').__version__,'providers':ball.session.get_providers(),'opencv_threads':1,'onnx_threads':4,'fps':fps,'resolution':[img.shape[1],img.shape[0]],'pose':False,'repeats':args.repeats,'video_sha256':digest.hexdigest(),'video_bytes':args.video.stat().st_size,'records_sha256':hashlib.sha256(args.records.read_bytes()).hexdigest(),'models_sha256':{n:hashlib.sha256((args.models/n).read_bytes()).hexdigest() for n in ('football-ball-detection.onnx','yolo11s.onnx')},'windows':[]}
    try:
        for window in windows:
            base=[r for r in records if window['start']-.2<=r['time']<=window['end']+.2];runs=[];hashes=[];last_rows=[]
            for repeat in range(args.repeats):
                stats={k:0 for k in ('local_detector_calls','full_detector_calls','native_person_calls','pose_calls','assigned_poses','native_frames_examined','measured_ball_frames')};camera_calls=0
                camera_step=tracker_module.camera_step
                def counted_camera(previous,current):
                    nonlocal camera_calls
                    camera_calls+=1;return camera_step(previous,current)
                cv2.setRNGSeed(0)
                with patch.object(native_ball,'MeasuredBallTracker',tracker_module.MeasuredBallTracker),patch.object(tracker_module,'camera_step',counted_camera):
                    begin=time.perf_counter();last_rows=native_ball.analyze_span(cap,ball,people,None,base,window['start'],window['end'],fps,stats);elapsed=time.perf_counter()-begin
                raw=json.dumps(last_rows,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'));hashes.append(hashlib.sha256(raw.encode()).hexdigest());runs.append({'seconds':elapsed,'camera_calls':camera_calls,**stats})
                print(json.dumps({'window':window['id'],'repeat':repeat,'seconds':round(elapsed,3),'camera_calls':camera_calls}),flush=True)
            (args.output/(window['id']+'-rows.json')).write_text(raw,encoding='utf8')
            entry={'id':window['id'],'split':window['split'],'start':window['start'],'end':window['end'],'median_seconds':statistics.median(r['seconds'] for r in runs),'runs':runs,'output_sha256':hashes,'stable':len(set(hashes))==1,'quality':quality(last_rows,window.get('labels',[]))}
            if args.compare_directory:
                prior=(args.compare_directory/(window['id']+'-rows.json')).read_text(encoding='utf8')
                entry['matches_baseline']=all(h==hashlib.sha256(prior.encode()).hexdigest() for h in hashes)
                entry['baseline_quality']=quality(json.loads(prior),window.get('labels',[]))
                if not entry['matches_baseline']:raise RuntimeError('Native outputs changed: '+window['id'])
            report['windows'].append(entry)
            (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    finally:cap.release()


if __name__=='__main__':main()
