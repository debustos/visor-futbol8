"""Train appearance from automatic dorsal seeds; evaluate with whole tracks held out."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,json,numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from threadpoolctl import threadpool_limits
from automatic_core import write_json
from runtime_context import ROOT,WORK,CACHE,SOURCE

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--physical',action='store_true');args=parser.parse_args()
    cache=CACHE;summaries=json.loads((cache/'summaries.json').read_text());labels=json.loads((cache/'labels.json').read_text());features=np.load(cache/'embeddings.npy');rows=[];ys=[];groups=[]
    if args.physical:features=np.column_stack([features,np.load(cache/'physical-features.npy')])
    for s in summaries:
        n=labels.get(str(s['id']),{}).get('number')
        if n is None or len(s['embedding_rows'])<2:continue
        ids=s['embedding_rows'][::max(1,len(s['embedding_rows'])//40)]
        for index in ids:rows.append(index);ys.append(n);groups.append(s['id'])
    X=features[rows].astype(np.float64);y=np.array(ys);g=np.array(groups);classes=np.unique(y);fold=StratifiedGroupKFold(n_splits=5,shuffle=True,random_state=20261004);prob=np.zeros((len(y),len(classes)));models=[]
    with threadpool_limits(limits=4):
        for train,test in fold.split(X,y,g):
            assert not set(g[train])&set(g[test]);model=LogisticRegression(C=40,max_iter=500,class_weight='balanced');model.fit(X[train],y[train]);prob[test]=model.predict_proba(X[test]);models.append(model)
    pred=classes[prob.argmax(axis=1)];confidence=prob.max(axis=1);thresholds={};evaluation=[]
    for n in classes:
        threshold=None;stats={}
        for t in (.75,.80,.85,.90,.95,.98):
            take=(pred==n)&(confidence>=t);total=int(take.sum());correct=int(((y==n)&take).sum());distinct=len(set(g[take]))
            if total>=20 and distinct>=3 and correct/total>=.98:threshold=t;stats={'accepted_samples':total,'precision_against_automatic_seeds':correct/total,'distinct_test_tracks':distinct};break
        thresholds[int(n)]=max(.90,threshold) if threshold is not None else 1.1;evaluation.append({'number':int(n),'threshold':thresholds[int(n)],**stats})
    predictions=[]
    with threadpool_limits(limits=4):
        for s in summaries:
            if labels.get(str(s['id']),{}).get('number') is not None or s['kit_counts'].get('orange',0)/max(1,sum(s['kit_counts'].values()))<.9:continue
            ids=s['embedding_rows']
            if len(ids)<2:continue
            values=np.array([model.predict_proba(features[ids].astype(np.float64)) for model in models]);mean=values.mean(axis=(0,1));ci=int(mean.argmax());n=int(classes[ci]);score=float(np.median(values[:,:,ci]));agree=float(np.mean(values.argmax(axis=2)==ci));runner=float(np.partition(mean,-2)[-2]);anchor=X[y==n];nearest=np.max(features[ids]@anchor.T,axis=1);similarity=float(np.median(nearest))
            if score>=thresholds[n] and score-runner>=.25 and agree>=.9 and similarity>=.78:predictions.append({'track_id':s['id'],'number':n,'probability':round(score,4),'agreement':round(agree,4),'similarity':round(similarity,4),'samples':len(ids),'method':'trained_appearance','state':'estimated'})
    # Persist numeric classifier weights, not executable pickle files.
    np.savez(cache/'appearance-models.npz',classes=classes,coef=np.array([m.coef_ for m in models]),intercept=np.array([m.intercept_ for m in models]))
    report={'state':'complete','features':'body-region color and brightness plus generic embedding' if args.physical else 'generic embedding only','training_samples':len(y),'seed_tracks':len(set(g)),'classes':classes.tolist(),'heldout_track_accuracy_against_automatic_seeds':float(np.mean(pred==y)),'evaluation_scope':'Proxy labels from automatic OCR; whole tracks held out, not independent manually verified ground truth. Probabilities are not a certified identity accuracy.','class_thresholds':evaluation,'new_estimated_tracks':len(predictions),'new_tracks_by_number':dict(Counter(p['number'] for p in predictions))}
    write_json(cache/'appearance-predictions.json',{'labels_sha256':hashlib.sha256((cache/'labels.json').read_bytes()).hexdigest(),'predictions':predictions,'physical_features':args.physical});write_json(ROOT/'automatic/appearance-training.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':main()
