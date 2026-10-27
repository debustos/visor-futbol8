"""Export isolated, source-scoped proposals for review/evaluation, without publication.

Missing records leave team and actor unresolved. This is not a verified match report.
"""
import argparse,json,time,math,subprocess
from pathlib import Path
from f8.core.io import write_json
from f8.acciones.sequence_engine import sequence_actions


def main():
    p=argparse.ArgumentParser();p.add_argument('--temporal',required=True);p.add_argument('--records');p.add_argument('--records-orientation',choices=['display','encoded'],default='display');p.add_argument('--source',required=True);p.add_argument('--duration',type=float,required=True);p.add_argument('--output',required=True);p.add_argument('--ffmpeg',help='Optional executable: export candidate intervals as local review clips');args=p.parse_args()
    started=time.monotonic();source=Path(args.source);stat=source.stat();path=Path(args.temporal)
    metadata=json.loads(path.with_name('temporal-metadata.json').read_text(encoding='utf8'))
    fingerprint={'source':str(source.resolve()),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}
    if metadata.get('source_fingerprint')!=fingerprint:raise ValueError('Temporal proposals belong to another source version')
    if metadata.get('status')!='complete':raise ValueError('Incomplete temporal analysis')
    if args.records and args.records_orientation!=metadata.get('orientation','display'):raise ValueError('Records and temporal proposals must use the same orientation')
    if not math.isfinite(args.duration) or not 0<args.duration or args.duration<float(metadata.get('last_decoded_timestamp',0)):raise ValueError('Duration does not contain the decoded source')
    proposals=[{**e,'source_duration':args.duration} for e in json.loads(path.read_text(encoding='utf8'))]
    records=json.loads(Path(args.records).read_text(encoding='utf-8-sig')) if args.records else []
    actions,quality=sequence_actions(records,proposals,True);out=Path(args.output)
    quality.update(source_fingerprint=fingerprint,full_temporal_source=metadata.get('full_source',False),records_available=bool(records),run_seconds=round(time.monotonic()-started,4),scope='Unverified proposals for independent evaluation; no certified goals or fouls')
    write_json(out/'actions.json',actions)
    write_json(out/'review-intervals.json',[{'id':e['id'],'kind':e['kind'],'time':e['time'],'start':e['evidence_start'],'end':e['evidence_end'],'team':e['team'],'player_id':e['player_id'],'state':e['state'],'proposal_evidence':e['proposal_evidence']} for e in actions if 'proposal_evidence' in e])
    if args.ffmpeg:
        from f8.acciones.video_time import merge_windows
        export_started=time.monotonic();quality['sequence_seconds']=quality['run_seconds']
        clips=out/'clips';clips.mkdir(parents=True,exist_ok=True);manifest=[]
        for i,(a,b) in enumerate(merge_windows([[e['evidence_start'],e['evidence_end']] for e in actions])):
            clip=clips/f'{i:04}.mp4'
            rotation=['-noautorotate','-display_rotation:v:0','0'] if metadata.get('orientation')=='encoded' else []
            subprocess.run([args.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y','-ss',str(a),*rotation,'-i',str(source),'-t',str(b-a),'-map','0:v:0','-map','0:a?','-vf','scale=960:-2','-c:v','libx264','-preset','veryfast','-crf','24','-c:a','aac','-b:a','96k','-fps_mode','passthrough',str(clip)],check=True)
            manifest.append({'file':clip.relative_to(out).as_posix(),'source_start':a,'source_end':b,'timestamp_basis':'source_presentation_time','action_ids':[e['id'] for e in actions if a<=e['time']<=b]})
        write_json(out/'clip-manifest.json',{'source_fingerprint':fingerprint,'orientation':metadata.get('orientation','display'),'clips':manifest,'scope':'Review exports; labels remain unverified candidates'})
        quality.update(clip_export_seconds=round(time.monotonic()-export_started,3),run_seconds=round(time.monotonic()-started,3))
    write_json(out/'sequence-quality.json',quality)
    print(json.dumps({'actions':len(actions),'rejected':len(quality['rejected_proposals']),**quality}))


if __name__=='__main__':main()
