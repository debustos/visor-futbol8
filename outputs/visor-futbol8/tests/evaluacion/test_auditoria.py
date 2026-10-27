"""Synthetic contract regressions; these do not measure sporting accuracy."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluacion.medir import compare, evaluate, main, normalize, sha, validate


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.ref = json.loads((Path(__file__).resolve().parents[2]/"evaluacion/ejemplo-sintetico.json").read_text())

    def test_published_fouls_are_not_dropped(self):
        rows = [dict(kind=k, time=20) for k in ("foul_won", "foul_committed")]
        self.assertEqual([p["kind"] for p in normalize(rows, [])], ["foul", "foul"])

    def test_legacy_goal_and_rival_without_author(self):
        rows = [dict(kind="shot", outcome="goal", time=20, team="rival", player_id=None),
                dict(kind="shot", outcome="saved", time=40)]
        predictions = normalize(rows, [])
        self.assertEqual(len(predictions), 1)
        result = evaluate(self.ref, predictions, "goal", "development")
        self.assertEqual(result["found"], 1)
        self.assertIsNone(predictions[0]["player_id"])
        self.assertEqual(predictions[0]["team"], "rival")

    def test_unknown_attribution_is_counted(self):
        self.ref["events"][0].update(team="orange", player_id="p9")
        pred = normalize([dict(kind="goal", time=20, team="unresolved")], [])
        result = evaluate(self.ref, pred, "goal", "development")
        self.assertEqual(result["team"]["unknown_prediction"], 1)
        self.assertEqual(result["author"]["unknown_prediction"], 1)
        self.assertEqual(result["author"]["accuracy"], 0)
        self.assertIsNone(pred[0]["team"])

    def test_pending_other_kind_does_not_hide_false_goal(self):
        self.ref["events"][0].update(kind="foul", status="pending")
        result = evaluate(self.ref, [dict(kind="goal", time=20)], "goal", "development")
        self.assertEqual(len(result["false"]), 1)

    def test_ambiguous_contact_is_not_a_verified_foul(self):
        self.ref["events"][0].update(kind="foul", status="ambiguous")
        validate(self.ref, "a"*64, 4, 1)
        result = evaluate(self.ref, [dict(kind="foul", time=20)], "foul", "development")
        self.assertEqual(result["verified"], 0)
        self.assertEqual(len(result["unassessed"]), 1)

    def test_overlapping_review_coverage_rejected(self):
        self.ref["coverage"]["holdout"] = [[40, 60]]
        with self.assertRaises(ValueError):
            validate(self.ref, "a"*64, 4, 1)

    def test_sequence_replay_cannot_cross_splits(self):
        self.ref["events"][0]["sequence_id"] = "same-goal"
        replay = copy.deepcopy(self.ref["events"][0])
        replay.update(id="replay", time=50, interval=[45, 55], split="holdout")
        self.ref["coverage"] = dict(development=[[0, 35]], holdout=[[40, 60]])
        self.ref["events"].append(replay)
        with self.assertRaises(ValueError):
            validate(self.ref, "a"*64, 4, 1)

    def test_other_split_prediction_is_not_unassessed(self):
        self.ref["coverage"] = dict(development=[[0, 35]], holdout=[[40, 60]])
        result = evaluate(self.ref, [dict(kind="goal", time=50)], "goal", "development")
        self.assertEqual(result["unassessed"], [])
        self.assertEqual(len(result["outside_split"]), 1)

    def test_synthetic_reference_cannot_pass_acceptance(self):
        self.ref["coverage"] = dict(development=[], holdout=[[0, 60]])
        self.ref["events"][0]["split"] = "holdout"
        result = evaluate(self.ref, [dict(kind="goal", time=20)], "goal", "holdout")
        self.assertEqual(result["acceptance"], "not_demonstrated")

    def test_exact_tolerance_is_inclusive(self):
        result = evaluate(self.ref, [dict(kind="goal", time=23)], "goal", "development")
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["mean_absolute_error_seconds"], 3)

    def test_one_prediction_cannot_match_two_goals(self):
        second = copy.deepcopy(self.ref["events"][0])
        second.update(id="second", time=22)
        self.ref["events"].append(second)
        result = evaluate(self.ref, [dict(kind="goal", time=21)], "goal", "development")
        self.assertEqual(result["found"], 1)
        self.assertEqual(len(result["missed"]), 1)

    def test_prediction_outside_original_is_invalid(self):
        with self.assertRaises(ValueError):
            evaluate(self.ref, [dict(kind="goal", time=61)], "goal", "development")

    def test_real_verified_annotation_needs_provenance(self):
        self.ref["synthetic"] = False
        with self.assertRaises(ValueError):
            validate(self.ref, "a"*64, 4, 1)

    def test_unknown_reference_is_not_in_accuracy_denominator(self):
        result = evaluate(self.ref, [dict(kind="goal", time=20)], "goal", "development")
        self.assertEqual(result["author"]["unknown_reference"], 1)
        self.assertEqual(result["author"]["known_reference"], 0)
        self.assertIsNone(result["author"]["accuracy"])

    def test_foul_recipient_is_not_compared_as_offender(self):
        self.ref["events"][0].update(kind="foul", player_id="p9", team="orange")
        row = dict(kind="foul_won", player_id="p9", team="orange", time=20)
        pred = normalize([row], [])
        result = evaluate(self.ref, pred, "foul", "development")
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["author"]["unknown_prediction"], 1)
        self.assertEqual(result["author"]["correct"], 0)
        self.ref["events"][0]["actor_role"] = "beneficiary"
        result = evaluate(self.ref, pred, "foul", "development")
        self.assertEqual(result["author"]["correct"], 1)
        row["kind"] = "foul_committed"
        self.ref["events"][0]["actor_role"] = "offender"
        result = evaluate(self.ref, normalize([row], []), "foul", "development")
        self.assertEqual(result["author"]["correct"], 1)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Deliberately not a video: tests exercise IO/contracts, never visual quality.
        (self.root/"original.mov").write_bytes(b"synthetic bytes, not sporting evidence")
        ref = json.loads((Path(__file__).resolve().parents[2]/"evaluacion/ejemplo-sintetico.json").read_text())
        ref["sha256"] = sha(self.root/"original.mov")
        self.write("reference.json", ref)
        self.write("actions.json", [dict(kind="shot", outcome="goal", time=20, state="candidate"),
                                    dict(kind="foul_won", time=40, state="estimated")])
        self.write("profiles.json", [])
        self.write("confirmed.json", [dict(kind="goal", time=20, state="confirmed"),
                                      dict(kind="goal", time=45, state="candidate")])
        self.args = ["medir", "--round", "4", "--half", "1", "--video", str(self.root/"original.mov"),
                     "--annotations", str(self.root/"reference.json"), "--actions", str(self.root/"actions.json"),
                     "--profiles", str(self.root/"profiles.json"), "--analysis-root", str(self.root),
                     "--output", str(self.root/"report"), "--version", "synthetic-test"]

    def write(self, name, value):
        (self.root/name).write_text(json.dumps(value), encoding="utf8")

    def run_command(self, extra=()):
        with patch("sys.argv", self.args+list(extra)), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            main()
        return json.loads((self.root/"report/informe.json").read_text(encoding="utf8"))

    def test_explicit_paths_separate_stages_and_preserve_inputs(self):
        inputs = {p: sha(p) for p in self.root.iterdir() if p.is_file()}
        report = self.run_command(["--confirmed-actions", str(self.root/"confirmed.json")])
        self.assertEqual(report["results"]["published_candidates"]["goal"]["found"], 1)
        self.assertEqual(report["results"]["published_accepted_pre_review"]["foul"]["false"][0]["time"], 40)
        self.assertEqual(report["results"]["post_human_review"]["goal"]["found"], 1)
        self.assertEqual(report["results"]["post_human_review"]["goal"]["false"], [])
        self.assertTrue(report["synthetic"])
        self.assertGreaterEqual(report["evaluator"]["seconds"], 0)
        self.assertEqual(report["evaluator"]["sha256"], sha(Path(__file__).resolve().parents[2]/"evaluacion/medir.py"))
        self.assertEqual(inputs, {p: sha(p) for p in inputs})

    def test_does_not_overwrite_previous_report(self):
        self.run_command()
        previous = sha(self.root/"report/informe.json")
        with self.assertRaises(SystemExit) as error:
            self.run_command()
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(previous, sha(self.root/"report/informe.json"))

    def test_wrong_original_does_not_generate_report(self):
        (self.root/"original.mov").write_bytes(b"wrong original")
        with self.assertRaises(SystemExit):
            self.run_command()
        self.assertFalse((self.root/"report").exists())

    def test_missing_explicit_temporal_is_not_silently_ignored(self):
        with self.assertRaises(SystemExit):
            self.run_command(["--temporal", str(self.root/"missing.json")])

    def test_comparison_same_reference_and_measured_runtime(self):
        self.run_command(["--runtime-seconds", "5"])
        self.args[self.args.index("--output")+1] = str(self.root/"new-report")
        self.run_command(["--runtime-seconds", "4", "--before", str(self.root/"report/informe.json")])
        report = json.loads((self.root/"new-report/informe.json").read_text(encoding="utf8"))
        self.assertEqual(report["detector_runtime_delta_seconds"], -1)
        self.assertEqual(report["delta"]["published_candidates"]["goal"]["found"], 0)
        self.assertEqual(report["delta"]["published_candidates"]["goal"]["precision"], 0)
        self.assertIsNone(report["delta"]["published_candidates"]["foul"]["recall"])

    def test_comparison_different_stages_is_invalid(self):
        with self.assertRaises(ValueError):
            compare(dict(identity=1, results={}), dict(identity=1, results={"other": {}}))

    def test_comparison_different_evaluator_is_invalid(self):
        before = dict(identity=1, results={}, evaluator=dict(sha256="old"))
        after = dict(identity=1, results={}, evaluator=dict(sha256="new"))
        with self.assertRaises(ValueError):
            compare(before, after)
