"""Synthetic regression comparison; this never measures video detection accuracy.

python tests/acciones/benchmark_proposals.py --code-root <baseline or current APP_DIR>
"""
import argparse,json,statistics,sys,time
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--code-root',required=True);p.add_argument('--temporal',help='Optional real model proposals; still not accuracy evaluation');args=p.parse_args();sys.path.insert(0,str(Path(args.code_root).resolve()))
    from f8.acciones.sequence_engine import sequence_actions
    def event(label='Goal',t=.3,**kw):return {'time':t,'class':label,'score':.8,**kw}
    def rows(kit):
        return [{'time':i*.1,'frame':i,'tracks':[{'id':1,'kit':kit,'player_id':'orange-7' if kit=='orange' else None,'box':[0,0,40,100],'position':None}],'ball':{'center':[x,100],'confidence':.9,'position':None},'possession':{'track_id':1,'distance':.1} if i<2 else None} for i,x in enumerate([20,20,80,110,140])]
    scenarios={'rival_goal':(rows('opponent'),[event()]),'unknown_goal':([],[event()]),'shot_not_goal':([],[event('Shots off target')]),'duplicates':([],[event('Goal',10),event('Shots on target',10.2)]),'foul_contact':(rows('orange'),[event('Foul')]),'wrong_time':([],[event(t=3,timestamp=7)])}
    if args.temporal:scenarios['temporal_input']=([],json.loads(Path(args.temporal).read_text(encoding='utf8')))
    results={}
    for name,(records,proposals) in scenarios.items():
        timings=[]
        for _ in range(101):
            start=time.perf_counter();actions,quality=sequence_actions(records,proposals,True);timings.append(time.perf_counter()-start)
        results[name]={'actions':[{k:e.get(k) for k in ('kind','team','player_id','state')} for e in actions],'rejected':len(quality.get('rejected_proposals',[])),'median_seconds':statistics.median(timings)}
    print(json.dumps({'scope':'synthetic software regressions, not verified video accuracy','iterations':101,'results':results},ensure_ascii=False))


if __name__=='__main__':main()
