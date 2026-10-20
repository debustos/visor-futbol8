"""Register local match videos or resolve an isolated analysis context."""
import argparse,json
from pathlib import Path
from server import App
from season_store import SeasonStore
from runtime_context import MASTER,WORK

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--round',type=int,required=True);parser.add_argument('--first');parser.add_argument('--second');parser.add_argument('--date');parser.add_argument('--opponent');parser.add_argument('--context-half',type=int,choices=[1,2]);args=parser.parse_args()
    app=App(MASTER);store=SeasonStore(app)
    if args.context_half:
        rows=store.rows(args.round,args.context_half)
        if not rows:raise ValueError('Jornada o parte no registrada')
        row=rows[0];root=store.directory(row['analysis_root']);cache=WORK/'automatic-half' if row['analysis_root']=='.' else WORK/'jornadas'/f'j{args.round:03d}'/f'parte-{args.context_half}'
        print(json.dumps({'root':str(root),'cache':str(cache),'source':row['source']},ensure_ascii=False));return
    parts=[{'half':half,'source':source} for half,source in [(1,args.first),(2,args.second)] if source]
    result=store.register({'round':args.round,'date':args.date,'opponent':args.opponent,'parts':parts});print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
