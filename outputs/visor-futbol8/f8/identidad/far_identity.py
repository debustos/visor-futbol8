"""Scale-specific appearance with nested group validation and temporal evidence.

Identity proposals never supply training labels. Outer context groups are excluded
from model selection and training. Low-resolution views alone need their own gate.
"""
from pathlib import Path
from collections import defaultdict
import argparse,json,hashlib,time
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from threadpoolctl import threadpool_limits
from f8.core.io import write_json
from f8.identidad.reference_bank import feature_matrix,acceptable_box,summarize_recovery
from f8.identidad.trajectory_identity import stabilize
from f8.core.runtime_context import ROOT,CACHE,SOURCE
CONFIGS={
 'v8':([1,1,1,1,1,1],20),
 'physical':([.15,1.5,.15,.5,1.5,3],2),
 'boots_hair_regularized':([.7,1.5,.15,.5,1.5,3],2),
 'parts_equal':([.5,1,1,1,1,1],2),
}
MIN_SAMPLES=8
MIN_SPAN=6
WINDOW_SECONDS=8


def feature_scale(name):
 weights,_=CONFIGS[name]
 return np.r_[np.repeat(weights[0],512),*[np.repeat(w,72) for w in weights[1:]]].astype(np.float64)


def aligned_probability(model,x,classes):
 p=model.predict_proba(x);result=np.zeros((len(x),len(classes)),np.float64)
 for col,n in enumerate(model.classes_):result[:,np.flatnonzero(classes==n)[0]]=p[:,col]
 return result


def fit_model(name,bx,by,bg,classes,train_groups):
 mask=np.isin(by,classes)&np.isin(bg,list(train_groups));scale=feature_scale(name)
 if len(set(by[mask]))<2:return None
 model=LogisticRegression(C=CONFIGS[name][1],max_iter=600,class_weight='balanced')
 return model.fit(bx[mask]*scale,by[mask])


def evidence_windows(indices,times,heights):
 """Time-based windows work at both existing 1 Hz and future 2 Hz sampling."""
 indices=np.array(indices,int);indices=indices[np.argsort(times[indices])]
 if not len(indices):return []
 results=[];start=0
 while start<len(indices):
  begin=times[indices[start]];end=np.searchsorted(times[indices],begin+WINDOW_SECONDS+.01,side='right');window=indices[start:end]
  if len(window)>=MIN_SAMPLES and times[window[-1]]-times[window[0]]>=MIN_SPAN and np.max(np.diff(times[window]))<=2.1 and np.median(heights[window])<140:
   results.append(window)
  start=max(start+1,int(np.searchsorted(times[indices],begin+4,side='left')))
 return results


def sequence_summary(probabilities,classes):
 average=probabilities.mean(axis=0);order=np.argsort(-average);column=order[0]
 return {'number':int(classes[column]),'score':float(np.median(probabilities[:,column])),
  'margin':float(average[column]-average[order[1]]) if len(order)>1 else 0,
  'agreement':float(np.mean(probabilities.argmax(axis=1)==column))}


def summarize_windows(pred,y,groups,heights,times,classes):
 result=[]
 for group in sorted(set(groups[np.isin(y,classes)])):
  for idx in evidence_windows(np.flatnonzero(groups==group),times,heights):
   summary=sequence_summary(pred[idx],classes)
   result.append({**summary,'group':str(group),'truth':int(y[idx[0]]),'far':bool(np.any(heights[idx]<80)),
    'pure_far':bool(np.median(heights[idx])<80),'samples':len(idx),'start':float(times[idx[0]]),'end':float(times[idx[-1]])})
 return result


def calibrate_sequences(windows,classes):
 thresholds={};checks=[]
 for n in classes:
  for distance in ('small','far'):
   threshold=1.1;stats={}
   for t in (.65,.70,.75,.80,.85,.90,.95):
    accepted=[w for w in windows if w['number']==n and w['score']>=t and w['agreement']>=.8 and w['margin']>=.18 and (distance=='small' or w['far'])]
    by_context=defaultdict(list)
    for w in accepted:by_context[w['group']].append(w['truth']==n)
    positive={w['group'] for w in accepted if w['truth']==n}
    precision=float(np.mean([w['truth']==n for w in accepted])) if accepted else 0
    balanced=float(np.mean([np.mean(v) for v in by_context.values()])) if by_context else 0
    if len(accepted)>=5 and len(positive)>=(3 if distance=='small' else 2) and min(precision,balanced)>=.90:
     threshold=t;stats={'windows':len(accepted),'independent_contexts':len(by_context),'positive_contexts':len(positive),
      'precision_against_anchor_labels':round(precision,4),'context_balanced_precision':round(balanced,4)};break
   thresholds[f'{int(n)}:{distance}']=threshold;checks.append({'number':int(n),'distance':distance,'threshold':threshold,**stats})
 return thresholds,checks


