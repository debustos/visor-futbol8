"""Adaptive native-frame ball measurements, with a reverse pass and streaming I/O.

Source-scoped references are never read by window selection or tracking. Human goal
annotations are for evaluation only. Existing identities and review IDs are preserved.
"""
from pathlib import Path
from bisect import bisect_left
import argparse,json,time,os,sys,hashlib,uuid,cv2,numpy as np
from automatic_core import Detector,infer_possession,foot_contacts,kit,iou,write_json,project
from pitch_geometry import recover_matrix
from refine_ball import FootballBall
from ball_tracker import MeasuredBallTracker
from pose_contacts import PoseDetector,attach_poses
from runtime_context import ROOT,CACHE,SOURCE,WORK


def iter_records(path):
    decoder=json.JSONDecoder();buffer='';started=False;ended=False
    with Path(path).open(encoding='utf-8-sig') as stream:
        while True:
            chunk=stream.read(1048576)
            if not chunk and not buffer.strip():break
            buffer+=chunk
            while True:
                buffer=buffer.lstrip()
                if not started:
                    if not buffer:break
                    if buffer[0]!='[':raise ValueError('Records must be a JSON array')
                    buffer=buffer[1:];started=True;continue
                if buffer.startswith(','):buffer=buffer[1:];continue
                if buffer.startswith(']'):buffer=buffer[1:];ended=True;break
                if ended or not buffer:break
                try:row,end=decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    if not chunk:raise ValueError('Incomplete records file')
                    break
                yield row;buffer=buffer[end:]
            if ended:
                if buffer.strip() or stream.read().strip():raise ValueError('Trailing data in records file')
                return
            if not chunk:raise ValueError('Incomplete records file')
    if not ended:raise ValueError('Missing final array delimiter')


def merge_spans(spans):
    out=[]
    for a,b in sorted(spans):
        if out and a<=out[-1][1]+.2:out[-1][1]=max(b,out[-1][1])
        else:out.append([a,b])
    return out


def automatic_windows(path,duration,temporal):
    spans=[];previous=None
    for r in iter_records(path):
        b=r.get('ball');t=r['time']
        if b and b.get('center') and b.get('confidence',0)>=.4:
            if previous:
                dt=t-previous['time'];pairs=[];old={str(p['id']):p for p in previous['tracks']}
                for p in r['tracks']:
                    q=old.get(str(p['id']))
                    if q and q.get('box') and p.get('box'):
                        pairs.append(np.array([(p['box'][0]+p['box'][2])/2,p['box'][3]])-[(q['box'][0]+q['box'][2])/2,q['box'][3]])
                camera=np.median(pairs,axis=0) if len(pairs)>=3 else np.zeros(2)
                speed=np.linalg.norm(np.array(b['center'])-previous['ball']['center']-camera)/max(dt,.001)
                if .02<dt<=.25 and 150<speed<2200 and not foot_contacts(r):spans.append((max(0,t-1.2),min(duration,t+1.2)))
            previous=r
        else:previous=None
    action_file=ROOT/'automatic/actions.json'
    if action_file.exists():
        for e in json.loads(action_file.read_text(encoding='utf8')):
            if e.get('kind') in ('pass','recovery','turnover','shot'):
                spans.append((max(0,e.get('evidence_start',e['time']-1)),min(duration,e.get('evidence_end',e['time']+1))))
    for e in temporal:
        if e['class'] in ('Goal','Shots on target','Shots off target','Foul','Clearance'):spans.append((max(0,e['time']-2),min(duration,e['time']+2)))
    merged=merge_spans(spans);parts=[]
    for a,b in merged:
        start=a
        while start<b:
            parts.append([start,min(b,start+2.4)]);start+=2
    return merged,parts


