"""Fixed-font numeric silhouettes; independent corroboration for jersey OCR."""
from pathlib import Path
import cv2,numpy as np
def silhouette(image):
    h,w=image.shape[:2];hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV);hu,sa,va=cv2.split(hsv);orange=((hu>=0)&(hu<26)&(sa>70)&(va>75)).astype(np.uint8);neighbors=cv2.dilate(orange,np.ones((9,9),np.uint8));mask=((va<150)&((hu<30)|(sa<85))&neighbors.astype(bool)).astype(np.uint8)*255;mask[:int(h*.15)]=0;mask[int(h*.52):]=0;mask[:,:int(w*.10)]=0;mask[:,int(w*.90):]=0
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask);components=[]
    for x,y,cw,ch,area in stats[1:]:
        if max(4,h*.055)<=ch<=h*.29 and area>=8 and ch>=cw*.7:components.append((int(x),int(y),int(cw),int(ch),int(area)))
    if not components:return None
    groups=[]
    for a in components:
        x,y,cw,ch,area=a;others=[b for b in components if abs((b[1]+b[3]/2)-(y+ch/2))<ch*.35 and .55<b[3]/ch<1.8 and abs((b[0]+b[2]/2)-(x+cw/2))<ch*1.8];groups.append(others)
    best=max(groups,key=lambda group:sum(c[4] for c in group));xa=min(c[0] for c in best);ya=min(c[1] for c in best);xb=max(c[0]+c[2] for c in best);yb=max(c[1]+c[3] for c in best)
    if not .18<(xb-xa)/(yb-ya)<2.4:return None
    region=np.zeros_like(mask)
    for component in best:
        x,y,cw,ch,area=component;region[y:y+ch,x:x+cw]=mask[y:y+ch,x:x+cw]
    return region[ya:yb,xa:xb]
def normalize(mask):
    h,w=mask.shape;scale=min(52/w,70/h);resized=cv2.resize(mask,(max(1,round(w*scale)),max(1,round(h*scale))));canvas=np.zeros((80,64),np.float32);y=(80-resized.shape[0])//2;x=(64-resized.shape[1])//2;canvas[y:y+resized.shape[0],x:x+resized.shape[1]]=resized/255;canvas=cv2.GaussianBlur(canvas,(5,5),1.0);return canvas.ravel()/max(np.linalg.norm(canvas),1e-6)

def proposals(crops,model_path):
    if not Path(model_path).exists():return []
    model=np.load(model_path);features=model['features'];numbers=model['numbers'];output=[]
    for file in sorted(Path(crops).glob('*.jpg')):
        img=cv2.imread(str(file))
        if img is None:continue
        mask=silhouette(img)
        if mask is None:continue
        scores=features@normalize(mask);order=sorted(((int(n),float(scores[numbers==n].max())) for n in np.unique(numbers)),key=lambda v:-v[1])
        if len(order)<2:continue
        n,score=order[0];margin=score-order[1][1]
        if score>=.72 and margin>=.08:output.append({'file':file.name,'number':n,'similarity':round(score,4),'margin':round(margin,4),'method':'font_silhouette'})
    return output
