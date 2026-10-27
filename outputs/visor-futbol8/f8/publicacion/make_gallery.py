"""Reuse the expanded source-scoped gallery; build one when absent."""
import json,hashlib
from pathlib import Path
from f8.core.runtime_context import ROOT,CACHE,SOURCE

def main():
    q=ROOT/'automatic/reference-bank-quality.json';gallery=ROOT/'automatic/gallery.json';source=Path(SOURCE);stat=source.stat()
    fingerprint={'source':str(source.resolve()),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'scan_sha256':hashlib.sha256((CACHE/'scan.json').read_bytes()).hexdigest()}
    if q.exists() and gallery.exists() and json.loads(q.read_text()).get('source_fingerprint')==fingerprint:
        rows=json.loads(gallery.read_text());photos=[r for g in rows for r in g['references']]
        if photos and all((ROOT/'automatic/portraits'/r['file']).exists() for r in photos):
            print('Expanded source-scoped references reused:',len(photos),flush=True);return
    from f8.identidad.reference_bank import main as build
    build(['--references-only'])

if __name__=='__main__':main()
