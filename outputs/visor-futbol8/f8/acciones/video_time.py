"""Use decoded presentation timestamps, never average FPS as a video clock."""
import math


def presentation_time(cap,previous=None):
    import cv2
    t=float(cap.get(cv2.CAP_PROP_POS_MSEC))/1000
    if not math.isfinite(t) or t<0 or (previous is not None and t<=previous):
        raise ValueError('Video presentation timestamps unavailable or non-monotonic; refusing frame/FPS fallback')
    return t


def sample_video(cap,limit=None,sampling_fps=2,orientation='display'):
    """Decode the entire source sequentially; retain actual frame indices and PTS."""
    import cv2
    if orientation not in ('display','encoded'):raise ValueError('Unknown orientation mode')
    rotation=cap.get(cv2.CAP_PROP_ORIENTATION_META)
    if orientation=='encoded' and not cap.set(cv2.CAP_PROP_ORIENTATION_AUTO,0):raise ValueError('Decoder cannot disable autorotation')
    if limit is not None and (not math.isfinite(limit) or limit<=0):raise ValueError('limit must be positive')
    if sampling_fps<=0:raise ValueError('sampling_fps must be positive')
    images=[];times=[];frames=[];previous=None;target=0.;frame=0;fps=cap.get(cv2.CAP_PROP_FPS);max_error=0
    while cap.grab():
        t=presentation_time(cap,previous);previous=t
        if fps>0:max_error=max(max_error,abs(t-frame/fps))
        if limit is not None and t>=limit:break
        if t+1e-8>=target:
            ok,img=cap.retrieve()
            if not ok:raise RuntimeError(f'Cannot retrieve frame {frame}')
            images.append(cv2.resize(img,(398,224))[:,:,::-1].copy());times.append(t);frames.append(frame)
            target=(math.floor(t*sampling_fps)+1)/sampling_fps
        frame+=1
    if not images:raise ValueError('No decodable video samples')
    expected=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if limit is None and expected>0 and frame!=expected:raise RuntimeError(f'Video frame count mismatch: {frame}/{expected} frames')
    return images,times,frames,{'decoded_frames':frame,'last_decoded_timestamp':previous,'orientation':orientation,'rotation_metadata_degrees':rotation,'max_average_fps_error_seconds':max_error,'timestamp_basis':'source_presentation_time','full_source':limit is None,'status':'complete'}


def cached_samples(source,cache,limit=None,orientation='display'):
    import cv2,json,hashlib,numpy as np
    from pathlib import Path
    source=Path(source);cache=Path(cache);stat=source.stat()
    signature={'source':str(source.resolve()),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'limit':limit,'orientation':orientation,'sampler_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    meta=cache/'samples.json';pixels=cache/'images.npy'
    stored=json.loads(meta.read_text(encoding='utf8')) if meta.exists() else {}
    if stored.get('signature')==signature and pixels.exists():
        images=np.load(pixels,mmap_mode='r')
        if len(images)==len(stored['timestamps']):return images,stored['timestamps'],stored['source_frames'],stored['timing'],True
    cap=cv2.VideoCapture(str(source))
    try:images,times,frames,timing=sample_video(cap,limit,orientation=orientation)
    finally:cap.release()
    cache.mkdir(parents=True,exist_ok=True)
    saved=np.lib.format.open_memmap(pixels,mode='w+',dtype=np.uint8,shape=(len(images),224,398,3))
    for i,img in enumerate(images):saved[i]=img
    saved.flush();del saved
    meta.write_text(json.dumps({'signature':signature,'timestamps':times,'source_frames':frames,'timing':timing}),encoding='utf8')
    return images,times,frames,timing,False


def candidate_windows(proposals,duration):
    from f8.acciones.proposal_review import checked_proposals,SHOT_CLASSES
    valid,_=checked_proposals(proposals)
    return [[max(0,e['evidence_start']),min(duration,e['evidence_end'])] for e in valid if e['class'] in SHOT_CLASSES|{'Foul'} and e['time']<duration]


def merge_windows(windows):
    result=[]
    for a,b in sorted(windows):
        if b<=a:continue
        if result and a<=result[-1][1]+.2:result[-1][1]=max(b,result[-1][1])
        else:result.append([a,b])
    return result


def audit_source(source):
    """One isolated timing index, also usable by independent clip evaluators."""
    import cv2,time
    from pathlib import Path
    started=time.monotonic();cap=cv2.VideoCapture(str(source));timestamps=[];previous=None
    fps=cap.get(cv2.CAP_PROP_FPS);expected=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    try:
        while cap.grab():
            previous=presentation_time(cap,previous);timestamps.append(previous)
            if len(timestamps)%10000==0:print(f'Indexed {len(timestamps)}/{expected} frames',flush=True)
    finally:cap.release()
    if not timestamps or (expected and len(timestamps)!=expected):raise RuntimeError('Incomplete timestamp index')
    stat=Path(source).stat()
    return {'source':str(Path(source).resolve()),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'source_fps':fps,'frames':len(timestamps),'timestamp_basis':'source_presentation_time','timestamps':timestamps,'max_average_fps_error_seconds':max(abs(t-i/fps) for i,t in enumerate(timestamps)) if fps>0 else None,'run_seconds':round(time.monotonic()-started,3)}


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    result=audit_source(args.source);output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result),encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k!='timestamps'}))
