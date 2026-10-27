"""Resolve names once per physical trajectory, independently of playback order.

Only observed boxes are linked. Unknown predictions never become player evidence.
A weak frame cannot change an accepted name. Real tracker cuts, role changes and
review boundaries end a context; competing people are resolved for whole contexts.
"""
from collections import defaultdict, Counter
from bisect import bisect_right
import math
from f8.identidad.identity_recovery import camera_offsets
OWN = {'orange', 'keeper'}
HARD = {'jersey_vote', 'review_reference', 'uniform_role', 'manual_review', 'local_dorsal_guard'}
LEVEL = {'manual_review': 5, 'review_reference': 4, 'jersey_vote': 3,
         'uniform_role': 3, 'calibrated_appearance': 2, 'visual_memory': 2,
         'resolution_reference_bank': 2, 'scale_sequence_memory': 2, 'local_dorsal_guard': 4, 'motion_memory': 1, 'bidirectional_memory': 1}


def _point(b):
    x1, y1, x2, y2 = b['box']
    return ((x1 + x2) / 2, y2)


def _evidence(b):
    if b.get('identity', {}).get('method') in ('manual_review', 'review_conflict'):
        return {'player_id': b.get('player_id'), 'identity': b.get('identity', {}),
                'segment_id': b.get('segment_id')}
    return b.get('identity_evidence') or {'player_id': b.get('player_id'),
        'identity': b.get('identity', {}), 'segment_id': b.get('segment_id')}


def _claim(b, segments):
    raw = _evidence(b); identity = raw.get('identity', {}); s = segments.get(raw.get('segment_id'), {})
    method = identity.get('method') or s.get('method', 'unknown')
    if identity.get('state') == 'rejected' or method in ('uniform_role_conflict', 'review_conflict'):
        return None
    pid = raw.get('player_id')
    # A frame-level duplicate veto is evidence of competition, not a new person.
    if not pid and identity.get('state') == 'conflict' and s.get('number') is not None:
        pid = f"orange-{s['number']}"
    if not pid or (b['kit'] == 'orange' and pid == 'orange-1') or (b['kit'] == 'keeper' and pid != 'orange-1'):
        return None
    proposal = identity.get('proposal') or s.get('proposal') or {}
    score = proposal.get('similarity', s.get('evidence', {}).get('vote_score', .85))
    return {'pid': pid, 'method': method, 'level': LEVEL.get(method, 1),
            'score': float(min(1, score)), 'segment': raw.get('segment_id') or str(b['id'])}


def _review_signature(tid, time, reviews, context_id=None):
    return tuple((d.get('item_id'), d.get('decision'), d.get('player_id'))
                 for d in reviews if (str(d.get('track_id')) == tid or (context_id and d.get('context_id') == context_id))
                 and d.get('start', -1) <= time <= d.get('end', -1))