def associated_tracks(img,detections,nearby,frame):
    result=[];used=set()
    for j,d in enumerate(detections):
        k,score=kit(img,d['box'])
        if k not in ('orange','opponent','keeper') or d['box'][3]-d['box'][1]<30:continue
        opts=sorted([(iou(d['box'],b['box']),b) for b in nearby['tracks'] if b.get('box') and b.get('kit')==k],key=lambda q:-q[0])
        good=opts and opts[0][0]>.5 and (len(opts)==1 or opts[0][0]-opts[1][0]>.15) and str(opts[0][1]['id']) not in used
        old=opts[0][1] if good else {};b={**d,'id':old.get('id',f'N{frame}-{j}'),'kit':k,'kit_score':score,'position':None,'player_id':old.get('player_id'),'association':'native_measured_unique_iou' if good else 'unassigned'}
        for key in ('person_track_id','context_epoch','segment_id','identity','identity_evidence','dorsal_guard'):
            if key in old:b[key]=old[key]
        if good:used.add(str(old['id']))
        result.append(b)
    return result


def consensus(forward,backward):
    if forward and backward:
        diameter=max(forward['box'][2]-forward['box'][0],backward['box'][2]-backward['box'][0],6)
        if np.linalg.norm(np.array(forward['center'])-backward['center'])>max(8,diameter*.8):return None
        chosen=max((forward,backward),key=lambda b:(b.get('measurement')=='neural_detection',b['confidence']))
        return {**chosen,'tracking_consensus':'bidirectional'}
    b=forward or backward
    if b is None:return None
    return {**b,'tracking_consensus':'forward_only' if forward else 'backward_only'}


