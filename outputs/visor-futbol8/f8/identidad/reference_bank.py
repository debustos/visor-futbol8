"""Source-scoped, scale-diverse references with held-out-context calibration.

A proposed appearance identity never becomes a training label. Only independently
anchored physical contexts provide labels. Low-resolution augmentations keep the
source context's fold and are never saved as extra real photographs.
"""
from collections import defaultdict, Counter
from pathlib import Path
import math, json, time, copy, argparse, hashlib
import cv2, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from threadpoolctl import threadpool_limits
from f8.core.io import crop,write_json;from f8.deteccion.modelos import Encoder
from f8.identidad.extract_appearance_parts import physical_signature
from f8.identidad.trajectory_identity import stabilize
from f8.core.runtime_context import ROOT, CACHE, WORK, SOURCE
MAX_REFERENCES = 64
MAX_MODEL_REFERENCES = 384
TRUSTED = {'jersey_vote','uniform_role','review_reference','manual_review','local_dorsal_guard'}


def scale_bucket(height):
    return 'far' if height < 80 else 'medium' if height < 140 else 'near'


def overlap_fraction(box, other):
    x1,y1,x2,y2=box;a,b,c,d=other
    return max(0,min(x2,c)-max(x1,a))*max(0,min(y2,d)-max(y1,b))/max(1,(x2-x1)*(y2-y1))


def acceptable_box(b, tracks):
    x1,y1,x2,y2=b['box']
    return y2-y1>=48 and x2-x1>=12 and b.get('confidence',0)>=.65 and not any(
        q is not b and q.get('box') and overlap_fraction(b['box'],q['box'])>.35 for q in tracks)


