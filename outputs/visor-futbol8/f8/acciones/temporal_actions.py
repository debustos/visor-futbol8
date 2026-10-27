"""E2E-Spot pretrained SoccerNet-v2 inference; candidates are not certified player statistics.
Upstream architecture and weights: https://github.com/jhong93/spot and e2e-spot-models.
"""
from pathlib import Path
import argparse,json,time,math
import cv2,numpy as np,torch,timm
from torch import nn
from scipy.signal import find_peaks
from f8.core.io import write_json
from f8.acciones.vendor.spot.shift import make_temporal_shift
from f8.core.runtime_context import ROOT,WORK,CACHE,SOURCE
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
    p=argparse.ArgumentParser();p.add_argument('--source',default=SOURCE);p.add_argument('--limit',type=float);p.add_argument('--output',default=str(ROOT/'automatic'));a=p.parse_args();output=Path(a.output);torch.set_num_threads(5);cv2.setNumThreads(1)
    model=Spot().eval();weights=torch.load(WORK/'e2e-spot/checkpoint_088.pt',map_location='cpu',weights_only=True);model.load_state_dict(weights,strict=True)
    cap=cv2.VideoCapture(a.source);fps=cap.get(cv2.CAP_PROP_FPS);total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));last=total-1 if a.limit is None else min(total-1,round(a.limit*fps)-1);stride=int(fps/2);targets=list(range(0,last+1,stride));samplefps=fps/stride;images=[];current=0;started=time.monotonic()
    for target in targets:
        while current<target:cap.grab();current+=1
        ok,img=cap.read();current+=1
        if not ok:raise RuntimeError(target)
        images.append(cv2.resize(img,(398,224))[:,:,::-1].copy())
    cap.release();values=np.zeros((len(images),18),np.float32);counts=np.zeros(len(images),np.float32)
    for start in range(-20,len(images),60):
        indices=np.arange(start,start+100);frames=np.array([images[min(max(i,0),len(images)-1)] if 0<=i<len(images) else np.zeros_like(images[0]) for i in indices],np.float32)/255
        frames=(frames-np.array([.485,.456,.406],np.float32)[None,None,None,:])/np.array([.229,.224,.225],np.float32)[None,None,None,:];tensor=torch.from_numpy(frames.transpose(0,3,1,2)[None])
        with torch.no_grad():prob=torch.softmax(model(tensor),-1)[0].numpy()
        valid=(indices>=0)&(indices<len(images));values[indices[valid]]+=prob[valid];counts[indices[valid]]+=1
        print(json.dumps({'stage':'temporal','seconds':round(min(len(images),start+100)/samplefps,1),'elapsed':round(time.monotonic()-started,1)}),flush=True)
    values/=np.maximum(counts[:,None],1);events=[]
    for ci,label in enumerate(CLASSES,1):
        peaks,_=find_peaks(values[:,ci],height=.2,distance=max(1,round(samplefps*4)))
        for i in peaks:events.append({'time':round(targets[i]/fps,3),'class':label,'score':round(float(values[i,ci]),4),'state':'candidate','model':'E2E-Spot pretrained SoccerNet-v2, no adaptation to this match'})
    write_json(output/'temporal-candidates.json',sorted(events,key=lambda e:e['time']));write_json(output/'temporal-metadata.json',{'frames':len(images),'sampling_fps':samplefps,'classes':CLASSES,'run_seconds':round(time.monotonic()-started,2),'checkpoint':'soccer_rny002gsm_gru_rgb/checkpoint_088.pt','full_source':last==total-1,'status':'complete','scope':'Coarse video event candidates; no actor identity or certified totals'});np.save(CACHE/'temporal-probabilities.npy',values);print(json.dumps({'candidates':len(events),'counts':{c:sum(e['class']==c for e in events) for c in CLASSES}}),flush=True)
if __name__=='__main__':main()
