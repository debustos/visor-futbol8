"""Action capability and source-scoped checks against independently supplied totals."""
from collections import Counter

PARTIAL_DETECTORS={'passes','recoveries'}
from f8.core.metricas import METRIC_KEYS as METRICS

def metric_counts(key,estimated,confirmed,candidates,observed):
    enabled=key in PARTIAL_DETECTORS
    return {'detected_value':estimated if observed and (enabled or estimated) else None,
            'detected_scope':'Accepted partial observations; zero is not a full-match total',
            'value':estimated or None,'confirmed_value':confirmed or None,'candidates':candidates,
            'state':'estimated' if estimated else 'unavailable',
            'analysis_state':'partial_detector' if enabled or estimated else 'candidate_only',
            'reason':'Detector parcial: faltan acciones cuando se pierde el balón o la identidad.' if enabled else 'Esta métrica aún no dispone de detección automática validada; las propuestas no son un cero deportivo.'}

def action_diagnostics(actions,quality,reference=None,source_key=None):
    from f8.acciones.pass_engine import pass_summary
    accepted=[e for e in actions if e.get('state')=='estimated']
    reviewed=[e for e in actions if e.get('state')=='confirmed']
    own=lambda e:e.get('team')=='orange' or str(e.get('player_id','')).startswith('orange-')
    automated_goals=sum(e.get('kind')=='goal' and own(e) for e in accepted)
    reviewed_goals=sum(e.get('kind')=='goal' and own(e) for e in reviewed)
    checked=None
    if reference and source_key and reference.get('source_key')==source_key:
        count=reference.get('team_goals')
        if isinstance(count,int) and not isinstance(count,bool) and count>=0:
            checked={'metric':'goals','declared':count,'automatically_detected':automated_goals,
                     'reviewed_events':reviewed_goals,'missing_from_automatic_count':max(0,count-automated_goals),
                     'state':'count_mismatch' if count!=automated_goals else 'count_matches_unvalidated',
                     'provenance':reference.get('provenance','supplied_reference'),'observations':reference.get('goal_observations',[]),
                     'scope':'Declared team total; no scorer or timestamp inferred, count agreement alone does not validate detections.'}
    samples=quality.get('sampled_frames',0);balls=quality.get('ball_visible_frames',0)
    proposals=Counter(e['kind'] for e in actions if e.get('state')=='candidate')
    return {'version':10,'state':'reference_failed' if checked and checked['state']=='count_mismatch' else 'partial_unvalidated',
            'source_key':source_key,'goal_check':checked,'passes':pass_summary(actions),
            'automatic_shots':sum(e['kind'] in ('shot','goal') and own(e) for e in accepted),
            'shot_candidates':proposals['shot']+proposals['goal'],
            'ball_sample_coverage_percent':round(100*balls/samples,1) if samples else None,
            'capabilities':{k:'partial_detector' if k in PARTIAL_DETECTORS else 'candidate_only' for k in METRICS},
            'scope':'Video processing completion is distinct from action accuracy; full-match recall has not been validated.'}
