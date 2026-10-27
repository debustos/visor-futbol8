"""Prepare a video-specific relative projection, or preserve an unavailable projection."""
import json
from pathlib import Path
import cv2,numpy as np
from f8.core.io import write_json
from f8.core.runtime_context import ROOT,MASTER,REGISTRY_ROOT,SOURCE

def prepare(root=ROOT,source=SOURCE,master=REGISTRY_ROOT):
    root=Path(root);path=root/'pitch-calibration.json'
    if path.exists():
        previous=json.loads(path.read_text(encoding='utf-8-sig'))
        if previous.get('matrix') is not None:return {'stage':'prepare','done':1,'total':1,'projection':'existing'}
    metadata=json.loads((root/'data/metadata.json').read_text(encoding='utf-8-sig'));context=metadata.get('match_context',{});references=[]
    from f8.plataforma.server import App
    from f8.plataforma.season_store import SeasonStore
    app=App(master);store=SeasonStore(app)
    rows=store.rows();rows.sort(key=lambda r:r['round']!=context.get('round'))
    from f8.deteccion.analyze_automatic import make_registrar,read_image_at
    from f8.campo.pitch_geometry import marking_evidence
    cap=cv2.VideoCapture(str(source))
    try:target=read_image_at(cap,0)
    finally:cap.release()
    for row in rows:
        directory=store.directory(row['analysis_root']);reference_path=directory/'pitch-calibration.json'
        if directory.resolve()==root.resolve() or not reference_path.exists() or not Path(row['source']).is_file():continue
        calibration=json.loads(reference_path.read_text(encoding='utf-8-sig'))
        if calibration.get('matrix') is None:continue
        refcap=cv2.VideoCapture(row['source'])
        try:registrar=make_registrar(refcap,calibration)
        finally:refcap.release()
        matrix,info=registrar(target)
        if matrix is None or info.get('inliers',0)<45 or info.get('median_reprojection_pixels',99)>3:continue
        markings=marking_evidence(target,matrix)
        if markings['state'] in ('rejected','unavailable'):continue
        value={'reference_second':0,'reference_size':[metadata['width'],metadata['height']],'matrix':matrix.tolist(),'calibration_status':'approximate','method':'Automatic feature registration to a calibrated video, checked against visible field markings; relative plane, no metric dimensions.','reference_source':row['source'],'registration':info,'marking_validation':markings}
        write_json(path,value);return {'stage':'prepare','done':1,'total':1,'projection':'approximate','inliers':info['inliers']}
    # The detector and identity engine can finish without inventing field positions.
    write_json(path,{'matrix':None,'reference_second':0,'reference_size':[metadata['width'],metadata['height']],'calibration_status':'unavailable','method':'No supported correspondence to a calibrated field; field coordinates are excluded.'})
    return {'stage':'prepare','done':1,'total':1,'projection':'unavailable','warning':'No se pudo proyectar el campo automáticamente. Se analizarán los jugadores, pero el mapa de calor quedará sin posiciones fiables.'}
if __name__=='__main__':print(json.dumps(prepare(),ensure_ascii=False),flush=True)