def choose_references(candidates, features, limit=MAX_REFERENCES):
    """Reserve distance and dorsal coverage, then fill with diverse real views."""
    chosen=[];used=set()
    def available(c):
        return c['key'] not in used and not any(c['context_id']==q['context_id'] and abs(c['time']-q['time'])<.55 for q in chosen)
    def pick(pool, count):
        for _ in range(count):
            opts=[c for c in pool if available(c)]
            if not opts:break
            def value(c):
                idx=c.get('feature_index');known=[q['feature_index'] for q in chosen if q.get('feature_index') is not None]
                diversity=min((1-float(features[idx]@features[j]) for j in known),default=.5) if idx is not None else .5
                new_context=not any(q['context_id']==c['context_id'] for q in chosen)
                return .55*diversity+.2*new_context+.25*c['quality']
            best=max(opts,key=lambda c:(value(c),-c['frame'],str(c['track_id'])));chosen.append(best);used.add(best['key'])
            if len(chosen)>=limit:return
    pick([c for c in candidates if c['kind']=='dorsal'],min(16,limit//4))
    for distance in ('far','medium','near'):
        if len(chosen)>=limit:break
        pick([c for c in candidates if c['distance']==distance],min(16,limit-len(chosen)))
    if len(chosen)<limit:pick(candidates,limit-len(chosen))
    return sorted(chosen,key=lambda c:(c['distance'],c['kind'],c['time']))


def feature_matrix(embeddings, physical):
    parts=[]
    for k in range(5):
        x=physical[:,k*72:(k+1)*72];parts.append(x/np.maximum(np.linalg.norm(x,axis=1,keepdims=True),1e-8))
    return np.column_stack([embeddings,np.column_stack(parts)*.4]).astype(np.float32)


def calibrate_thresholds(pred, y, groups, heights, classes):
    decisions=[];thresholds={}
    for column,n in enumerate(classes):
        for distance in ('all','far'):
            allowed=np.ones(len(y),bool) if distance=='all' else heights<80
            threshold=1.1;stats={}
            for t in (.65,.70,.75,.80,.85,.90,.95):
                mask=allowed&(pred.argmax(axis=1)==column)&(pred[:,column]>=t)
                count=int(mask.sum());distinct=len(set(groups[mask]));correct=int(np.sum(y[mask]==n))
                if count>=(8 if distance=='all' else 5) and distinct>=2 and correct/count>=.90:
                    threshold=t;stats={'samples':count,'independent_contexts':distinct,'precision_against_anchor_labels':round(correct/count,4)};break
            thresholds[f'{int(n)}:{distance}']=threshold;decisions.append({'number':int(n),'distance':distance,'threshold':threshold,**stats})
    return thresholds,decisions


def train_and_evaluate(bank_x, bank_y, bank_groups, eval_x, eval_y, eval_groups, heights, baseline_mask):
    counts={int(n):len(set(eval_groups[eval_y==n])) for n in set(eval_y)}
    classes=np.array(sorted(n for n,v in counts.items() if v>=3 and n!=1),int)
    if len(classes)<2:return None,{}, {'reason':'No hay tres contextos independientes por clase'}, np.zeros((len(eval_y),0))
    eligible=np.isin(eval_y,classes);ei=np.flatnonzero(eligible)
    pred=np.zeros((len(eval_y),len(classes)),np.float32);baseline=np.zeros_like(pred)
    folds=StratifiedGroupKFold(n_splits=3,shuffle=True,random_state=20261005);folds_report=[]
    def aligned(model, matrix):
        values=model.predict_proba(matrix);result=np.zeros((len(matrix),len(classes)),np.float32)
        for col,n in enumerate(model.classes_):result[:,np.flatnonzero(classes==n)[0]]=values[:,col]
        return result
    with threadpool_limits(limits=4):
        for fold,(tr,te) in enumerate(folds.split(eval_x[ei],eval_y[ei],eval_groups[ei])):
            train_groups=set(eval_groups[ei[tr]]);test_groups=set(eval_groups[ei[te]])
            assert not train_groups.intersection(test_groups)
            bank_mask=np.isin(bank_y,classes)&np.isin(bank_groups,list(train_groups))
            legacy=eligible&baseline_mask&np.isin(eval_groups,list(train_groups))
            if len(set(bank_y[bank_mask]))<2 or len(set(eval_y[legacy]))<2:continue
            model=LogisticRegression(C=20,max_iter=500,class_weight='balanced');model.fit(bank_x[bank_mask],bank_y[bank_mask]);pred[ei[te]]=aligned(model,eval_x[ei[te]])
            old=LogisticRegression(C=20,max_iter=500,class_weight='balanced');old.fit(eval_x[legacy],eval_y[legacy]);baseline[ei[te]]=aligned(old,eval_x[ei[te]])
            folds_report.append({'fold':fold,'train_contexts':len(train_groups),'heldout_contexts':len(test_groups),'bank_training_samples':int(bank_mask.sum()),'old_training_samples':int(legacy.sum()),'context_leakage':False})
        mask=np.isin(bank_y,classes);full=LogisticRegression(C=20,max_iter=600,class_weight='balanced');full.fit(bank_x[mask],bank_y[mask])
    measured=eligible&(pred.sum(axis=1)>.99);thresholds,checks=calibrate_thresholds(pred[measured],eval_y[measured],eval_groups[measured],heights[measured],classes)
    comparisons={}
    for label,valid in [('all',measured),('far',measured&(heights<80)),('medium',measured&(heights>=80)&(heights<140)),('near',measured&(heights>=140))]:
        comparisons[label]={'samples':int(valid.sum()),'contexts':len(set(eval_groups[valid])),
            'near_dorsal_baseline_proxy_accuracy':round(float(np.mean(classes[baseline[valid].argmax(axis=1)]==eval_y[valid])),4) if valid.any() else None,
            'expanded_bank_proxy_accuracy':round(float(np.mean(classes[pred[valid].argmax(axis=1)]==eval_y[valid])),4) if valid.any() else None}
    report={'classes':classes.tolist(),'seed_contexts_per_class':counts,'heldout_comparison':comparisons,'folds':folds_report,'class_checks':checks,
        'evaluation_scope':'Held-out physical contexts with OCR/reference-derived labels, not independent full-match player annotations.',
        'far_acceptance_policy':'At least 90% precision against proxy labels, 5 samples and 2 held-out contexts per class; otherwise far appearance cannot assign a name.'}
    return full,thresholds,report,pred


def build_inputs(records, rows, features, segments, evidence, contexts):
    frames={r['frame']:r for r in records};contexts={c['id']:c for c in contexts};segs={s['id']:s for s in segments};readings=defaultdict(list)
    for e in evidence:
        for rd in e.get('readings',[]):
            if rd.get('text','').isdigit() and rd.get('source')!='jersey_name':readings[(rd['frame'],str(e['track_id']))].append(rd)
    for r in records:
        for b in r['tracks']:
            for v in b.get('dorsal_observations',[]):
                readings[(r['frame'],str(b['id']))].append({'text':str(v['number']),'score':v['score'],'localized':True,'source':'local_dorsal_recheck','time':r['time'],'frame':r['frame']})
    anchors=defaultdict(list)
    for (frame,tid),values in readings.items():
        r=frames.get(frame);b=next((b for b in r['tracks'] if str(b['id'])==tid),None) if r else None
        if not b or not b.get('player_id'):continue
        n=int(b['player_id'].split('-')[-1]);cid=b.get('person_track_id');c=contexts.get(cid,{})
        if c.get('anchor_method') not in TRUSTED:continue
        good=[v for v in values if v['text']==str(n) and (v.get('source')=='verified_training_reference' or v.get('localized') and v['score']>=.85)]
        if good:anchors[cid].append((r,b,max(good,key=lambda v:v['score'])))
    trusted={cid for cid,vals in anchors.items() if len({r['frame'] for r,b,v in vals})>=2 or any(v.get('source')=='verified_training_reference' for r,b,v in vals)}
    trusted.update(cid for cid,c in contexts.items() if c.get('player_id')=='orange-1' and c.get('anchor_method')=='uniform_role')
    trusted.update(cid for cid,c in contexts.items() if c.get('anchor_method') in ('manual_review','review_reference'))
    candidates=defaultdict(list);pool=[];seen=set();row_map={}
    for row in rows:
        r=frames.get(row['frame']);b=next((b for b in r['tracks'] if b['id']==row['track_id']),None) if r else None
        if not b or b.get('person_track_id') not in trusted or not b.get('player_id') or not acceptable_box(b,r['tracks']):continue
        cid=b['person_track_id'];n=int(b['player_id'].split('-')[-1]);h=b['box'][3]-b['box'][1]
        nearby=[v for rr,bb,v in anchors.get(cid,[]) if abs(rr['time']-r['time'])<=3]
        item={'key':f"{r['frame']}:{b['id']}",'frame':r['frame'],'time':r['time'],'track_id':b['id'],'context_id':cid,
            'number':n,'box':b['box'],'height':round(h,1),'distance':scale_bucket(h),'kind':'appearance',
            'feature_index':row['index'],'quality':round(min(1,b.get('confidence',.7)),3),'baseline_near_dorsal':bool(nearby) or n==1}
        candidates[n].append(item);pool.append(item);seen.add(item['key']);row_map[(row['frame'],str(row['track_id']))]=row['index']
    for cid in trusted:
        for r,b,rd in anchors.get(cid,[]):
            if not acceptable_box(b,r['tracks']):continue
            n=int(b['player_id'].split('-')[-1]);key=f"{r['frame']}:{b['id']}";h=b['box'][3]-b['box'][1]
            if key in seen:
                c=next(c for c in candidates[n] if c['key']==key);c.update(kind='dorsal',anchor_source=rd.get('source','localized_ocr'));continue
            options=[c for c in candidates[n] if c['context_id']==cid and c['feature_index'] is not None];near=min(options,key=lambda c:abs(c['time']-r['time'])) if options else None
            candidates[n].append({'key':key,'frame':r['frame'],'time':r['time'],'track_id':b['id'],'context_id':cid,'number':n,
                'box':b['box'],'height':round(h,1),'distance':scale_bucket(h),'kind':'dorsal','anchor_source':rd.get('source','localized_ocr'),
                'feature_index':near['feature_index'] if near else None,'quality':float(rd['score']),'baseline_near_dorsal':True});seen.add(key)
    return candidates,pool,frames,trusted



def summarize_recovery(records, predictions, lineage):
    """Track source observations rather than context IDs regenerated by stabilization."""
    observations={(r['frame'],str(b['id'])):b for r in records for b in r['tracks']}
    recovered=[]
    for p in predictions:
        if not p['accepted']:continue
        target=f"orange-{p['number']}"
        retained=[observations[key] for key in lineage.get(p['context_id'],[]) if observations.get(key,{}).get('player_id')==target]
        recovered.append({**p,'kept_after_exclusivity':bool(retained),'recovered_observations':len(retained),
            'resolved_context_ids':sorted({b['person_track_id'] for b in retained})})
    return recovered


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--records');parser.add_argument('--output');parser.add_argument('--references-only',action='store_true');args=parser.parse_args(argv)
    out=ROOT/'automatic';candidate=CACHE/'recovery-v5';path=Path(args.records) if args.records else None
    records=json.loads(path.read_text(encoding='utf-8-sig')) if path else [r for p in sorted((out/'chunks').glob('*.json')) for r in json.loads(p.read_text())]
    def read(p,default):return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else default
    rows=read(CACHE/'feature-rows.json',[]);emb=np.load(CACHE/'embeddings.npy');physical=np.load(CACHE/'physical-features.npy')
    segments=read(out/'identity-segments.json',[]);evidence=read(candidate/'jersey-evidence-v5.json',[]);contexts=read(out/'identity-contexts.json',[])
    candidates,pool,frames,trusted=build_inputs(records,rows,emb,segments,evidence,contexts)
    selections=[c for n,cs in sorted(candidates.items()) for c in choose_references(cs,emb)]
    portraits=out/'portraits';portraits.mkdir(exist_ok=True);cap=cv2.VideoCapture(SOURCE);encoder=Encoder(WORK/'yolo26n-reid.onnx');bank=[];vectors=[];signatures=[];labels=[];groups=[];gallery=defaultdict(list);started=time.monotonic();rejected=Counter();augmented=0
    byframe=defaultdict(list)
    for c in selections:byframe[c['frame']].append(c)
    indices=Counter();variants=Counter()
    for i,(frame,items) in enumerate(sorted(byframe.items())):
        cap.set(cv2.CAP_PROP_POS_FRAMES,frame);ok,image=cap.read()
        if not ok:rejected['decode']+=len(items);continue
        for c in items:
            part=crop(image,c['box'])
            torso=crop(part,[0,0,part.shape[1],part.shape[0]],.15,.58,.1,.9) if part.size else None
            sharp=float(cv2.Laplacian(cv2.cvtColor(torso,cv2.COLOR_BGR2GRAY),cv2.CV_32F).var()) if torso is not None and torso.size else 0
            if part.size==0 or sharp<8:rejected['blur_or_empty']+=1;continue
            n=c['number'];index=indices[n];indices[n]+=1;filename=f'{n}-pose-{index}.jpg';cv2.imwrite(str(portraits/filename),part,[cv2.IMWRITE_JPEG_QUALITY,96])
            fullbox=[0,0,part.shape[1],part.shape[0]];v=encoder(part,[fullbox])[0];p=physical_signature(part,fullbox)
            vectors.append(v);signatures.append(p);labels.append(n);groups.append(c['context_id']);bank.append({**c,'file':filename,'sharpness':round(sharp,2),'synthetic':False})
            label=('Dorsal observado' if c['kind']=='dorsal' else 'Apariencia vinculada a identidad respaldada')+' Â· '+{'far':'lejos','medium':'media distancia','near':'cerca'}[c['distance']]
            gallery[n].append({'file':filename,'time':c['time'],'frame':c['frame'],'label':label,'track_id':c['track_id'],'context_id':c['context_id'],
                'kind':c['kind'],'distance':c['distance'],'native_height_pixels':int(round(c['height'])),'anchor_source':c.get('anchor_source','physical_continuity_to_dorsal_or_role')})
            if n!=1 and c['height']>=140 and variants[n]<8:
                for height in (48,64):
                    small=cv2.resize(part,(max(12,round(part.shape[1]*height/part.shape[0])),height),interpolation=cv2.INTER_AREA);sb=[0,0,small.shape[1],small.shape[0]]
                    vectors.append(encoder(small,[sb])[0]);signatures.append(physical_signature(small,sb));labels.append(n);groups.append(c['context_id']);augmented+=1
                variants[n]+=1
        if i%20==0 or i==len(byframe)-1:
            progress={'stage':'references','done':i+1,'total':len(byframe),'real_references':len(bank),'elapsed_seconds':round(time.monotonic()-started,1)};write_json(out/'reference-status.json',progress);print(json.dumps(progress),flush=True)
    cap.release();roster=read(ROOT/'plantilla.json',{})['players'];published=[]
    for player in roster:
        n=player['jersey_number'];refs=gallery.get(n,[])
        published.append({'jersey_number':n,'references':refs,'appearance_samples':len(candidates.get(n,[])),
            'reference_counts':dict(Counter(r['distance'] for r in refs)),'kind_counts':dict(Counter(r['kind'] for r in refs)),
            'training_scope':'OCR/review/keeper-anchored physical contexts; proposed identities are not training seeds.',
            'reason':None if refs else 'No hay una identidad respaldada para guardar referencias de este jugador.'})
    write_json(out/'gallery.json',published);write_json(out/'reference-bank.json',bank)
    photo_keys={c['key'] for c in selections};extra=[]
    for n in sorted(candidates):
        native=[c for c in pool if c['number']==n and c['key'] not in photo_keys]
        extra.extend(choose_references(native,emb,MAX_MODEL_REFERENCES))
    for c in extra:
        vectors.append(emb[c['feature_index']]);signatures.append(physical[c['feature_index']]);labels.append(c['number']);groups.append(c['context_id'])
    bank_x=feature_matrix(np.asarray(vectors),np.asarray(signatures)) if vectors else np.zeros((0,872),np.float32);bank_y=np.array(labels,int);bank_groups=np.array(groups)
    write_json(out/'model-reference-manifest.json',[{k:v for k,v in c.items() if k!='box'} for c in bank+extra])
    np.savez_compressed(CACHE/'reference-bank-features-v8.npz',features=bank_x,labels=bank_y,groups=bank_groups)
    eval_indices=np.array([c['feature_index'] for c in pool],int);eval_x=feature_matrix(emb[eval_indices],physical[eval_indices]);eval_y=np.array([c['number'] for c in pool],int);eval_groups=np.array([c['context_id'] for c in pool]);heights=np.array([c['height'] for c in pool]);baseline_mask=np.array([c['baseline_near_dorsal'] for c in pool],bool)
    np.savez_compressed(CACHE/'reference-bank-evaluation-v8.npz',features=eval_x,labels=eval_y,groups=eval_groups,heights=heights,times=np.array([c['time'] for c in pool]))
    model,thresholds,evaluation,pred=train_and_evaluate(bank_x,bank_y,bank_groups,eval_x,eval_y,eval_groups,heights,baseline_mask)
    if model is not None:
        np.savez_compressed(CACHE/'reference-bank-model-v8.npz',coef=model.coef_,intercept=model.intercept_,classes=model.classes_)
        write_json(CACHE/'reference-bank-thresholds-v8.json',thresholds)
    predictions=[];recovered=[]
    if model is not None and not args.references_only:
        all_x=feature_matrix(emb,physical);probs=model.predict_proba(all_x);obs=defaultdict(list);context_meta={c['id']:c for c in contexts}
        for row in rows:
            r=frames.get(row['frame']);b=next((b for b in r['tracks'] if b['id']==row['track_id']),None) if r else None
            if b and b.get('person_track_id') and b.get('kit')=='orange' and acceptable_box(b,r['tracks']):obs[b['person_track_id']].append((row,r,b))
        for cid,values in obs.items():
            c=context_meta.get(cid,{})
            if c.get('player_id') or len(values)<3:continue
            indices=[v[0]['index'] for v in values];p=probs[indices];average=p.mean(axis=0);order=np.argsort(-average);column=order[0];n=int(model.classes_[column]);score=float(np.median(p[:,column]));margin=float(average[column]-average[order[1]]);agreement=float(np.mean(p.argmax(axis=1)==column));far=np.median([v[2]['box'][3]-v[2]['box'][1] for v in values])<80
            threshold=max(thresholds.get(f'{n}:all',1.1),thresholds.get(f'{n}:far',1.1)) if far else thresholds.get(f'{n}:all',1.1)
            item={'context_id':cid,'number':n,'similarity':round(score,4),'margin':round(margin,4),'agreement':round(agreement,4),'samples':len(values),'distance':'far' if far else 'medium_or_near','threshold':threshold,'accepted':bool(score>=threshold and margin>=.18 and agreement>=.8),'method':'resolution_reference_bank'};predictions.append(item)
        proposals={p['context_id']:p for p in predictions if p['accepted']}
        lineage=defaultdict(list)
        for r in records:
            for b in r['tracks']:
                p=proposals.get(b.get('person_track_id'))
                if p:
                    lineage[p['context_id']].append((r['frame'],str(b['id'])))
                    raw=b.get('identity_evidence',{});b['identity_evidence']={**raw,'player_id':f"orange-{p['number']}",'identity':{'method':'resolution_reference_bank','state':'estimated','proposal':p}}
                    b['identity']={'method':'resolution_reference_bank','state':'estimated','proposal':p};b['player_id']=f"orange-{p['number']}"
        new_contexts,context_quality=stabilize(records,segments,read(out/'memory-quality.json',{}).get('cuts',[]))
        recovered=summarize_recovery(records,predictions,lineage)
        write_json(candidate/'identity-contexts.json',new_contexts);write_json(candidate/'identity-context-quality.json',context_quality)
        write_json(Path(args.output) if args.output else candidate/'records-v5.json',records)
    if model is None or args.references_only:write_json(Path(args.output) if args.output else candidate/'records-v5.json',records)
    source=Path(SOURCE);stat=source.stat();quality={'version':8,'source_fingerprint':{'source':str(source.resolve()),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'scan_sha256':hashlib.sha256((CACHE/'scan.json').read_bytes()).hexdigest()},
        'max_real_references_per_player':MAX_REFERENCES,'real_references':len(bank),'model_real_reference_samples':len(bank)+len(extra),'max_model_reference_samples_per_player':MAX_REFERENCES+MAX_MODEL_REFERENCES,'low_resolution_training_variants':augmented,'trusted_contexts':len(trusted),
        'by_player':{str(g['jersey_number']):{'real_references':len(g['references']),'distance_counts':g['reference_counts'],'kind_counts':g['kind_counts']} for g in published},
        'rejected_references':dict(rejected),'evaluation':evaluation,'proposed_contexts':len(predictions),'accepted_before_exclusivity':sum(p['accepted'] for p in predictions),
        'recovered_contexts':sum(p['kept_after_exclusivity'] for p in recovered),'recovered_observations':sum(p['recovered_observations'] for p in recovered),'policy':'Real native-resolution photos; diverse distance/view samples; only anchored contexts seed learning; no labels from a mere appearance proposal.',
        'run_seconds':round(time.monotonic()-started,1),'resolution_limit':'Resizing cannot recover a dorsal or physical detail absent from the source pixels.'}
    write_json(out/'reference-bank-quality.json',quality);write_json(out/'reference-bank-proposals.json',predictions);write_json(out/'reference-bank-recovery.json',recovered);write_json(candidate/'reference-bank-quality.json',quality)
    write_json(out/'reference-status.json',{'state':'complete','stage':'references','done':len(bank),'total':len(bank)});print(json.dumps(quality,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
