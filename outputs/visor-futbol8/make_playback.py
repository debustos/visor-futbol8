"""Create a browser-compatible local playback copy; analysis continues to use original pixels."""
from pathlib import Path
import subprocess,time,json,cv2
import imageio_ffmpeg
from automatic_core import write_json
from runtime_context import ROOT,WORK,CACHE,SOURCE
def main():
    sourcecap=cv2.VideoCapture(SOURCE);source_frames=int(sourcecap.get(cv2.CAP_PROP_FRAME_COUNT));source_fps=sourcecap.get(cv2.CAP_PROP_FPS);sourcecap.release();duration=source_frames/source_fps
    media=ROOT/'media';media.mkdir(exist_ok=True);temp=media/'primera-compatible.tmp.mp4';dest=media/'primera-compatible.mp4';ffmpeg=imageio_ffmpeg.get_ffmpeg_exe();started=time.monotonic();last=-10
    # iPhone HLG/Dolby Vision compatible base layer -> SDR Rec.709 for ordinary browser playback.
    vf='zscale=w=1280:h=720:t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=reinhard:desat=0,zscale=t=bt709:m=bt709:r=limited,format=yuv420p'
    args=[ffmpeg,'-hide_banner','-loglevel','warning','-nostats','-y','-i',SOURCE,'-map','0:v:0','-map','0:a:0','-vf',vf,'-c:v','h264_nvenc','-preset','p4','-rc','vbr','-cq','27','-b:v','0','-c:a','copy','-fps_mode','passthrough','-movflags','+faststart','-progress','pipe:1',str(temp)]
    proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=open(CACHE/'playback-ffmpeg.log','w'),text=True)
    for line in proc.stdout:
        if line.startswith('out_time_us=') and line.split('=')[1].strip().lstrip('-').isdigit():
            seconds=int(line.split('=')[1])/1e6
            if time.monotonic()-last>8:
                status={'state':'processing','done_seconds':round(seconds,2),'total_seconds':duration,'elapsed':round(time.monotonic()-started,1)};write_json(ROOT/'automatic/playback-status.json',status);print(json.dumps(status),flush=True);last=time.monotonic()
    if proc.wait()!=0:raise RuntimeError('Browser copy encoding failed; inspect work/playback-ffmpeg.log')
    cap=cv2.VideoCapture(str(temp));metadata={'width':int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),'height':int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),'frames':int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),'fps':cap.get(cv2.CAP_PROP_FPS),'bytes':temp.stat().st_size,'codec':'H264 8bit SDR + source AAC audio','source':SOURCE,'frame_timestamps':'passed through; source variable-frame timestamps','purpose':'browser playback only; detection uses original pixels','run_seconds':round(time.monotonic()-started,2)};cap.release()
    if metadata['frames']!=source_frames or metadata['width']!=1280:raise RuntimeError(f'Playback verification failed: {metadata}')
    temp.replace(dest);write_json(ROOT/'automatic/playback-metadata.json',metadata);write_json(ROOT/'automatic/playback-status.json',{'state':'complete',**metadata});print(json.dumps(metadata),flush=True)
if __name__=='__main__':main()
