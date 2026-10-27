"""Create empty local runtime files without overwriting existing match data."""
import json
from pathlib import Path


def prepare(root):
    root = Path(root).resolve()
    app = root / "outputs" / "visor-futbol8"
    if not (app / "f8" / "plataforma" / "server.py").is_file():
        raise SystemExit("No se encuentra el código del visor en esta carpeta.")
    for folder in ("data", "automatic", "media", "training", "aprendizaje"):
        (app / folder).mkdir(exist_ok=True)
    (root / "work").mkdir(exist_ok=True)
    files = {
        "data/metadata.json": {"source": "", "duration": 0, "width": 1920, "height": 1080, "source_fps": 0, "source_frames": 0, "analysis_fps": 5, "part": "sin registrar", "chunk_seconds": 60},
        "data/fragments.json": [],
        "data/status.json": {"state": "waiting"},
        "automatic/status.json": {"state": "waiting"},
    }
    for name, value in files.items():
        path = app / name
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
        except FileExistsError:
            pass
    return app


if __name__ == "__main__":
    print("Archivos locales preparados:", prepare(Path(__file__).resolve().parent))
    print("Registra los vídeos desde el visor. Los datos existentes se han conservado.")
