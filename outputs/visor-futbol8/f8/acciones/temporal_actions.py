"""E2E-Spot pretrained SoccerNet-v2 inference; candidates are not certified player statistics.
Upstream architecture and weights: https://github.com/jhong93/spot and e2e-spot-models.
"""
from pathlib import Path
import argparse,json,time,math,hashlib
import cv2,numpy as np,torch,timm
from torch import nn
from scipy.signal import find_peaks
from f8.core.io import write_json
from f8.acciones.vendor.spot.shift import make_temporal_shift
from f8.core.runtime_context import ROOT,WORK,CACHE,SOURCE
from f8.acciones.video_time import cached_samples
CLASSES=['Ball out of play','Clearance','Corner','Direct free-kick','Foul','Goal','Indirect free-kick','Kick-off','Offside','Penalty','Red card','Shots off target','Shots on target','Substitution','Throw-in','Yellow card','Yellow->red card']
class FC(nn.Module):
    def __init__(self,dim,n):super().__init__();self._fc_out=nn.Linear(dim,n)
    def forward(self,x):return self._fc_out(x)
class GRU(nn.Module):
    def __init__(self,dim,n):super().__init__();self._gru=nn.GRU(dim,dim,batch_first=True,bidirectional=True);self._fc_out=FC(2*dim,n);self._dropout=nn.Dropout()
    def forward(self,x):y,_=self._gru(x);return self._fc_out(self._dropout(y))
class Spot(nn.Module):
    def __init__(self,clip=100):
        super().__init__();features=timm.create_model('regnety_002',pretrained=False);dim=features.head.fc.in_features;features.head.fc=nn.Identity();make_temporal_shift(features,clip,is_gsm=True);self._features=features;self._feat_dim=dim;self._pred_fine=GRU(dim,18);self.clip=clip
    def forward(self,x):return self._pred_fine(self._features(x.reshape(-1,3,224,398)).reshape(1,self.clip,-1))
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default=SOURCE);p.add_argument('--limit',type=float);p.add_argument('--output',default=str(ROOT/'automatic'));p.add_argument('--weights',default=str(WORK/'e2e-spot/checkpoint_088.pt'));p.add_argument('--orientation',choices=['display','encoded'],default='display');a=p.parse_args();output=Path(a.output);torch.set_num_threads(5);cv2.setNumThreads(1)
    checkpoint=Path(a.weights)
    if not checkpoint.is_file():raise FileNotFoundError(f'E2E-Spot checkpoint unavailable: {checkpoint}')
    model=Spot().eval();weights=torch.load(checkpoint,map_location='cpu',weights_only=True);model.load_state_dict(weights,strict=True)
    started=time.monotonic();cap=cv2.VideoCapture(a.source);fps=cap.get(cv2.CAP_PROP_FPS);cap.release()
    images,timestamps,targets,timing,reused=cached_samples(a.source,CACHE/f'temporal-samples-{a.orientation}',a.limit,a.orientation)
    print(json.dumps({'stage':'temporal','sampled_frames':len(images),'sampling_cache_reused':reused,'elapsed':round(time.monotonic()-started,2)}),flush=True)
    samplefps=2.;values=np.zeros((len(images),18),np.float32);counts=np.zeros(len(images),np.float32)
    for start in range(-20,len(images),60):
        indices=np.arange(start,start+100);frames=np.array([images[min(max(i,0),len(images)-1)] if 0<=i<len(images) else np.zeros_like(images[0]) for i in indices],np.float32)/255
        frames=(frames-np.array([.485,.456,.406],np.float32)[None,None,None,:])/np.array([.229,.224,.225],np.float32)[None,None,None,:];tensor=torch.from_numpy(frames.transpose(0,3,1,2)[None])
        with torch.no_grad():prob=torch.softmax(model(tensor),-1)[0].numpy()
        valid=(indices>=0)&(indices<len(images));values[indices[valid]]+=prob[valid];counts[indices[valid]]+=1
        print(json.dumps({'stage':'temporal','seconds':timestamps[min(len(images)-1,start+99)],'elapsed':round(time.monotonic()-started,1)}),flush=True)
    values/=np.maximum(counts[:,None],1);events=[]
    for ci,label in enumerate(CLASSES,1):
        peaks,_=find_peaks(np.r_[-np.inf,values[:,ci],-np.inf],height=.2,distance=max(1,round(samplefps*(.7 if label in ('Goal','Foul','Shots on target','Shots off target') else 4))))
        for i in peaks-1:events.append({'time':round(timestamps[i],6),'timestamp':timestamps[i],'frame':targets[i],'timestamp_basis':'source_presentation_time','class':label,'score':round(float(values[i,ci]),4),'state':'candidate','model':'E2E-Spot pretrained SoccerNet-v2, no adaptation to this match'})
    stat=Path(a.source).stat();fingerprint={'source':str(Path(a.source).resolve()),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}
    write_json(output/'temporal-candidates.json',sorted(events,key=lambda e:e['time']));write_json(output/'temporal-metadata.json',{'frames':len(images),'sampling_fps':samplefps,'source_fps':fps,'classes':CLASSES,'run_seconds':round(time.monotonic()-started,2),'checkpoint':str(checkpoint),'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),'source_fingerprint':fingerprint,**timing,'scope':'Coarse full-video event proposals; no actor identity or certified totals'});write_json(output/'temporal-sampling.json',{'timestamps':timestamps,'source_frames':targets,**timing});CACHE.mkdir(parents=True,exist_ok=True);np.save(CACHE/'temporal-probabilities.npy',values);print(json.dumps({'candidates':len(events),'counts':{c:sum(e['class']==c for e in events) for c in CLASSES}}),flush=True)
if __name__=='__main__':main()