def train_and_evaluate(bx,by,bg,x,y,groups,heights,times,progress=None):
 counts={int(n):len(set(groups[y==n])) for n in set(y)};classes=np.array(sorted(n for n,v in counts.items() if v>=3 and n!=1),int)
 if len(classes)<2:return None,None,{}, {'active':False,'reason':'No hay tres trayectorias respaldadas por clase.'}
 eligible=np.isin(y,classes);ei=np.flatnonzero(eligible);pred=np.zeros((len(x),len(classes)),np.float64);base=np.zeros_like(pred);fold_reports=[]
 outer=list(StratifiedGroupKFold(n_splits=3,shuffle=True,random_state=20261005).split(x[ei],y[ei],groups[ei]))
 def predictions(name,tg,test):
  model=fit_model(name,bx,by,bg,classes,tg)
  return aligned_probability(model,x[test]*feature_scale(name),classes) if model is not None else np.zeros((len(test),len(classes)))
 def select(train,n_splits,seed):
  scores={};inner=list(StratifiedGroupKFold(n_splits=n_splits,shuffle=True,random_state=seed).split(x[train],y[train],groups[train]))
  for name in CONFIGS:
   result=np.zeros((len(train),len(classes)),np.float64)
   for tr,te in inner:result[te]=predictions(name,set(groups[train[tr]]),train[te])
   predicted=classes[result.argmax(axis=1)];far=heights[train]<80
   small=float(np.mean(predicted[far]==y[train[far]])) if far.any() else 0
   general=float(np.mean(predicted==y[train]));scores[name]={'far':round(small,4),'all':round(general,4),'score':small+.05*general}
  return max(scores,key=lambda n:scores[n]['score']),scores
 with threadpool_limits(limits=4):
  for fold,(tr,te) in enumerate(outer):
   train=ei[tr];test=ei[te];tg=set(groups[train]);heldout=set(groups[test]);assert not tg.intersection(heldout)
   selected,scores=select(train,2,726+fold);pred[test]=predictions(selected,tg,test);base[test]=predictions('v8',tg,test)
   fold_reports.append({'fold':fold,'selected':selected,'inner_scores':scores,'train_contexts':len(tg),'heldout_contexts':len(heldout),'context_leakage':False,'selection_saw_outer_labels':False})
   if progress:progress({'stage':'far_identity','done':fold+1,'total':5})
  selected,selection_scores=select(ei,3,20261005);model=fit_model(selected,bx,by,bg,classes,set(groups[ei]))
 comparisons={}
 for label,mask in [('far',eligible&(heights<80)),('small',eligible&(heights<140)),('all',eligible),('busi_far',(y==41)&(heights<80))]:
  comparisons[label]={'samples':int(mask.sum()),'independent_contexts':len(set(groups[mask])),
   'baseline_accuracy_against_anchor_labels':round(float(np.mean(classes[base[mask].argmax(axis=1)]==y[mask])),4) if mask.any() else None,
   'specialist_accuracy_against_anchor_labels':round(float(np.mean(classes[pred[mask].argmax(axis=1)]==y[mask])),4) if mask.any() else None}
 windows=summarize_windows(pred,y,groups,heights,times,classes);thresholds,checks=calibrate_sequences(windows,classes)
 far=comparisons['far'];active=far['samples']>=40 and far['independent_contexts']>=8 and far['specialist_accuracy_against_anchor_labels']>=far['baseline_accuracy_against_anchor_labels']+.02
 report={'active':bool(active),'selected_model':selected,'feature_weights':CONFIGS[selected][0],'regularization_C':CONFIGS[selected][1],'classes':classes.tolist(),'comparisons':comparisons,'folds':fold_reports,'full_training_selection':selection_scores,'class_checks':checks,
  'validation_windows':len(windows),'minimum_sequence_samples':MIN_SAMPLES,'minimum_sequence_span_seconds':MIN_SPAN,
  'scope':'Nested group validation against dorsal/reference-derived labels; not independent sporting identity annotations.',
  'policy':'Only previously unknown small-player trajectories; eight seconds of temporal evidence; per-class, context-balanced gates; purely distant evidence requires a far-specific gate.'}
 return model,feature_scale(selected),thresholds,report


def decide_context(probs,classes,times,heights,thresholds):
 indices=np.arange(len(times));windows=evidence_windows(indices,times,heights)
 summary=sequence_summary(probs,classes)
 pure_far=int(np.sum(heights>=80))<3;distance='far' if pure_far else 'small';threshold=thresholds.get(f"{summary['number']}:{distance}",1.1)
 support=[]
 for idx in windows:
  w=sequence_summary(probs[idx],classes)
  if w['number']==summary['number'] and w['score']>=threshold and w['agreement']>=.8 and w['margin']>=.18:support.append({'start':float(times[idx[0]]),'end':float(times[idx[-1]]),'samples':len(idx),'score':round(w['score'],4)})
 accepted=bool(support and summary['score']>=threshold and summary['agreement']>=.8 and summary['margin']>=.18 and np.median(heights)<140)
 return {**summary,'samples':len(times),'distance':distance,'pure_far':pure_far,'threshold':threshold,'supporting_windows':support,'accepted':accepted,'method':'scale_sequence_memory'}


