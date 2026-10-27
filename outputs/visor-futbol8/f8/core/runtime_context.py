"""Shared model paths, isolated per-video data and explicit source selection."""
import json,os
from pathlib import Path
from f8.core.paths import APP_DIR,WORK_DIR
MASTER=APP_DIR
ROOT=Path(os.environ.get('FOOTBALL_VIEWER_ROOT',str(MASTER))).resolve()
REGISTRY_ROOT=Path(os.environ.get('FOOTBALL_MASTER_ROOT',str(MASTER))).resolve()
WORK=WORK_DIR
CACHE=Path(os.environ.get('FOOTBALL_CACHE_ROOT',str(WORK/'automatic-half'))).resolve()
metadata=ROOT/'data/metadata.json'
SOURCE=os.environ.get('FOOTBALL_VIDEO_SOURCE') or (json.loads(metadata.read_text(encoding='utf-8-sig')).get('source') if metadata.exists() else 'S:/PRIMERA PARTE.MP4')