def stabilize(records, segments=None, cuts=None, reviews=None):
    segments = {s['id']: s for s in (segments or [])}; reviews = reviews or []
    barriers = defaultdict(list); barrier_reasons = defaultdict(dict)
    for c in cuts or []:
        barriers[str(c['track_id'])].append(c['time']); barrier_reasons[str(c['track_id'])][c['time']] = c.get('reason', '')
    for times in barriers.values(): times.sort()
    offsets = camera_offsets(records); episodes = []; active = []; latest_native = {}; reset_reasons = Counter(); alias_links = 0
    before = identity_transitions(records)
    for r in records:
        time = r['time']
        active = [e for e in active if time - e['last'][0]['time'] <= .45]
        existing = {tid for e in active for tid in e['raw_ids']}
        current = [b for b in r['tracks'] if b.get('box') and (b.get('kit') in OWN or str(b['id']) in existing)]
        assigned_b = set(); assigned_e = set(); edges = []
        for j, b in enumerate(current):
            tid = str(b['id']); claim = _claim(b, segments); sig = _review_signature(tid, time, reviews, b.get('person_track_id'))
            for i, e in enumerate(active):
                previous_r, a = e['last']; gap = time - previous_r['time']
                if gap <= 0: continue
                same = tid in e['raw_ids']
                if same and latest_native.get(tid) is not e: continue
                if not same and a['kit'] != b['kit']: continue
                crossed_cut = None
                if same:
                    last_seen = e['last_by_id'][tid]
                    times = barriers[tid]; k = bisect_right(times, last_seen)
                    if k < len(times) and times[k] <= time: crossed_cut = times[k]
                elif not (tid.startswith(('D','N')) or str(a['id']).startswith(('D','N'))) or gap > .22:
                    continue
                if sig != e['review_signature']:
                    if same: reset_reasons['manual_boundary'] += 1
                    continue
                if claim and claim['method'] in HARD and e['hard_pids'] and claim['pid'] not in e['hard_pids']:
                    if same: reset_reasons['contradictory_anchor'] += 1
                    continue
                ah = max(1, a['box'][3] - a['box'][1]); bh = max(1, b['box'][3] - b['box'][1]); height = max(40, (ah + bh) / 2)
                ratio = bh / ah
                ap = _point(a); bp = _point(b); shift = offsets[time] - offsets[previous_r['time']]
                px, py = ap[0] + float(shift[0]), ap[1] + float(shift[1])
                distance = math.hypot(bp[0] - px, bp[1] - py) / height
                if crossed_cut is not None:
                    reason = barrier_reasons[tid][crossed_cut]
                    crowded = any(q is not b and q.get('kit') == b.get('kit') and q.get('box') and math.hypot(_point(q)[0]-bp[0],_point(q)[1]-bp[1])/height < .7 for q in current)
                    reconciled = 'Discontinuidad' in reason and gap <= .25 and distance < .45 and .7 <= ratio <= 1.35 and not crowded
                    if not reconciled: reset_reasons['tracker_cut'] += 1; continue
                    reset_reasons['dense_continuity_recovers_old_cut'] += 1
                if same:
                    if not .35 <= ratio <= 2.75 or distance > max(1.20, gap * 3.5):
                        reset_reasons['physical_jump'] += 1; continue
                else:
                    if claim and e['accepted_pids'] and claim['pid'] not in e['accepted_pids']: continue
                    # Aliases must never join people visible together in either frame.
                    if any(str(q['id']) == str(a['id']) for q in r['tracks']) or any(str(q['id']) == tid for q in previous_r['tracks']): continue
                    if not .70 <= ratio <= 1.35 or distance > .28 + gap * .4: continue
                    if any(q is not b and q.get('kit') == b['kit'] and q.get('box') and
                           math.hypot(_point(q)[0] - px, _point(q)[1] - py) / height < distance + .18
                           for q in current): continue
                cost = distance + .15 * abs(math.log(ratio))
                edges.append((0 if same else 1, cost, i, j))
        # Native track continuity has priority. Alias links require mutual uniqueness.
        for kind, cost, i, j in sorted(edges):
            if i in assigned_e or j in assigned_b: continue
            if kind:
                alternatives_e = [c for k, c, ii, jj in edges if ii == i and jj != j]
                alternatives_b = [c for k, c, ii, jj in edges if jj == j and ii != i]
                if alternatives_e and min(alternatives_e) < cost + .16: continue
                if alternatives_b and min(alternatives_b) < cost + .16: continue
                alias_links += 1; active[i]['alias_links'] += 1
            e = active[i]; b = current[j]; e['rows'].append((r, b)); e['last'] = (r, b)
            e['raw_ids'].add(str(b['id'])); e['last_by_id'][str(b['id'])] = time; latest_native[str(b['id'])] = e
            claim = _claim(b, segments)
            if claim: e['accepted_pids'].add(claim['pid'])
            if claim and claim['method'] in HARD: e['hard_pids'].add(claim['pid'])
            assigned_e.add(i); assigned_b.add(j)
        for j, b in enumerate(current):
            if j in assigned_b or b.get('kit') not in OWN: continue
            tid = str(b['id']); claim = _claim(b, segments)
            e = {'id': f"P{r.get('frame', len(episodes))}-{len(episodes)}", 'rows': [(r, b)], 'last': (r, b),
                 'raw_ids': {tid}, 'last_by_id': {tid: time}, 'alias_links': 0,
                 'accepted_pids': {claim['pid']} if claim else set(),
                 'review_signature': _review_signature(tid, time, reviews, b.get('person_track_id')),
                 'hard_pids': {claim['pid']} if claim and claim['method'] in HARD else set()}
            episodes.append(e); active.append(e); latest_native[tid] = e
    # Offline selection sees the full trajectory, so a later clear dorsal can label
    # the earlier front/profile frames without depending on the user's seek order.
    for e in episodes:
        claims = defaultdict(list)
        for r, b in e['rows']:
            c = _claim(b, segments)
            if c: claims[c['pid']].append(c)
        ranked = []
        for pid, values in claims.items():
            level = max(v['level'] for v in values); top = [v for v in values if v['level'] == level]
            score = max(v['score'] for v in top); support = len({v['segment'] for v in top})
            ranked.append((level, score, support, len(values), pid, top[0]['method']))
        ranked.sort(reverse=True); e['pid'] = None; e['reason'] = 'no_accepted_anchor'; e['rank'] = ()
        if ranked:
            best = ranked[0]
            ambiguous = len(ranked) > 1 and best[0] == ranked[1][0] and best[0] < 3 and best[1] - ranked[1][1] < .10
            if not ambiguous:
                e.update(pid=best[4], anchor_method=best[5], rank=best[:4], reason='trajectory_anchor')
            else: e['reason'] = 'ambiguous_appearance'
        kit_counts = Counter(b.get('observed_kit', b['kit']) for r, b in e['rows'])
        own_fraction = sum(kit_counts[k] for k in OWN) / len(e['rows'])
        if e['pid'] and own_fraction < .65:
            e['pid'] = None; e['reason'] = 'uncertain_uniform_context'
        e['frames'] = {r.get('frame', r['time']) for r, b in e['rows']}
    # Allocate an identity for entire trajectories, not independently every frame.
    # Rejecting a competing trajectory never makes names flash back and forth.
    occupied = defaultdict(set); rejected = 0
    for e in sorted((e for e in episodes if e['pid']), key=lambda e: (e['rank'], -e['rows'][0][0]['time']), reverse=True):
        pid = e['pid']
        if occupied[pid].intersection(e['frames']):
            e['candidate_pid'] = pid; e['pid'] = None; e['reason'] = 'competing_trajectory'; rejected += 1
        else: occupied[pid].update(e['frames'])
    public = []
    for e in episodes:
        for r, b in e['rows']:
            raw = _evidence(b); b['identity_evidence'] = raw
            if e['pid']:
                b.setdefault('observed_kit', b['kit']); b['kit'] = 'keeper' if e['pid'] == 'orange-1' else 'orange'
            b['player_id'] = e['pid']; b['person_track_id'] = e['id']; b['identity_epoch'] = e['id']
            b['identity'] = {'method': 'trajectory_context', 'state': 'estimated' if e['pid'] else 'unknown',
                'locked': bool(e['pid']), 'context_id': e['id'], 'anchor_method': e.get('anchor_method'),
                'reason': e['reason'], 'proposal': raw.get('identity', {}).get('proposal')}
        public.append({'id': e['id'], 'start': e['rows'][0][0]['time'], 'end': e['last'][0]['time'],
            'player_id': e['pid'], 'raw_track_ids': sorted(e['raw_ids']), 'samples': len(e['rows']),
            'alias_links': e['alias_links'], 'anchor_method': e.get('anchor_method'), 'reason': e['reason'],
            'candidate_player_id': e.get('candidate_pid')})
    from f8.identidad.dorsal_guard import apply_guard
    dorsal_quality=apply_guard(records)
    for item in public:
        rows=[b for r in records for b in r['tracks'] if b.get('person_track_id')==item['id']] if item['id'] in {q['context_id'] for q in dorsal_quality['changes']} else []
        if rows:item.update(player_id=rows[0].get('player_id'),anchor_method=rows[0].get('identity',{}).get('anchor_method'),reason=rows[0].get('identity',{}).get('reason'))
    after = identity_transitions(records)
    report = {'version': 7, 'observed_trajectories': len(episodes), 'identified_trajectories': sum(bool(e['pid']) for e in episodes),
        'physical_alias_links': alias_links, 'competing_trajectories_rejected': rejected,
        'dorsal_guard':dorsal_quality,'reset_reasons': dict(reset_reasons), 'before': before, 'after': after,
        'identity_changes_inside_context': sum(len({b.get('player_id') for r, b in e['rows']}) != 1 for e in episodes),
        'policy': 'One offline identity per physical context; measured unique aliases; tracker cuts and review boundaries reset it; whole-context exclusivity.',
        'accuracy_scope': 'Continuity and exclusivity checked; sporting identity accuracy is not independently measured.'}
    return public, report


