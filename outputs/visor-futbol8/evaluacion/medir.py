"""Read-only evaluation. Times are seconds in the original video."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3


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
        for start, end in regions:
            if not 0 <= start < end <= ref["duration"]:
                raise ValueError("Cobertura inválida")
    ids = set()
    for event in ref["events"]:
        if event["id"] in ids:
            raise ValueError("Identificador repetido")
        ids.add(event["id"])
        start, end = event["interval"]
        if not 0 <= start <= event["time"] <= end <= ref["duration"]:
            raise ValueError("Intervalo inválido")
        if event["status"] not in ("verified", "pending", "rejected") or event["split"] not in ("development", "holdout"):
            raise ValueError("Estado o partición inválidos")
        if event["status"] == "verified" and not event.get("evidence"):
            raise ValueError("Falta evidencia")
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
    pending = [e for e in events if e["status"] == "pending"]
    regions = ref["coverage"].get(split, [])
    def covered(t):
        return any(a <= t <= b for a, b in regions)
    candidates = [p for p in predictions if p["kind"] == kind]
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
        eligible = [d for d in details if d["reference"].get(field) is not None]
        correct = sum(d["reference"][field] == d["prediction"].get(field) for d in eligible)
        return {"correct": correct, "known_reference": len(eligible), "accuracy": correct/len(eligible) if eligible else None}
    denominator = len(pairs)+len(false)+len(duplicates)
    return {"verified": len(truth), "found": len(pairs), "missed": missed, "false": false, "duplicates": duplicates, "precision": len(pairs)/denominator if denominator else None, "recall": len(pairs)/len(truth) if truth else None, "matches": details, "mean_absolute_error_seconds": sum(abs(d["error_seconds"]) for d in details)/len(details) if details else None, "team": accuracy("team"), "author": accuracy("player_id"), "pending": pending, "unassessed": unresolved, "coverage": regions, "acceptance": "pass" if split == "holdout" and truth and regions == [[0, ref["duration"]]] and not (missed or false or duplicates or pending or unresolved) else "not_demonstrated"}


def normalize(rows, profiles):
    people = {p["id"]: p for p in profiles}
    aliases = {"Goal": "goal", "Foul": "foul"}
    result = []
    for index, row in enumerate(rows):
        kind = aliases.get(row.get("class"), row.get("kind"))
        if kind not in ("goal", "foul"):
            continue
        time = row.get("time")
        if isinstance(time, bool) or not isinstance(time, (int, float)) or not math.isfinite(time) or time < 0:
            raise ValueError("Tiempo de predicción inválido")
        result.append({**row, "id": row.get("id", str(index)), "kind": kind, "team": row.get("team"), "jersey_number": people.get(row.get("player_id"), {}).get("jersey_number")})
    return result


def compare(before, after):
    if before["identity"] != after["identity"]:
        raise ValueError("Comparación con entradas, anotaciones, grupo o tolerancia diferentes")
    return {stage: {kind: {key: after["results"][stage][kind][key]-before["results"][stage][kind][key] for key in ("verified", "found")} | {key: len(after["results"][stage][kind][key])-len(before["results"][stage][kind][key]) for key in ("missed", "false", "duplicates")} for kind in ("goal", "foul")} for stage in before["results"]}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--half", type=int, required=True, choices=(1, 2))
    parser.add_argument("--registry-root", type=Path, default=Path(os.environ.get("FOOTBALL_MASTER_ROOT", Path(__file__).resolve().parents[1])))
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--analysis-root", type=Path)
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--tolerance", type=float, default=3)
    parser.add_argument("--version", default="unknown", help="Commit del detector, no del evaluador")
    parser.add_argument("--runtime-seconds", type=float)
    parser.add_argument("--output", type=Path, default=Path("evaluacion-local"))
    parser.add_argument("--before", type=Path)
    args = parser.parse_args()
    try:
        registry = args.registry_root/"temporada.sqlite3"
        with sqlite3.connect(registry.resolve().as_uri()+"?mode=ro", uri=True) as db:
            row = db.execute("SELECT source,fingerprint,analysis_root FROM parts WHERE round=? AND half=?", (args.round, args.half)).fetchone()
        if row is None:
            raise ValueError("Jornada/parte no registrada; no se sustituye por otra")
        source, fingerprint, relative = row
        video_hash = sha(source)
        if video_hash != fingerprint:
            raise ValueError("Original incompatible con registro")
        annotation = args.annotations or Path(__file__).parent/"anotaciones"/f"j{args.round:03d}-p{args.half}.json"
        ref = read(annotation)
        validate(ref, video_hash, args.round, args.half)
        analysis = args.analysis_root or args.registry_root/relative
        files = {"actions": analysis/"automatic/actions.json", "profiles": analysis/"automatic/profiles.json", "temporal": analysis/"automatic/temporal-candidates.json"}
        actions = normalize(read(files["actions"]), read(files["profiles"]))
        temporal = normalize(read(files["temporal"]), []) if files["temporal"].exists() else None
        stages = {"published_candidates": [e for e in actions if e.get("state") == "candidate"], "published_accepted_pre_review": [e for e in actions if e.get("state") == "estimated"]}
        unknown = [e for e in actions if e.get("state") not in ("candidate", "estimated")]
        if unknown:
            raise ValueError("Estado de publicación desconocido; exportar revisión por separado")
        if temporal is not None:
            stages["temporal_candidates"] = temporal
        report = {"identity": {"round": args.round, "half": args.half, "video_sha256": video_hash, "annotations_sha256": sha(annotation), "split": args.split, "tolerance": args.tolerance}, "detector_version": args.version, "runtime_seconds": args.runtime_seconds, "input_sha256": {k: sha(v) for k, v in files.items() if v.exists()}, "unavailable": ["post_human_review"]+([] if temporal is not None else ["temporal_candidates"]), "results": {stage: {kind: evaluate(ref, events, kind, args.split, args.tolerance) for kind in ("goal", "foul")} for stage, events in stages.items()}}
        if args.before:
            report["delta"] = compare(read(args.before), report)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output/"informe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        lines = [f"Jornada {args.round}, parte {args.half}; grupo {args.split}; tolerancia {args.tolerance}s"]
        for stage, kinds in report["results"].items():
            for kind, result in kinds.items():
                lines.append(f"{stage} / {kind}: reales {result['verified']}, encontrados {result['found']}, omitidos {len(result['missed'])}, falsos {len(result['false'])}, duplicados {len(result['duplicates'])}; aceptación {result['acceptance']}")
                for category in ("missed", "false", "duplicates", "pending", "unassessed"):
                    for event in result[category]:
                        lines.append(f"  {category}: {event['id']} @ {event['time']}s; intervalo {event.get('interval', [max(0,event['time']-10),event['time']+10])}")
        text = "\n".join(lines)
        (args.output/"informe.txt").write_text(text, encoding="utf8")
        print(text)
    except (ValueError, OSError, sqlite3.Error, KeyError) as error:
        parser.exit(2, f"Evaluación pendiente: {error}\n")


if __name__ == "__main__":
    main()
