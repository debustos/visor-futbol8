"""Review evidence without turning a model label into a verified sporting result."""
import math

SHOT_CLASSES={'Goal','Shots on target','Shots off target','Visual goal approach'}


def json_evidence(value):
    if isinstance(value,float) and not math.isfinite(value):return repr(value)
    if isinstance(value,dict):return {k:json_evidence(v) for k,v in value.items()}
    if isinstance(value,list):return [json_evidence(v) for v in value]
    return value


def checked_proposals(proposals):
    valid=[];rejected=[]
    for proposal in proposals:
        e=dict(proposal);t=e.get('time');duration=e.get('source_duration')
        numeric=lambda x:isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
        reason=None
        if not isinstance(e.get('class'),str):reason='invalid_class'
        elif not numeric(t) or t<0:reason='invalid_time'
        elif duration is not None and (not numeric(duration) or not 0<=t<duration):reason='outside_source'
        elif e.get('timestamp') is not None and (not numeric(e['timestamp']) or abs(e['timestamp']-t)>.05):reason='timestamp_mismatch'
        elif not numeric(e.get('score')) or not 0<=e['score']<=1:reason='invalid_score'
        start=e.get('evidence_start',max(0,t-5) if numeric(t) else 0)
        end=e.get('evidence_end',t+12 if numeric(t) else 0)
        if reason is None and (not numeric(start) or not numeric(end) or not 0<=start<=t<=end):reason='invalid_interval'
        if reason:rejected.append({'proposal':json_evidence(proposal),'reason':reason});continue
        e['evidence_start']=max(0,min(start,t-5))
        e['evidence_end']=min(duration,max(end,t+12)) if duration is not None else max(end,t+12)
        valid.append(e)
    return valid,rejected


def related(a,b):
    """Anchor-bounded association; never chain neighbouring attacks together."""
    if abs(a['time']-b['time'])>=.7:return False
    if a.get('goal_end') is not None and b.get('goal_end') is not None and a['goal_end']!=b['goal_end']:return False
    # Repeated labels may be separate actions; merge only at the same instant.
    if a['class']==b['class']:return abs(a['time']-b['time'])<.05
    return a['class'] in SHOT_CLASSES and b['class'] in SHOT_CLASSES


def review_proposals(proposals):
    groups=[];other=[]
    for e in sorted(proposals,key=lambda e:e['time']):
        if e['class'] not in SHOT_CLASSES|{'Foul'}:other.append(e);continue
        compatible=[g for g in groups if all(related(q,e) for q in g)]
        # Ambiguous association stays separate instead of swallowing another shot.
        if len(compatible)==1:compatible[0].append(e)
        else:groups.append([e])
    for group in groups:
        goals=[e for e in group if e['class']=='Goal']
        winner=dict(max(goals or group,key=lambda e:e['score']))
        winner['proposal_evidence']=[dict(e) for e in group]
        winner['temporal_evidence']=[{'class':e['class'],'score':e['score'],'time':e['time']} for e in group]
        winner['evidence_start']=min(e['evidence_start'] for e in group)
        winner['evidence_end']=max(e['evidence_end'] for e in group)
        other.append(winner)
    return sorted(other,key=lambda e:e['time'])


def complementary_evidence(event,proposals):
    labels={'Kick-off'} if event['class']=='Goal' else {'Direct free-kick','Indirect free-kick','Penalty','Yellow card','Red card','Yellow->red card'} if event['class']=='Foul' else set()
    limit=30 if event['class']=='Goal' else 8
    return [{'class':e['class'],'time':e['time'],'score':e['score'],'state':'candidate'} for e in proposals if e['class'] in labels and 0<=e['time']-event['time']<=limit]
