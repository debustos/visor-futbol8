"""Inspect registered originals without running detectors or inventing annotations."""
import argparse
import json
import math
from pathlib import Path
import sqlite3
import time

from evaluacion.medir import sha


def inspect_capture(cap):
    # OpenCV is imported by the caller; independent tests use a fake capture.
    import cv2
    fps, frames = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not cap.isOpened() or not math.isfinite(fps) or fps <= 0 or frames < 2:
        raise ValueError("No se pudo leer la duración del original")
    samples = []
    for index in (0, frames//2, frames-2):
        if not cap.set(cv2.CAP_PROP_POS_FRAMES, index):
            raise ValueError("No se pudo buscar el fotograma")
        for _ in range(2):
            ok, _image = cap.read()
            if not ok:
                raise ValueError("Fallo de decodificación en muestra temporal")
            actual = int(cap.get(cv2.CAP_PROP_POS_FRAMES))-1
            seconds = cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            if actual < 0 or not math.isfinite(seconds) or seconds < 0:
                raise ValueError("Posición temporal inválida")
            samples.append({"requested_start_frame": index, "frame_index": actual,
                            "pts_seconds": seconds, "frame_over_average_fps_seconds": actual/fps})
    return {"average_fps": fps, "frame_count": frames, "duration_seconds": frames/fps,
            "samples": samples, "timing_complete": False,
            "scope": "Six decoded frames: beginning, middle, end; not full PTS or visual review"}


def reference(round_number, half, fingerprint, timing):
    return {"schema_version": 1, "synthetic": False, "round": round_number, "half": half,
            "sha256": fingerprint, "duration": timing["duration_seconds"], "video_timing": timing,
            "coverage": {"development": [], "holdout": []}, "events": [], "negative_examples": [],
            "review_status": "unreviewed", "reviewed_seconds": 0,
            "review_provenance": {"method": "Technical inspection only; no sporting events verified",
                                  "human_confirmation": None}}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--registry-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    try:
        if args.output.exists():
            raise ValueError("La salida debe ser nueva; no se sobrescribe")
        import cv2
        registry = args.registry_root/"temporada.sqlite3"
        with sqlite3.connect(registry.resolve().as_uri()+"?mode=ro", uri=True) as db:
            rows = db.execute("SELECT half,source,fingerprint,analysis_root FROM parts WHERE round=? ORDER BY half", (args.round,)).fetchall()
        if sorted(row[0] for row in rows) != [1, 2]:
            raise ValueError("Faltan originales registrados de una o ambas partes")
        entries, references = [], {}
        for half, source, fingerprint, relative in rows:
            source = Path(source)
            digest = sha(source)
            if digest != fingerprint:
                raise ValueError("Original incompatible con su huella registrada")
            cap = cv2.VideoCapture(str(source))
            try:
                timing = inspect_capture(cap)
            finally:
                cap.release()
            contracts = {}
            for name in ("actions", "profiles", "temporal-candidates"):
                path = args.registry_root/relative/"automatic"/(name+".json")
                contracts[name] = {"path": str(path.resolve()), "available": path.is_file(),
                                   "sha256": sha(path) if path.is_file() else None}
            entries.append({"half": half, "source": str(source.resolve()), "video_sha256": digest,
                            "timing": timing, "contracts": contracts, "metrics": None})
            references[f"j{args.round:03d}-p{half}.json"] = reference(args.round, half, digest, timing)
        report = {"round": args.round, "parts": entries, "evaluator_sha256": sha(__file__),
                  "opencv_version": cv2.__version__, "seconds": time.perf_counter()-started,
                  "reviewed_seconds": 0, "comparison": None, "status": "pending_continuous_review_and_detector_outputs"}
        args.output.mkdir(parents=True)
        for name, value in references.items():
            (args.output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
        (args.output/"preparacion.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(report, ensure_ascii=True, indent=2))
    except (ValueError, OSError, sqlite3.Error, ImportError) as error:
        parser.exit(2, f"Preparación pendiente: {error}\n")


if __name__ == "__main__":
    main()
