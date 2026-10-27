"""Read-only evaluation. Times are seconds in the original video."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(ref, video_hash, round_number, half):
    if (ref["round"], ref["half"], ref["sha256"]) != (round_number, half, video_hash):
        raise ValueError("Anotaciones de otro vídeo, jornada, parte o huella incompatible")
    if len(video_hash) != 64 or any(c not in "0123456789abcdef" for c in video_hash):
        raise ValueError("SHA-256 inválido")
    if not math.isfinite(ref["duration"]) or ref["duration"] <= 0:
        raise ValueError("Duración inválida")
    for regions in ref["coverage"].values():
        previous_end = -1
        for start, end in sorted(regions):
            if not 0 <= start < end <= ref["duration"]:
                raise ValueError("Cobertura inválida")
            if start < previous_end:
                raise ValueError("Cobertura solapada")
            previous_end = end
    for a, b in ref["coverage"].get("development", []):
        for c, d in ref["coverage"].get("holdout", []):
            if max(a, c) < min(b, d):
                raise ValueError("Cobertura compartida entre particiones")
    ids = set()
    sequences = {}
    for event in ref["events"]:
        if event["id"] in ids:
            raise ValueError("Identificador repetido")
        ids.add(event["id"])
        start, end = event["interval"]
        if not 0 <= start <= event["time"] <= end <= ref["duration"]:
            raise ValueError("Intervalo inválido")
        if event["status"] not in ("verified", "pending", "ambiguous", "rejected") or event["split"] not in ("development", "holdout"):
            raise ValueError("Estado o partición inválidos")
        if event["kind"] not in ("goal", "foul", "shot_no_goal", "other"):
            raise ValueError("Tipo de anotación inválido")
        if event["status"] == "verified" and not event.get("evidence"):
            raise ValueError("Falta evidencia")
        sequence = event.get("sequence_id", event["id"])
        if sequences.setdefault(sequence, event["split"]) != event["split"]:
            raise ValueError("Una secuencia y sus repeticiones deben conservar la partición")
        for group, regions in ref["coverage"].items():
            if group != event["split"] and any(max(start, a) < min(end, b) for a, b in regions):
                raise ValueError("Jugada dentro de cobertura de otra partición")
        if event["status"] == "verified" and not ref.get("synthetic"):
            provenance = event.get("provenance", {})
            if not all(provenance.get(k) for k in ("observer", "method", "date")) or not event.get("sequence_id"):
                raise ValueError("Faltan secuencia o procedencia de la observación verificada")
    for i, event in enumerate(ref["events"]):
        for other in ref["events"][i+1:]:
            if event["split"] != other["split"] and max(event["interval"][0], other["interval"][0]) <= min(event["interval"][1], other["interval"][1]):
                raise ValueError("Jugadas vecinas repartidas entre particiones")


def matching(truth, predictions, tolerance):
    # Maximum cardinality bipartite matching, deterministic closest-first edges.
    owners = {}
    def visit(i, seen):
        choices = sorted((j for j, p in enumerate(predictions) if abs(p["time"]-truth[i]["time"]) <= tolerance), key=lambda j: (abs(predictions[j]["time"]-truth[i]["time"]), j))
        for j in choices:
            if j in seen:
                continue
            seen.add(j)
            if j not in owners or visit(owners[j], seen):
                owners[j] = i
                return True
        return False
    for i in range(len(truth)):
        visit(i, set())
    return sorted((i, j) for j, i in owners.items())


def evaluate(ref, predictions, kind, split, tolerance=3):
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Tolerancia inválida")
    events = [e for e in ref["events"] if e["split"] == split]
    truth = [e for e in events if e["status"] == "verified" and e["kind"] == kind]
    pending = [e for e in events if e["status"] in ("pending", "ambiguous") and e["kind"] == kind]
    regions = ref["coverage"].get(split, [])
    def covered(t):
        return any(a <= t <= b for a, b in regions)
    def partition(t):
        # Half-open review blocks assign a shared boundary only once.
        for group, blocks in sorted(ref["coverage"].items()):
            if any(a <= t < b or t == b == ref["duration"] for a, b in blocks):
                return group
        nearby = [e for e in ref["events"] if e["kind"] == kind and e["status"] in ("verified", "pending", "ambiguous") and e["interval"][0]-tolerance <= t <= e["interval"][1]+tolerance]
        return min(nearby, key=lambda e: (abs(t-e["time"]), e["id"]))["split"] if nearby else None
    candidates, outside_split = [], []
    for pred in predictions:
        if pred["kind"] != kind:
            continue
        if not 0 <= pred["time"] <= ref["duration"]:
            raise ValueError("Predicción fuera de duración del original")
        (outside_split if partition(pred["time"]) not in (None, split) else candidates).append(pred)
    pairs = matching(truth, candidates, tolerance)
    used = {j for _, j in pairs}
    missed = [e for i, e in enumerate(truth) if i not in {a for a, _ in pairs}]
    false, duplicates, unresolved = [], [], []
    for j, pred in enumerate(candidates):
        if j in used:
            continue
        if any(abs(pred["time"]-e["time"]) <= tolerance for e in truth):
            duplicates.append(pred)
        elif any(e["interval"][0]-tolerance <= pred["time"] <= e["interval"][1]+tolerance for e in pending) or not covered(pred["time"]):
            unresolved.append(pred)
        else:
            false.append(pred)
    details = [{"reference": truth[i], "prediction": candidates[j], "error_seconds": candidates[j]["time"]-truth[i]["time"]} for i, j in pairs]
    def accuracy(field):
        def predicted(detail):
            reference, prediction = detail["reference"], detail["prediction"]
            if kind == "foul" and reference.get("actor_role", "offender") != prediction.get("actor_role", "unknown"):
                return None
            return prediction.get(field)
        eligible = [d for d in details if d["reference"].get(field) is not None]
        correct = sum(d["reference"][field] == predicted(d) for d in eligible)
        return {"correct": correct, "known_reference": len(eligible), "unknown_reference": len(details)-len(eligible), "unknown_prediction": sum(predicted(d) is None for d in details), "accuracy": correct/len(eligible) if eligible else None}
    denominator = len(pairs)+len(false)+len(duplicates)
    return {"verified": len(truth), "found": len(pairs), "missed": missed, "false": false, "duplicates": duplicates, "precision": len(pairs)/denominator if denominator else None, "recall": len(pairs)/len(truth) if truth else None, "matches": details, "mean_absolute_error_seconds": sum(abs(d["error_seconds"]) for d in details)/len(details) if details else None, "team": accuracy("team"), "author": accuracy("player_id"), "pending": pending, "unassessed": unresolved, "outside_split": outside_split, "coverage": regions, "reviewed_seconds": sum(b-a for a, b in regions), "acceptance": "pass" if not ref.get("synthetic") and split == "holdout" and truth and regions == [[0, ref["duration"]]] and not (missed or false or duplicates or pending or unresolved) else "not_demonstrated"}


def normalize(rows, profiles):
    people = {p["id"]: p for p in profiles}
    aliases = {"Goal": "goal", "Foul": "foul"}
    result = []
    for index, row in enumerate(rows):
        kind = aliases.get(row.get("class"), row.get("kind"))
        if kind == "shot" and row.get("outcome") == "goal":
            kind = "goal"
        if kind in ("foul_won", "foul_committed"):
            kind = "foul"
        if kind not in ("goal", "foul"):
            continue
        time = row.get("time")
        if isinstance(time, bool) or not isinstance(time, (int, float)) or not math.isfinite(time) or time < 0:
            raise ValueError("Tiempo de predicción inválido")
        team = row.get("team")
        role = {"foul_won": "beneficiary", "foul_committed": "offender"}.get(row.get("kind"), row.get("actor_role", "unknown"))
        result.append({**row, "id": row.get("id", str(index)), "kind": kind, "source_kind": row.get("kind", row.get("class")), "actor_role": role, "team": None if team == "unresolved" else team, "jersey_number": people.get(row.get("player_id"), {}).get("jersey_number")})
    return result


def compare(before, after):
    if before["identity"] != after["identity"]:
        raise ValueError("Comparación con entradas, anotaciones, grupo o tolerancia diferentes")
    if before["results"].keys() != after["results"].keys():
        raise ValueError("Comparación con etapas diferentes")
    if before.get("evaluator", {}).get("sha256") != after.get("evaluator", {}).get("sha256"):
        raise ValueError("Evaluadores diferentes; recalcular ambas versiones con el mismo evaluador")
    delta = {}
    for stage in before["results"]:
        delta[stage] = {}
        for kind in ("goal", "foul"):
            old, new = before["results"][stage][kind], after["results"][stage][kind]
            values = {key: new[key]-old[key] for key in ("verified", "found")}
            values.update({key: len(new[key])-len(old[key]) for key in ("missed", "false", "duplicates")})
            values.update({key: new[key]-old[key] if new[key] is not None and old[key] is not None else None for key in ("precision", "recall", "mean_absolute_error_seconds")})
            delta[stage][kind] = values
    return delta


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--half", type=int, required=True, choices=(1, 2))
    parser.add_argument("--registry-root", type=Path, default=Path(os.environ.get("FOOTBALL_MASTER_ROOT", Path(__file__).resolve().parents[1])))
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--analysis-root", type=Path)
    parser.add_argument("--video", type=Path, help="Original explícito; requiere --annotations")
    parser.add_argument("--actions", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--temporal", type=Path)
    parser.add_argument("--confirmed-actions", type=Path, help="Exportación separada de acciones revisadas")
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--tolerance", type=float, default=3)
    parser.add_argument("--version", default="unknown", help="Commit del detector, no del evaluador")
    parser.add_argument("--runtime-seconds", type=float)
    parser.add_argument("--output", type=Path, default=Path("evaluacion-local"))
    parser.add_argument("--before", type=Path)
    args = parser.parse_args()
    try:
        if args.runtime_seconds is not None and (not math.isfinite(args.runtime_seconds) or args.runtime_seconds < 0):
            raise ValueError("Tiempo del detector inválido")
        if args.output.exists() and any(args.output.iterdir()):
            raise ValueError("La salida debe ser una carpeta nueva o vacía; no se sobrescribe")
        if args.video:
            if not args.annotations:
                raise ValueError("El original explícito requiere --annotations")
            source, fingerprint, relative = args.video, None, ""
        else:
            registry = args.registry_root/"temporada.sqlite3"
            with sqlite3.connect(registry.resolve().as_uri()+"?mode=ro", uri=True) as db:
                row = db.execute("SELECT source,fingerprint,analysis_root FROM parts WHERE round=? AND half=?", (args.round, args.half)).fetchone()
            if row is None:
                raise ValueError("Jornada/parte no registrada; no se sustituye por otra")
            source, fingerprint, relative = row
        video_hash = sha(source)
        if fingerprint is not None and video_hash != fingerprint:
            raise ValueError("Original incompatible con registro")
        annotation = args.annotations or Path(__file__).parent/"anotaciones"/f"j{args.round:03d}-p{args.half}.json"
        ref = read(annotation)
        validate(ref, video_hash, args.round, args.half)
        analysis = args.analysis_root or args.registry_root/relative
        files = {"actions": args.actions or analysis/"automatic/actions.json", "profiles": args.profiles or analysis/"automatic/profiles.json", "temporal": args.temporal or analysis/"automatic/temporal-candidates.json"}
        actions = normalize(read(files["actions"]), read(files["profiles"]))
        if args.temporal and not args.temporal.is_file():
            raise ValueError("No existe la entrada temporal explícita")
        temporal = normalize(read(files["temporal"]), []) if files["temporal"].exists() else None
        stages = {"published_candidates": [e for e in actions if e.get("state") == "candidate"], "published_accepted_pre_review": [e for e in actions if e.get("state") == "estimated"]}
        unknown = [e for e in actions if e.get("state") not in ("candidate", "estimated")]
        if unknown:
            raise ValueError("Estado de publicación desconocido; exportar revisión por separado")
        if temporal is not None:
            stages["temporal_candidates"] = temporal
        if args.confirmed_actions:
            files["confirmed_actions"] = args.confirmed_actions
            reviewed = normalize(read(args.confirmed_actions), read(files["profiles"]))
            if any(e.get("state") not in ("candidate", "estimated", "confirmed", "rejected") for e in reviewed):
                raise ValueError("Estado de revisión desconocido")
            stages["post_human_review"] = [e for e in reviewed if e.get("state") == "confirmed"]
        report = {"identity": {"round": args.round, "half": args.half, "video_sha256": video_hash, "annotations_sha256": sha(annotation), "split": args.split, "tolerance": args.tolerance}, "detector_version": args.version, "runtime_seconds": args.runtime_seconds, "input_sha256": {k: sha(v) for k, v in files.items() if v.exists()}, "unavailable": ([] if args.confirmed_actions else ["post_human_review"])+([] if temporal is not None else ["temporal_candidates"]), "results": {stage: {kind: evaluate(ref, events, kind, args.split, args.tolerance) for kind in ("goal", "foul")} for stage, events in stages.items()}}
        report["synthetic"] = bool(ref.get("synthetic"))
        report["evaluator"] = {"sha256": sha(__file__), "python": sys.version, "seconds": time.perf_counter()-started}
        report["input_paths"] = {k: str(v.resolve()) for k, v in files.items() if v.exists()} | {"video": str(Path(source).resolve()), "annotations": str(annotation.resolve())}
        if args.before:
            before = read(args.before)
            report["delta"] = compare(before, report)
            old_runtime = before.get("runtime_seconds")
            report["detector_runtime_delta_seconds"] = args.runtime_seconds-old_runtime if args.runtime_seconds is not None and old_runtime is not None else None
            report["comparison_source"] = {"path": str(args.before.resolve()), "sha256": sha(args.before)}
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/"informe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        lines = [f"Jornada {args.round}, parte {args.half}; grupo {args.split}; tolerancia {args.tolerance}s"]
        for stage, kinds in report["results"].items():
            for kind, result in kinds.items():
                lines.append(f"{stage} / {kind}: reales {result['verified']}, encontrados {result['found']}, omitidos {len(result['missed'])}, falsos {len(result['false'])}, duplicados {len(result['duplicates'])}; aceptación {result['acceptance']}")
                lines.append(f"  precisión {result['precision']}; recall {result['recall']}; error absoluto medio {result['mean_absolute_error_seconds']}s; revisados {result['reviewed_seconds']}s de {ref['duration']}s")
                lines.append(f"  equipo {result['team']}; autor {result['author']}")
                for category in ("missed", "false", "duplicates", "pending", "unassessed"):
                    for event in result[category]:
                        lines.append(f"  {category}: {event['id']} @ {event['time']}s; intervalo {event.get('interval', [max(0,event['time']-10),min(ref['duration'],event['time']+10)])}")
        text = "\n".join(lines)
        (args.output/"informe.txt").write_text(text, encoding="utf8")
        print(text)
    except (ValueError, OSError, sqlite3.Error, KeyError) as error:
        parser.exit(2, f"Evaluación pendiente: {error}\n")


if __name__ == "__main__":
    main()
