"""First lineup and visibility alerts; never asserts substitutions. Moved from automatic_core.py without changes."""
from __future__ import annotations
from collections import defaultdict

def infer_changes(players,records,start_seconds=30):
    """Visibility cannot prove a substitution. Report candidates, require observed border crossing."""
    presence=defaultdict(list)
    for r in records:
        for b in r['tracks']:
            if b.get('player_id') and b.get('position') is not None and 0<=b['position'][0]<=100 and 0<=b['position'][1]<=100:presence[b['player_id']].append((r['time'],b['position'],b['id']))
    starters=[];changes=[]
    for pid,rows in presence.items():
        early=[r for r in rows if r[0]<=start_seconds]
        if len(early)>=5:starters.append({'player_id':pid,'first_seen':early[0][0],'last_seen_initial':early[-1][0],'state':'probable','reason':'Repeated automatic identity within the opening recording interval; kickoff time is not certified.'})
        previous=rows[0]
        for row in rows[1:]:
            gap=row[0]-previous[0]
            if gap>25:
                before_edge=min(previous[1][0],100-previous[1][0])<4;after_edge=min(row[1][0],100-row[1][0])<4
                if before_edge or after_edge:changes.append({'player_id':pid,'time_start':previous[0],'time_end':row[0],'type':'possible_return','state':'uncertain','reason':'Border visibility gap; not sufficient to certify a substitution.'})
            previous=row
    starters.sort(key=lambda v:v['first_seen'])
    return {'expected':8,'identified_candidates':starters,'state':'probable' if len(starters)==8 else 'incomplete','unidentified_slots':max(0,8-len(starters)),'substitutions':[],'visibility_alerts':changes,'reason':'No substitution is asserted from disappearance alone.'}
