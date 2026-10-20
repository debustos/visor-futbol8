"""F8 marking evidence and per-view plane validity, without assumed metric dimensions."""
import cv2, numpy as np
from automatic_core import project

def recover_matrix(record):
    pairs=[b for b in record['tracks'] if b.get('position') is not None]
    if len(pairs)<4:return None
    source=np.float32([[(b['box'][0]+b['box'][2])/2,b['box'][3]] for b in pairs]);target=np.float32([b['position'] for b in pairs])
    H,mask=cv2.findHomography(source,target,cv2.RANSAC,.15)
    if H is None or mask is None or int(mask.sum())<4:return None
    return H

def marking_evidence(img,H):
    small=cv2.resize(img,(960,540));h,s,v=cv2.split(cv2.cvtColor(small,cv2.COLOR_BGR2HSV))
    grass=((h>30)&(h<95)&(s>20)&(v>35)).astype(np.uint8)
    neighborhood=cv2.dilate(grass,np.ones((19,19),np.uint8))
    result={};support=[]
    for name,mask in [('blue',((h>=95)&(h<=135)&(s>45)&(v>25)).astype(np.uint8)),('white',((s<60)&(v>155)).astype(np.uint8))]:
        mask=mask*neighborhood;mask[:175]=0
        lines=cv2.HoughLinesP(mask*255,1,np.pi/180,45,minLineLength=65,maxLineGap=20)
        segments=[]
        for line in [] if lines is None else lines.reshape(-1,4):
            x1,y1,x2,y2=map(int,line);length=float(np.hypot(x2-x1,y2-y1))
            if length<80:continue
            # Ignore high nets/barriers and nearly vertical structures.
            if min(y1,y2)<210 or abs(y2-y1)>abs(x2-x1)*2:continue
            pts=np.linspace([x1,y1],[x2,y2],20);inside=[]
            for x,y in pts:
                yy,xx=round(y),round(x);patch=grass[max(0,yy-12):min(540,yy+13),max(0,xx-12):min(960,xx+13)];inside.append(patch.mean() if patch.size else 0)
            if np.mean(inside)<.30:continue
            source=np.asarray([[x1*2,y1*2],[x2*2,y2*2]],np.float32);plane=project(H,source)
            angle=None;deviation=None
            if plane is not None:
                delta=plane[1]-plane[0];angle=float(np.degrees(np.arctan2(delta[1],delta[0]))%90);deviation=min(angle,90-angle)
            segments.append({'image':source.tolist(),'plane':None if plane is None else plane.round(3).tolist(),'axis_error_degrees':None if deviation is None else round(deviation,2),'length_pixels':round(length*2,1)})
        segments.sort(key=lambda x:-x['length_pixels']);result[name]=segments[:24]
    # Blue small-sided markings have priority where both sets of markings coexist.
    chosen=result['blue'] if len(result['blue'])>=2 else result['white'];errors=[s['axis_error_degrees'] for s in chosen if s['axis_error_degrees'] is not None]
    aligned=sum(e<10 for e in errors);state='line_supported' if H is not None and aligned>=2 else 'approximate' if H is not None else 'unavailable'
    if len(errors)>=3 and np.median(errors)>20:state='rejected'
    return {'state':state,'blue_segments':result['blue'],'white_segments':result['white'],'aligned_segments':aligned,'median_axis_error_degrees':round(float(np.median(errors)),2) if errors else None,'marking_family':'blue' if len(result['blue'])>=2 else 'white','metric_dimensions_known':False,'reason':'Líneas compatibles con el plano relativo; dimensiones y límites F8 pendientes de validar' if state=='line_supported' else 'Proyección aproximada con evidencia insuficiente' if state=='approximate' else 'Geometría incompatible o no disponible'}

def attach_geometry(records,views):
    times=np.array([v['time'] for v in views]);blocked=0
    for r in records:
        i=int(np.argmin(abs(times-r['time']))) if len(times) else None
        v=views[i] if i is not None and abs(times[i]-r['time'])<=2.2 else None
        prior=r.get('calibration',{}).get('state','unavailable')
        state=v['state'] if v and prior!='unavailable' else 'unavailable' if prior=='unavailable' else 'approximate'
        r['geometry']={'state':state,'view_time':v['time'] if v else None,'metric_dimensions_known':False,'marking_family':v.get('marking_family') if v else None}
        if state in ('rejected','unavailable'):blocked+=1
    return {'views':len(views),'line_supported_views':sum(v['state']=='line_supported' for v in views),'rejected_views':sum(v['state']=='rejected' for v in views),'samples_excluded':blocked,'metric_dimensions_known':False,'scope':'Automatic marking checks improve validity gating; relative goal-anchored plane remains approximate. No metric distances.'}
