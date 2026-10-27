import copy
import json
from pathlib import Path
import unittest
from evaluacion.medir import evaluate, validate, matching, compare


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.ref = json.loads((Path(__file__).resolve().parents[2]/"evaluacion/ejemplo-sintetico.json").read_text())
        self.goal = self.ref["events"][0]
        self.goal["player_id"] = "player-9"
        self.goal["team"] = "home"

    def measure(self, preds):
        return evaluate(self.ref, preds, "goal", "development", 3)

    def prediction(self, time=20, **kwargs):
        return dict(id="p", kind="goal", time=time, player_id="player-9", team="home", **kwargs)

    def test_hit(self):
        self.assertEqual(self.measure([self.prediction()])["found"], 1)

    def test_missed(self):
        self.assertEqual(len(self.measure([])["missed"]), 1)

    def test_false(self):
        self.assertEqual(len(self.measure([self.prediction(45)])["false"]), 1)

    def test_duplicate(self):
        result = self.measure([self.prediction(), self.prediction(21)])
        self.assertEqual((result["found"],len(result["duplicates"]),result["precision"]),(1,1,.5))

    def test_outside_tolerance(self):
        result = self.measure([self.prediction(23.01)])
        self.assertEqual((result["found"],len(result["missed"])),(0,1))

    def test_wrong_author(self):
        pred = self.prediction(); pred["player_id"] = "wrong"
        result = self.measure([pred])
        self.assertEqual(result["found"],1)
        self.assertEqual(result["author"]["accuracy"],0)

    def test_unknown_team(self):
        self.goal["team"] = None
        self.assertIsNone(self.measure([self.prediction()])["team"]["accuracy"])

    def test_pending_foul(self):
        self.goal.update(kind="foul", status="pending")
        result = evaluate(self.ref,[dict(id="p",kind="foul",time=20)],"foul","development")
        self.assertEqual(result["false"],[])
        self.assertEqual(len(result["unassessed"]),1)

    def test_wrong_video(self):
        for h,r,p in [("b"*64,4,1),("a"*64,2,1),("a"*64,4,2)]:
            with self.assertRaises(ValueError): validate(self.ref,h,r,p)

    def test_unreviewed_not_negative(self):
        self.ref["coverage"]["development"] = []
        self.assertEqual(len(self.measure([self.prediction(50)])["unassessed"]),1)

    def test_matching_maximum_cardinality(self):
        self.assertEqual(len(matching([{"time":2},{"time":0}],[{"time":1},{"time":4}],2)),2)

    def test_leaking_split(self):
        event=copy.deepcopy(self.goal);event.update(id="other",split="holdout")
        self.ref["events"].append(event)
        with self.assertRaises(ValueError):validate(self.ref,"a"*64,4,1)

    def test_no_empty_acceptance(self):
        self.assertEqual(evaluate(self.ref,[],"goal","holdout")["acceptance"],"not_demonstrated")

    def test_compare_incompatible(self):
        with self.assertRaises(ValueError):compare({"identity":1},{"identity":2})