def main(argv=None):
 parser=argparse.ArgumentParser();parser.add_argument('--records');parser.add_argument('--output');args=parser.parse_args(argv)
 out=ROOT/'automatic';candidate=CACHE/'recovery-v5';data_path=CACHE/'reference-bank-evaluation-v8.npz';bank_path=CACHE/'reference-bank-features-v8.npz';started=time.monotonic()
 def read(path,default):return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default
 source=Path(SOURCE);stat=source.stat();fingerprint={'source':str(source.resolve()),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'scan_sha256':hashlib.sha256((CACHE/'scan.json').read_bytes()).hexdigest()}
 if not data_path.exists() or not bank_path.exists() or read(out/'reference-bank-quality.json',{}).get('source_fingerprint')!=fingerprint:
  write_json(out/'far-identity-quality.json',{'version':9,'active':False,'source_fingerprint':fingerprint,'reason':'Faltan referencias y evaluación verificables para este vídeo.'});return
 bank=np.load(bank_path);data=np.load(data_path)
 def progress(value):write_json(out/'far-identity-status.json',value);print(json.dumps(value),flush=True)
 model,scale,thresholds,evaluation=train_and_evaluate(bank['features'],bank['labels'],bank['groups'],data['features'],data['labels'],data['groups'],data['heights'],data['times'],progress)
 records_path=Path(args.records) if args.records else candidate/'records-v5.json';records=read(records_path,[]);frames={r['frame']:r for r in records};predictions=[];recovered=[]
 if model is not None:
  np.savez_compressed(CACHE/'far-identity-model-v9.npz',coef=model.coef_,intercept=model.intercept_,classes=model.classes_,scale=scale);write_json(CACHE/'far-identity-thresholds-v9.json',thresholds)
 if model is not None and evaluation['active']:
  x=feature_matrix(np.load(CACHE/'embeddings.npy'),np.load(CACHE/'physical-features.npy'))
  with threadpool_limits(limits=4):probabilities=model.predict_proba(x*scale)
  obs=defaultdict(list)
  for row in read(CACHE/'feature-rows.json',[]):
   r=frames.get(row['frame']);b=next((b for b in r['tracks'] if b['id']==row['track_id']),None) if r else None
   if b and b.get('person_track_id') and b.get('kit')=='orange' and acceptable_box(b,r['tracks']):obs[b['person_track_id']].append((row,r,b))
  context_rows=defaultdict(list)
  for r in records:
   for b in r['tracks']:
    if b.get('person_track_id'):context_rows[b['person_track_id']].append((r,b))
  for cid,values in obs.items():
   if any(b.get('player_id') or b.get('identity',{}).get('reason')=='competing_trajectory' or b.get('identity',{}).get('method') in ('manual_review','review_conflict') for r,b in context_rows[cid]):continue
   values.sort(key=lambda v:v[1]['time']);times=np.array([v[1]['time'] for v in values]);heights=np.array([v[2]['box'][3]-v[2]['box'][1] for v in values]);p=probabilities[[v[0]['index'] for v in values]]
   if len(values)<MIN_SAMPLES:continue
   proposal=decide_context(p,model.classes_,times,heights,thresholds);proposal.update(context_id=cid,start=times[0],end=times[-1]);predictions.append(proposal)
  proposals={p['context_id']:p for p in predictions if p['accepted']};lineage=defaultdict(list)
  for r in records:
   for b in r['tracks']:
    p=proposals.get(b.get('person_track_id'))
    if p:
     lineage[p['context_id']].append((r['frame'],str(b['id'])));raw=b.get('identity_evidence',{});b['identity_evidence']={**raw,'player_id':f"orange-{p['number']}",'identity':{'method':'scale_sequence_memory','state':'estimated','proposal':{**p,'similarity':p['score']}}};b['player_id']=f"orange-{p['number']}";b['identity']={'method':'scale_sequence_memory','state':'estimated','proposal':{**p,'similarity':p['score']}}
  if proposals:
   contexts,quality=stabilize(records,read(out/'identity-segments.json',[]),read(out/'memory-quality.json',{}).get('cuts',[]));write_json(candidate/'identity-contexts.json',contexts);write_json(candidate/'identity-context-quality.json',quality);recovered=summarize_recovery(records,predictions,lineage)
 write_json(Path(args.output) if args.output else records_path,records)
 quality={'version':9,'source_fingerprint':fingerprint,**evaluation,'proposed_contexts':len(predictions),'accepted_before_exclusivity':sum(p['accepted'] for p in predictions),'recovered_contexts':sum(p['kept_after_exclusivity'] for p in recovered),'recovered_observations':sum(p['recovered_observations'] for p in recovered),'runtime_seconds':round(time.monotonic()-started,1)}
 write_json(out/'far-identity-quality.json',quality);write_json(out/'far-identity-proposals.json',predictions);write_json(out/'far-identity-recovery.json',recovered);write_json(out/'far-identity-status.json',{'state':'complete','stage':'far_identity','done':5,'total':5});print(json.dumps(quality),flush=True)

if __name__=='__main__':main()
