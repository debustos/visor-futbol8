"""Full-source validation for v3, including dense contacts and exclusive identities."""
from pathlib import Path
import json,math,hashlib
from collections import Counter
from automatic_core import write_json
from runtime_context import ROOT,WORK,CACHE,SOURCE

def main():
    out=ROOT/'automatic';metadata=json.loads((out/'metadata.json').read_text());quality=json.loads((out/'quality.json').read_text());records=[r for path in sorted((out/'chunks').glob('*.json')) for r in json.loads(path.read_text())];profiles=json.loads((out/'profiles.json').read_text());actions=json.loads((out/'actions.json').read_text());queue=json.loads((out/'uncertainties.json').read_text());previous=-1;checks=[]
    assert records[0]['frame']==0 and records[-1]['frame']==int(round(metadata['duration']*metadata['source_fps']))-1
    for r in records:
        assert r['frame']>previous;previous=r['frame'];assert abs(r['time']-r['frame']/metadata['source_fps'])<.00011
        tids=[str(b['id']) for b in r['tracks']];assert len(tids)==len(set(tids))
        players=[b['player_id'] for b in r['tracks'] if b.get('player_id')];assert len(players)==len(set(players)),(r['time'],players)
        for b in r['tracks']:assert all(math.isfinite(v) for v in b['box'])
    assert len(records)==quality['sampled_frames'];assert len(profiles)==16;assert all(len(p['metrics'])==11 for p in profiles);assert len({q['id'] for q in queue})==len(queue);assert len({e['id'] for e in actions})==len(actions)
    for p in profiles:
        assert 0<=p['visible_seconds']<=metadata['duration']+.2;assert p['mapped_seconds']<=p['visible_seconds']+.2
        assert p['mapped_samples']==len(p['heatmap_points']);assert all(0<=v['x']<=100 and 0<=v['y']<=100 for v in p['heatmap_points']);assert abs(sum(v['weight_seconds'] for v in p['heatmap_points'])-p['mapped_seconds'])<.11
    # Every estimated pass must have observed release/travel/reception evidence.
    for e in actions:
        if e['state']=='estimated' and e['kind']=='pass':assert e['sequence']['travel_verified'] and e['sequence']['measured_path_samples']>=2 and e['sequence']['largest_sample_gap']<=.35
    checks=['first and last native source frame','monotonic source timestamps','unique trajectory IDs','exclusive player identities per frame','16 profiles and eleven metric fields','duration-weighted maps','no invalid geometry in maps','unique review items','measured path required for estimated passes']
    report={'engine_version':3,'checks_passed':checks,'frames':len(records),'adaptive_frames':quality['adaptive_frames'],'identities':quality['identified_players'],'actions':len(actions),'review_items':len(queue),'independent_sporting_accuracy':'not measured; user review available'};write_json(ROOT/'validacion-v3.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':main()