def identity_transitions(records):
    last = {}; named_unknown = 0; named_named = 0; proposals = 0
    for r in records:
        for b in r['tracks']:
            if b.get('kit') not in OWN: continue
            key = str(b['id']); p = last.get(key)
            if p and 0 < r['time'] - p[0] <= .35 and b.get('player_id') != p[1]:
                if b.get('player_id') and p[1]: named_named += 1
                else: named_unknown += 1
            if not b.get('player_id') and (b.get('identity', {}).get('proposal') or {}).get('similarity', 0) >= .55: proposals += 1
            last[key] = (r['time'], b.get('player_id'))
    return {'raw_track_named_to_unknown_transitions': named_unknown, 'raw_track_name_changes': named_named,
            'uncertain_proposal_labels_previously_possible': proposals}


if __name__ == '__main__':
    from pathlib import Path
    import argparse, json
    from f8.core.io import write_json
    from f8.core.runtime_context import CACHE
    parser = argparse.ArgumentParser(); parser.add_argument('--records'); parser.add_argument('--output'); args = parser.parse_args()
    candidate = CACHE / 'recovery-v5'; path = Path(args.records) if args.records else candidate / 'records-v5.json'
    records = json.loads(path.read_text(encoding='utf-8-sig'))
    def read(name, default):
        p = candidate / (name + '.json'); return json.loads(p.read_text()) if p.exists() else default
    episodes, report = stabilize(records, read('identity-segments', []), read('memory-quality', {}).get('cuts', []))
    write_json(Path(args.output) if args.output else path, records)
    write_json(candidate / 'identity-contexts.json', episodes); write_json(candidate / 'identity-context-quality.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
