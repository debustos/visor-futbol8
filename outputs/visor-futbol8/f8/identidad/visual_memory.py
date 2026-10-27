"""Offline visual memory: anchored galleries, trajectory cuts and exclusive identities."""
from collections import defaultdict, Counter
import numpy as np
from f8.identidad.dorsales import jersey_vote

def similarity(a, b, physical=None, ia=None, ib=None):
    visual=float(np.clip(a@b,0,1))
    if physical is None or ia is None or ib is None:return visual
    pa=physical[ia];pb=physical[ib];scores=[]
    for k in (0,3,4):
        x=pa[k*72:(k+1)*72];y=pb[k*72:(k+1)*72]
        scores.append(float(x@y/max(np.linalg.norm(x)*np.linalg.norm(y),1e-8)))
    return .65*visual+.35*float(np.mean(scores))

def reconstruct(records, rows, features, evidence, roster, physical=None, reviews=None):
    reviews=reviews or []
    observations=defaultdict(list);fr=defaultdict(list);ocr={e['track_id']:e['readings'] for e in evidence};segments=[];cuts=[]
    for r in records:
        for b in r['tracks']:
            if b['kit'] in ('orange','keeper'):observations[b['id']].append((r,b))
    for row in rows:fr[row['track_id']].append(row)
    for tid, obs in observations.items():
        boundaries=[];votes=[]
        for rd in ocr.get(tid,[]):
            text=rd.get('text','');threshold=.75 if rd.get('localized') else .90
            if text.isdigit() and str(int(text))==text and int(text) in roster and int(text)!=1 and rd['score']>=threshold:
                votes.append(rd)
        # Contradictory dorsals must each have independent-frame support before cutting.
        by_n=defaultdict(set)
        for v in votes:by_n[int(v['text'])].add(v['frame'])
        eligible={n for n,fs in by_n.items() if len(fs)>=2}
        ordered={}
        for v in votes:
            n=int(v['text'])
            if n in eligible:
                old=ordered.get(v['frame'])
                if old is None or len(v['text'])>len(old['text']) or len(v['text'])==len(old['text']) and v['score']>old['score']:ordered[v['frame']]=v
        anchor_runs=[]
        for v in sorted(ordered.values(),key=lambda v:v['time']):
            n=int(v['text'])
            if not anchor_runs or anchor_runs[-1]['number']!=n:anchor_runs.append({'number':n,'rows':[v]})
            else:anchor_runs[-1]['rows'].append(v)
        reliable=[g for g in anchor_runs if len({v['frame'] for v in g['rows']})>=2]
        for a,b in zip(reliable,reliable[1:]):
            if a['number']!=b['number']:
                t=(a['rows'][-1]['time']+b['rows'][0]['time'])/2;boundaries.append(t);cuts.append({'track_id':tid,'time':round(t,4),'reason':'Dorsales incompatibles en imágenes independientes'})
        # Cut physically impossible jumps and prolonged detection gaps.
        for (ra,ba),(rb,bb) in zip(obs,obs[1:]):
            dt=rb['time']-ra['time'];pa=ba.get('position');pb=bb.get('position')
            if dt>.65 or pa is not None and pb is not None and np.linalg.norm(np.array(pa)-pb)>max(8,dt*35):
                t=(ra['time']+rb['time'])/2;boundaries.append(t);cuts.append({'track_id':tid,'time':round(t,4),'reason':'Discontinuidad de trayectoria'})
        for review in reviews:
            if review.get('track_id')==tid and review.get('category')=='identity':
                boundaries.extend([review.get('start',obs[0][0]['time'])-.00001,review.get('end',obs[-1][0]['time'])+.00001])
        limits=[obs[0][0]['time']-.0001]+sorted(set(boundaries))+[obs[-1][0]['time']+.0001]
        for k,(lo,hi) in enumerate(zip(limits,limits[1:])):
            group=[(r,b) for r,b in obs if lo<=r['time']<hi]
            if not group:continue
            readings=[v for v in ocr.get(tid,[]) if lo<=v['time']<hi];n,ev=jersey_vote(readings,roster)
            keeper=sum(b['kit']=='keeper' for r,b in group)>=4
            if keeper:n=1;ev={'state':'accepted','method':'uniform_role'}
            fs=[v for v in fr[tid] if lo<=v['time']<hi]
            seg={'id':f'A{tid}-S{k}','track_id':tid,'start':group[0][0]['time'],'end':group[-1][0]['time'],'samples':len(group),'number':n,'method':'uniform_role' if n==1 else 'jersey_vote' if n else 'unknown','state':'accepted' if n else 'unknown','evidence':ev,'feature_indices':[v['index'] for v in fs],'feature_rows':fs,'observations':group,'readings':readings}
            manual=[d for d in reviews if d.get('category')=='identity' and d.get('track_id')==tid and d.get('start',float('inf'))<=seg['start'] and d.get('end',-1)>=seg['end']]
            if manual:
                d=manual[-1];seg.update(number=int(d['player_id'].split('-')[-1]) if d.get('player_id') and d['decision']!='rejected' else None,method='review_reference',state='accepted' if d['decision']!='rejected' else 'rejected')
            segments.append(seg)
    gallery=defaultdict(list)
    for s in segments:
        if s['number'] is None or s['number']==1:continue
        if s['method']=='review_reference':
            for row in s['feature_rows'][::max(1,len(s['feature_rows'])//8)]:gallery[s['number']].append({**row,'segment_id':s['id'],'source':'manual_review'})
            continue
        times=[v['time'] for v in s['readings'] if v['text']==str(s['number']) and v['score']>=.75]
        near=[v for v in s['feature_rows'] if times and min(abs(v['time']-t) for t in times)<=2]
        if not near:continue
        # Reference rows close to actual OCR evidence, rather than all frames of a long track.
        for row in near[::max(1,len(near)//8)]:gallery[s['number']].append({**row,'segment_id':s['id']})
    # Batch gallery matching avoids millions of repeated Python histogram comparisons.
    numbers=sorted(gallery);scores_by_player=np.zeros((len(features),len(numbers)),np.float32)
    if physical is not None:
        normalized=[]
        for k in (0,3,4):
            part=physical[:,k*72:(k+1)*72];normalized.append(part/np.maximum(np.linalg.norm(part,axis=1,keepdims=True),1e-8))
    for column,n in enumerate(numbers):
        indices=[g['index'] for g in gallery[n]];sim=features@features[indices].T
        if physical is not None:
            ps=sum(part@part[indices].T for part in normalized)/3;sim=.65*sim+.35*ps
        scores_by_player[:,column]=sim.max(axis=1)
    proposals=[]
    for s in segments:
        if s['number'] is not None or s['state']=='rejected' or len(s['feature_indices'])<2 or not numbers:continue
        values=scores_by_player[s['feature_indices']];order=np.argsort(-values,axis=1);best_columns=order[:,0];best_scores=np.take_along_axis(values,order[:,:1],axis=1)[:,0];runner=np.take_along_axis(values,order[:,1:2],axis=1)[:,0] if len(numbers)>1 else np.zeros(len(values));margins=best_scores-runner
        column,count=Counter(best_columns.tolist()).most_common(1)[0];n=numbers[column];mask=best_columns==column;score=float(np.median(best_scores[mask]));margin=float(np.median(margins[mask]));strong=int(np.sum(mask&(best_scores>=.82)&(margins>=.055)))
        s['proposal']={'number':n,'similarity':round(score,4),'margin':round(margin,4),'agreement':round(count/len(values),3)}
        if count/len(values)>=.8 and strong>=2 and score>=.84 and margin>=.07:proposals.append((score,s,n))
    def overlapping(s,n):return any(q['number']==n and q['id']!=s['id'] and min(s['end'],q['end'])-max(s['start'],q['start'])>=.15 for q in segments)
    for score,s,n in sorted(proposals,key=lambda v:-v[0]):
        if not overlapping(s,n):s.update(number=n,method='visual_memory',state='estimated')
    # Resolve short occlusions forwards and backwards, using only OCR seeds as origins.
    linked=0
    for target in segments:
        if target['number'] is not None or target['state']=='rejected' or not target['feature_indices']:continue
        opts=[]
        for source in segments:
            if source['number'] in (None,1) or source['method'] not in ('jersey_vote','review_reference') or not source['feature_indices']:continue
            before=target['start']>=source['end'];gap=target['start']-source['end'] if before else source['start']-target['end']
            if not .03<=gap<=3:continue
            a=source['observations'][-1 if before else 0][1];b=target['observations'][0 if before else -1][1]
            if a.get('position') is None or b.get('position') is None:continue
            dist=float(np.linalg.norm(np.array(a['position'])-b['position']));gate=3+gap*2
            if dist>gate:continue
            sa=source['feature_indices'][-3:] if before else source['feature_indices'][:3];ta=target['feature_indices'][:3] if before else target['feature_indices'][-3:]
            sim=float(np.median([max(similarity(features[i],features[j],physical,i,j) for j in sa) for i in ta]))
            if sim<.81:continue
            opts.append((.65*dist/gate+.35*(1-sim),source['number'],source['id'],sim,gap))
        opts.sort()
        if opts and (len({v[1] for v in opts if v[0]-opts[0][0]<.12})==1) and not overlapping(target,opts[0][1]):
            c,n,src,sim,gap=opts[0];target.update(number=n,method='bidirectional_memory',state='estimated',link={'source':src,'similarity':round(sim,4),'gap':round(gap,3)});linked+=1
    conflicts=0
    for s in segments:
        for r,b in s['observations']:
            b['segment_id']=s['id'];b['player_id']=f"orange-{s['number']}" if s['number'] is not None else None;b['identity']={'method':s['method'],'state':s['state'],'segment_id':s['id'],'proposal':s.get('proposal'),'link':s.get('link')}
    for r in records:
        claims=defaultdict(list)
        for b in r['tracks']:
            if b.get('player_id'):claims[b['player_id']].append(b)
        for pid,boxes in claims.items():
            if len(boxes)<2:continue
            seeds=[b for b in boxes if b['identity']['method'] in ('jersey_vote','uniform_role','review_reference')]
            keep=seeds[0] if len(seeds)==1 else None
            for b in boxes:
                if b is keep:continue
                b['player_id']=None;b['identity']={**b['identity'],'state':'conflict','reason':'Identidad simultánea incompatible'};conflicts+=1
    public=[{k:v for k,v in s.items() if k not in ('observations','feature_indices','feature_rows','readings')} for s in segments]
    memory=[{'jersey_number':n,'references':refs,'regions':['pelo','camiseta','pantalón','medias','botas'],'scope':'Rasgos de imagen; sin altura o peso inferidos'} for n,refs in sorted(gallery.items())]
    report={'version':3,'reviewed_reference_inputs':len(reviews),'passes':2,'segments':len(segments),'cuts':cuts,'visual_memory_assignments':sum(s['method']=='visual_memory' for s in segments),'bidirectional_links':linked,'duplicate_claims_rejected':conflicts,'reference_rows':sum(len(v) for v in gallery.values()),'policy':'Only OCR-near seed references; independent visual votes; bidirectional geometry; exclusive frame identities; no unsupported propagation across cuts.'}
    return records,public,memory,report
