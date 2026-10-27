"""Fixed synthetic sequences; regression evidence, never video accuracy evidence.

Run from outputs/visor-futbol8: python -B -m tests.identidad.compare_contexts
Each sequence is independent. No model fitting or neighbouring-frame validation.
"""
import copy
import hashlib
import json
import statistics
import time
from f8.identidad.trajectory_identity import stabilize


def observation(pid=None, method='unknown', tid=1, x=100, height=80):
    return {'id': tid, 'player_id': pid, 'kit': 'orange',
            'box': [x-20, 20, x+20, 20+height], 'confidence': .9,
            'segment_id': method+str(tid), 'position': None,
            'identity': {'method': method, 'state': 'accepted' if pid else 'unknown'}}


def sequences():
    def anchor(n, method='jersey_vote', **kw):
        return observation('orange-'+str(n), method, **kw)
    cases = {
        'legible_then_far': ([[anchor(41)], [observation(height=60)]], [['orange-41']]*2),
        'crossing': ([[anchor(41), observation(tid=2, x=110)],
                     [observation(), observation(tid=2, x=105)]],
                    [['orange-41', None]]*2),
        'exit_reentry': ([[anchor(41)], [], [observation()]], [['orange-41'], [], [None]]),
        'local_22_then_41': ([[anchor(22, 'local_dorsal_guard')], [anchor(41)]],
                            [['orange-22'], ['orange-41']]),
        '41_then_local_22': ([[anchor(41)], [anchor(22, 'local_dorsal_guard')]],
                            [['orange-41'], ['orange-22']]),
        'local_16_then_11': ([[anchor(16, 'local_dorsal_guard')],
                              [anchor(11, 'local_dorsal_guard')]],
                             [['orange-16'], ['orange-11']]),
        'weak_appearance_then_dorsal': ([[anchor(7, 'calibrated_appearance')], [anchor(41)]],
                                      [['orange-41']]*2),
    }
    result = {}
    for name, (boxes, truth) in cases.items():
        result[name] = ([{'frame': i*3, 'time': 1.0 if name=='exit_reentry' and i==2 else i*.1,
                          'tracks': bs, 'ball': None} for i, bs in enumerate(boxes)], truth)
    return result


def compare(stabilizer=stabilize):
    cases = sequences(); counts = {'correct': 0, 'incorrect': 0, 'unknown': 0,
                                   'unjustified_changes': 0, 'duplicate_claims': 0}
    snapshots = {}; durations = []
    for name, (original, truth) in cases.items():
        # Time only stabilization; deepcopy and imports are excluded in both runs.
        for _ in range(31):
            records = copy.deepcopy(original); start = time.perf_counter()
            stabilizer(records); elapsed = time.perf_counter()-start
            if _: durations.append(elapsed)
        predicted = [[b.get('player_id') for b in r['tracks']] for r in records]
        snapshots[name] = predicted
        last = {}
        for r, expected in zip(records, truth):
            named = [b['player_id'] for b in r['tracks'] if b.get('player_id')]
            counts['duplicate_claims'] += len(named)-len(set(named))
            for b, actual in zip(r['tracks'], expected):
                pid = b.get('player_id')
                counts['unknown' if pid is None else 'correct' if pid==actual else 'incorrect'] += 1
                previous = last.get(b['id'])
                if previous and previous[0]==actual and previous[1] and pid and previous[1]!=pid:
                    counts['unjustified_changes'] += 1
                last[b['id']] = (actual, pid)
    assigned = counts['correct']+counts['incorrect']; total = assigned+counts['unknown']
    return {'scope': 'synthetic regression sequences; no independent video annotations',
            'input_sha256': hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
            **counts, 'observations': total, 'precision': counts['correct']/assigned if assigned else None,
            'coverage': assigned/total, 'median_sequence_ms': statistics.median(durations)*1000,
            'snapshots': snapshots}


if __name__ == '__main__':
    import argparse
    import subprocess
    parser = argparse.ArgumentParser(); parser.add_argument('--baseline-ref'); args = parser.parse_args()
    stabilizer = stabilize
    if args.baseline_ref:
        # Only the stabilizer changed behaviour; its dependency functions are unchanged.
        code = subprocess.check_output(['git', 'show', args.baseline_ref+
            ':outputs/visor-futbol8/f8/identidad/trajectory_identity.py'], encoding='utf8')
        namespace = {'__name__': 'baseline_trajectory'}; exec(compile(code, '<baseline>', 'exec'), namespace)
        stabilizer = namespace['stabilize']
    print(json.dumps(compare(stabilizer), indent=2))