def analyze_span(cap,detector,people,pose,base,start,end,fps,stats):
    first=round(start*fps);last=min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT))-1,round(end*fps));cap.set(cv2.CAP_PROP_POS_FRAMES,first);tracker=MeasuredBallTracker();frames=[];rows=[];byframe={r['frame']:r for r in base};times=[r['time'] for r in base];last_full=-100
    for frame in range(first,last+1):
        ok,img=cap.read()
        if not ok:raise RuntimeError(f'Cannot decode native source frame {frame}')
        t=frame/fps;prediction=tracker.predict(img,t);old=byframe.get(frame);candidates=list(old.get('ball_candidates',[])) if old else []
        if old and old.get('ball'):candidates.append(old['ball'])
        if prediction is not None and frame%2==0:
            size=320 if tracker.diameter<12 else 640;x=int(np.clip(prediction[0]-size/2,0,img.shape[1]-size));y=int(np.clip(prediction[1]-size/2,0,img.shape[0]-size));candidates+=detector(img,[(x,y,x+size,y+size)]);stats['local_detector_calls']+=1
        elif prediction is None and t-last_full>=.19:
            candidates+=detector(img);last_full=t;stats['full_detector_calls']+=1
        idx=min(len(base)-1,bisect_left(times,t));near=min(base[max(0,idx-1):idx+1],key=lambda r:abs(r['time']-t));C=recover_matrix(near)
        selected=tracker.update(img,t,candidates,C=C,prediction=prediction)
        # Bound replay to 2.4 seconds. Both directions use original decoded pixels.
        frames.append(img);rows.append({'frame':frame,'time':round(t,4),'forward':selected,'candidates':candidates,'old':old,'C':C})
    backward=MeasuredBallTracker()
    for index in range(len(rows)-1,-1,-1):
        row=rows[index];img=frames[index];time_reverse=(len(rows)-1-index)/fps;pred=backward.predict(img,time_reverse);b=backward.update(img,time_reverse,row['candidates'],C=row['C'],prediction=pred);row['backward']=b
    output=[]
    for index,row in enumerate(rows):
        ball=consensus(row['forward'],row['backward']);conflict=bool(row['forward'] and row['backward'] and ball is None);old=row.pop('old');t=row['time'];frame=row['frame']
        if old:
            r=dict(old)
            if ball:r['old_ball']=old.get('ball');r['ball']={**ball,'time':t}
            elif conflict:r['old_ball']=old.get('ball');r['ball']=None;r['ball_tracking_conflict']=True
        elif ball:
            img=frames[index];idx=min(len(base)-1,bisect_left(times,t));near=min(base[max(0,idx-1):idx+1],key=lambda r:abs(r['time']-t));tracks=associated_tracks(img,people(img)[0],near,frame);stats['native_person_calls']+=1
            C=recover_matrix(near)
            if C is not None:
                for b in tracks:
                    p=project(C,[[(b['box'][0]+b['box'][2])/2,b['box'][3]]])
                    if p is not None and -8<=p[0,0]<=108 and -8<=p[0,1]<=108:b['position']=p[0].round(4).tolist()
            r={'frame':frame,'time':t,'tracks':tracks,'ball':{**ball,'time':t},'calibration':near.get('calibration',{}),'geometry':near.get('geometry',{}),'native_ball':True}
        else:continue
        if ball and pose is not None and frame%3==0 and any(np.linalg.norm(np.array(ball['center'])-[(b['box'][0]+b['box'][2])/2,b['box'][3]])<.5*(b['box'][3]-b['box'][1]) for b in r['tracks']):
            img=frames[index];x,y=ball['center'];x=int(np.clip(x-320,0,img.shape[1]-640));y=int(np.clip(y-450,0,img.shape[0]-640));stats['pose_calls']+=1;stats['assigned_poses']+=attach_poses(r['tracks'],pose(img,(x,y,x+640,y+640)))
        if ball and ball.get('measurement')=='compact_image_component' and foot_contacts(r):
            r['ball_component_proposal']=r['ball'];r['ball']=old.get('ball') if old else None
        r['ball_candidates']=row['candidates'];r['possession']=infer_possession(r);output.append(r)
    stats['native_frames_examined']+=len(rows);stats['measured_ball_frames']+=sum(bool(r.get('ball')) for r in output)
    return output


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--records',default=str(CACHE/'recovery-v5/records-v5.json'));parser.add_argument('--output');parser.add_argument('--windows');parser.add_argument('--quality');parser.add_argument('--no-pose',action='store_true');parser.add_argument('--pose',action='store_true',help='Experimental ankle proposals; disabled by default');parser.add_argument('--resume',action=argparse.BooleanOptionalAction,default=True);parser.add_argument('--status');args=parser.parse_args();source=Path(args.records);metadata=json.loads((ROOT/'automatic/metadata.json').read_text(encoding='utf8'));duration=metadata['duration'];fps=metadata['source_fps'];temporal=json.loads((ROOT/'automatic/temporal-candidates.json').read_text(encoding='utf8'));started=time.monotonic()
    if args.windows:
        merged=json.loads(Path(args.windows).read_text(encoding='utf8'));parts=[]
        for a,b in merged:
            parts.extend([[s,min(b,s+2.4)] for s in np.arange(a,b,2)])
    else:merged,parts=automatic_windows(source,duration,temporal)
    cap=cv2.VideoCapture(SOURCE);ball=FootballBall();people=Detector(WORK/'yolo11s.onnx');pose=PoseDetector() if args.pose and not args.no_pose else None;stats={'version':11,'native_frames_examined':0,'measured_ball_frames':0,'local_detector_calls':0,'full_detector_calls':0,'native_person_calls':0,'pose_calls':0,'assigned_poses':0,'windows':merged,'source':SOURCE,'source_key':metadata.get('source_key'),'native_source_fps':fps,'run_seconds':0};replacements={};status=Path(args.status) if args.status else ROOT/'automatic/native-ball-status.json'
    def file_signature(path):
        path=Path(path);st=path.stat();return {'path':str(path.resolve()),'size':st.st_size,'mtime_ns':st.st_mtime_ns}
    input_signature=file_signature(source);video_signature=file_signature(SOURCE)
    code_signature=hashlib.sha256(b''.join((Path(__file__).parent/n).read_bytes() for n in ('native_ball.py','ball_tracker.py','automatic_core.py','refine_ball.py','pitch_geometry.py','pose_contacts.py'))).hexdigest()
    signature={'records':input_signature,'video':video_signature,'code':code_signature,'windows':hashlib.sha256(json.dumps(parts).encode()).hexdigest(),'pose':bool(pose)}
    checkpoint=CACHE/'native-ball-checkpoint.json';checkpoint_meta=CACHE/'native-ball-checkpoint-meta.json';resume_done=0
    stats['run_id']=uuid.uuid4().hex;stats['source_fingerprint']=video_signature
    if args.resume and checkpoint.exists() and checkpoint_meta.exists():
        saved=json.loads(checkpoint_meta.read_text(encoding='utf8'))
        if saved.get('signature')==signature and saved.get('data_sha256')==hashlib.sha256(checkpoint.read_bytes()).hexdigest():
            replacements={r['frame']:r for r in iter_records(checkpoint)};stats=saved['stats'];resume_done=saved['done'];started-=saved.get('elapsed_seconds',0)
            print(json.dumps({'stage':'native_ball','resumed_windows':resume_done,'total':len(parts)}),flush=True)
    stream=iter(iter_records(source));pending=next(stream,None);buffer=[]
    for index,(start,end) in enumerate(parts):
        if index<resume_done:continue
        buffer=[r for r in buffer if r['time']>=start-.2]
        while pending is not None and pending['time']<=end+.2:
            if pending['time']>=start-.2:buffer.append(pending)
            pending=next(stream,None)
        if not buffer:continue
        found=analyze_span(cap,ball,people,pose,buffer,start,end,fps,stats)
        for r in found:
            old=replacements.get(r['frame'])
            if old is None or r.get('ball') and (not old.get('ball') or r['ball'].get('tracking_consensus')=='bidirectional'):replacements[r['frame']]=r
        progress={'state':'processing','stage':'native_ball','done':index+1,'total':len(parts),'progress':round(95*(index+1)/max(1,len(parts)),1),'elapsed_seconds':round(time.monotonic()-started,1),'measured_ball_frames':stats['measured_ball_frames'],'worker_pid':os.getpid(),'source_key':metadata.get('source_key'),'run_id':stats['run_id']};write_json(status,progress);print(json.dumps(progress),flush=True)
        # Checkpoint only the changed windows. Original source remains immutable.
        if index%10==0:
            write_json(checkpoint,list(replacements.values()));write_json(checkpoint_meta,{'signature':signature,'done':index+1,'stats':stats,'elapsed_seconds':time.monotonic()-started,'data_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest()})
    write_json(status,{'state':'processing','stage':'saving_native_ball','progress':96,'done':len(parts),'total':len(parts)})
    cap.release();output=Path(args.output) if args.output else source;temp=output.with_suffix('.native.tmp');ordered=sorted(replacements);cursor=0
    with temp.open('w',encoding='utf8') as target:
        target.write('[');first=True
        def put(r):
            nonlocal first
            if not first:target.write(',')
            target.write(json.dumps(r,ensure_ascii=False,allow_nan=False,separators=(',',':')));first=False
        for old in iter_records(source):
            while cursor<len(ordered) and ordered[cursor]<old['frame']:put(replacements[ordered[cursor]]);cursor+=1
            if cursor<len(ordered) and ordered[cursor]==old['frame']:put(replacements[ordered[cursor]]);cursor+=1
            else:put(old)
        while cursor<len(ordered):put(replacements[ordered[cursor]]);cursor+=1
        target.write(']')
    if file_signature(source)!=input_signature or file_signature(SOURCE)!=video_signature:raise RuntimeError('El vídeo o los registros cambiaron durante el análisis; no se publican resultados mezclados.')
    temp.replace(output);stats['run_seconds']=round(time.monotonic()-started,2);stats['added_or_revisited_frames']=len(replacements);stats['unique_native_ball_measurements']=sum(bool(r.get('ball') and r['ball'].get('measurement')) for r in replacements.values());stats['unique_tracking_conflicts']=sum(bool(r.get('ball_tracking_conflict')) for r in replacements.values());stats['components_rejected_at_feet']=sum(bool(r.get('ball_component_proposal')) for r in replacements.values());stats['window_seconds']=round(sum(b-a for a,b in merged),2);stats['policy']='Adaptive native measurements and reverse image search; no reference goal read, no synthetic ball centers, prior names and manual review records preserved. Original decoded pixels in both directions; replay windows bounded to 2.4 seconds.';write_json(Path(args.quality) if args.quality else ROOT/'automatic/native-ball-quality.json',stats);write_json(status,{'state':'complete',**stats,'progress':100});print(json.dumps(stats),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        status_path=Path(sys.argv[sys.argv.index('--status')+1]) if '--status' in sys.argv else ROOT/'automatic/native-ball-status.json'
        prior=json.loads(status_path.read_text(encoding='utf8')) if status_path.exists() else {}
        write_json(status_path,{**prior,'state':'failed','error':str(error)[:600],'worker_pid':os.getpid()});raise
