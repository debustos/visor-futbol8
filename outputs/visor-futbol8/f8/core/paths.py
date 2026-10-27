"""Fixed project locations. Every module resolves code, web and model paths from here."""
from pathlib import Path

PACKAGE_DIR=Path(__file__).resolve().parents[1]
APP_DIR=PACKAGE_DIR.parent
WEB_DIR=APP_DIR/'web'
REPO_DIR=APP_DIR.parents[1]
WORK_DIR=REPO_DIR/'work'
