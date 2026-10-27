"""Short-gap identity recovery: exclusive geometry plus appearance, with bounded propagation."""
from collections import defaultdict
import numpy as np

def stitch(records,summaries,features,label_map,evidence_map):
    points=defaultdict(list)
    for r in records:
        for b in r['tracks']:
            if b.get('position') is not None:points[b['id']].append((r['time'],np.asarray(b['position'])))
    by_id={s['id']:s for s in summaries};depth={t:0 for t in label_map};accepted=[]
    for iteration in range(2):
        proposals=defaultdict(list);source_options=defaultdict(list)
        for target,trows in points.items():
            if target in label_map or len(trows)<3:continue
            ts=by_id[target];ti=ts['embedding_rows'][:4]
            if len(ti)<2 or ts['kit_counts'].get('orange',0)/max(1,sum(ts['kit_counts'].values()))<.9:continue
            for source,n in list(label_map.items()):
                if n==1 or source not in points or depth.get(source,0)>=2:continue
                if evidence_map[source]['method'] not in ('jersey_vote','appearance_motion_link'):continue
                srows=points[source];gap=trows[0][0]-srows[-1][0]
                if not .05<=gap<=2:continue
                si=by_id[source]['embedding_rows'][-4:]
                if len(si)<2:continue
                similarity=float(np.median(np.max(features[ti]@features[si].T,axis=1)))
                if similarity<.86:continue
                velocity=np.zeros(2)
                if len(srows)>=4:
                    a=srows[-min(6,len(srows))];delta=srows[-1][0]-a[0]
                    if delta>0:velocity=(srows[-1][1]-a[1])/delta
                prediction=srows[-1][1]+velocity*min(gap,.6);distance=float(np.linalg.norm(trows[0][1]-prediction));gate=2.5+gap*1.2
                if distance>gate:continue
                cost=.7*distance/gate+.3*(1-similarity)
                proposal={'target':target,'source':source,'number':n,'similarity':similarity,'gap':gap,'distance':distance,'cost':cost}
                proposals[target].append(proposal);source_options[source].append(proposal)
        for target,opts in proposals.items():
            opts.sort(key=lambda q:q['cost']);v=opts[0]
            if len(opts)>1 and opts[1]['cost']-v['cost']<.15:continue
            reverse=sorted(source_options[v['source']],key=lambda q:q['cost'])
            if reverse[0]['target']!=target or len(reverse)>1 and reverse[1]['cost']-v['cost']<.15:continue
            label_map[target]=v['number'];depth[target]=depth[v['source']]+1
            evidence_map[target]={'method':'appearance_motion_link','state':'estimated','source_track':v['source'],'similarity':round(v['similarity'],4),'gap_seconds':round(v['gap'],3),'position_residual':round(v['distance'],3),'depth':depth[target]}
            accepted.append(v)
    return accepted
