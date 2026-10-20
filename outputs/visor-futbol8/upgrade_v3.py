"""Prepare immutable automatic bases for the upgraded reconstruction."""
from pathlib import Path
import argparse,json,time,numpy as np
from automatic_core import write_json,infer_possession
from visual_memory import reconstruct
from runtime_context import ROOT,WORK,CACHE,SOURCE

def prepare():
    out=ROOT/'automatic';cache=CACHE;records=json.loads((cache/'scan.json').read_text());rows=json.loads((cache/'feature-rows.json').read_text());features=np.load(cache/'embeddings.npy');physical=np.load(cache/'physical-features.npy') if (cache/'physical-features.npy').exists() else None;evidence=json.loads((out/'jersey-evidence.json').read_text());roster={p['jersey_number']:p for p in json.loads((ROOT/'plantilla.json').read_text(encoding='utf8'))['players']};refined=json.loads((cache/'ball-refinement.json').read_text());beg=time.monotonic()
    for r,v in zip(records,refined):
        if r['frame']!=v['frame']:raise RuntimeError('Cached source mismatch')
        r['ball']=v['ball'];r['possession']=infer_possession(r)
    reviews=[]
    if (out/'review-manifest.json').exists() and (ROOT/'revisiones.sqlite3').exists():
        import sqlite3
        import hashlib
        metadata=json.loads((out/'metadata.json').read_text());source=Path(metadata['source']);stat=source.stat();current_key=hashlib.sha256((str(source.resolve())+str(stat.st_size)+str(stat.st_mtime_ns)+hashlib.sha256((cache/'scan.json').read_bytes()).hexdigest()+'v3').encode()).hexdigest()[:24]
        key=json.loads((out/'review-manifest.json').read_text())['source_key'];db=sqlite3.connect(ROOT/'revisiones.sqlite3')
        try:
            if key==current_key and db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='automatic_reviews'").fetchone():reviews=[json.loads(r[0]) for r in db.execute('SELECT payload FROM automatic_reviews WHERE source_key=?',(key,)) if json.loads(r[0]).get('category')=='identity']
        finally:db.close()
    records,segments,memory,q=reconstruct(records,rows,features,evidence,roster,physical,reviews);q['run_seconds']=round(time.monotonic()-beg,1)
    write_json(cache/'identified-v3.json',records);write_json(out/'identity-segments.json',segments);write_json(out/'visual-memory.json',memory);write_json(out/'memory-quality.json',q);print(json.dumps({k:v for k,v in q.items() if k!='cuts'}),flush=True)
if __name__=='__main__':prepare()
